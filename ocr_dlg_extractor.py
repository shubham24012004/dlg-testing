"""Utility for extracting DLG values from scanned disclosures using OCR.

The script first tries searchable text and then falls back to OCR when no DLG
rows are detected. Use ``--skip-text`` for scanned PDFs, ``--ocr-only`` to bypass
text parsing, and ``--dump-lines`` to debug what each pass sees. For layout driven
documents, ``--table-mode opencv`` uses morphological table segmentation, while
``--table-mode detector`` attempts a layoutparser/Detectron2 model when available.
Install the Tesseract binary separately and ensure the ``tesseract`` command is
available or provide ``--tesseract-cmd``.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from functools import lru_cache
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, TypedDict

import pdfplumber
import pytesseract
from PIL import ImageFilter, ImageOps
from pytesseract import Output

try:
    import layoutparser as lp  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    lp = None

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore

DLG_KEYWORDS = ("dlg", "default loss guarantee")
KEYWORD_WINDOW_SIZE = 8
OCR_CONFIG = "--psm 6 --oem 3"
AMOUNT_REGEX = re.compile(r"(?:₹|INR|Rs\.?)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(?:Cr|Crores?)?", re.IGNORECASE)
LENDER_REGEX = re.compile(r"(?:Lender|Partner|Bank)\s*[:\-]\s*(.+)", re.IGNORECASE)
PORTFOLIO_REGEX = re.compile(r"(Portfolio[\s\-:]*[A-Za-z0-9 .#\-/]+)", re.IGNORECASE)
DEFAULT_TABLE_DETECTOR_CONFIG = "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config"
LAYOUT_LABEL_MAP = {0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}


class LineInfo(TypedDict):
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]


class _LineBucket(TypedDict):
    text: List[str]
    conf: List[float]
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass
class DLGRecord:
    page: int
    amount: float
    amount_text: str
    line_text: str
    source: str
    confidence: float
    lender_hint: Optional[str] = None
    portfolio_hint: Optional[str] = None
    context_before: Optional[str] = None


def _looks_like_real_amount(token: str) -> bool:
    cleaned = token.replace(",", "").strip()
    numeric = re.sub(r"[^0-9]", "", cleaned)

    if cleaned.isdigit() and len(cleaned) <= 5:
        return False
    if len(numeric) < 3:
        return False
    if "." in cleaned:
        parts = cleaned.split(".")
        if len(parts[-1]) < 2:
            return False
    return True


def _page_lines_from_text(page: pdfplumber.page.Page) -> List[LineInfo]:
    text = page.extract_text() or ""
    lines: List[LineInfo] = []
    for raw in text.splitlines():
        cleaned = raw.strip()
        if cleaned:
            lines.append({"text": cleaned, "confidence": 100.0, "bbox": (0, 0, 0, 0)})
    return lines


def _page_lines_from_ocr(
    page: pdfplumber.page.Page,
    resolution: int,
    lang: str,
    min_conf: int,
) -> List[LineInfo]:
    pil_image = page.to_image(resolution=resolution).original.convert("L")
    pil_image = ImageOps.autocontrast(pil_image)
    pil_image = pil_image.filter(ImageFilter.MedianFilter(size=3))

    data = pytesseract.image_to_data(
        pil_image,
        lang=lang,
        config=OCR_CONFIG,
        output_type=Output.DICT,
    )

    grouped: Dict[Tuple[int, int, int], _LineBucket] = {}
    order: List[Tuple[int, int, int]] = []

    for idx, raw in enumerate(data["text"]):
        text = raw.strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][idx])
        except (KeyError, ValueError):
            conf = 0.0
        if conf < min_conf:
            continue
        key = (
            data.get("block_num", [0])[idx],
            data.get("par_num", [0])[idx],
            data.get("line_num", [0])[idx],
        )
        if key not in grouped:
            grouped[key] = {"text": [], "conf": [], "x0": 10**9, "y0": 10**9, "x1": 0, "y1": 0}
            order.append(key)
        grouped[key]["text"].append(text)
        grouped[key]["conf"].append(conf)
        left = data.get("left", [0])[idx]
        top = data.get("top", [0])[idx]
        width = data.get("width", [0])[idx]
        height = data.get("height", [0])[idx]
        bucket = grouped[key]
        bucket["x0"] = min(bucket["x0"], left)
        bucket["y0"] = min(bucket["y0"], top)
        bucket["x1"] = max(bucket["x1"], left + width)
        bucket["y1"] = max(bucket["y1"], top + height)

    lines: List[LineInfo] = []
    for key in order:
        payload = grouped[key]
        if not payload["text"]:
            continue
        joined = " ".join(payload["text"]).strip()
        if not joined:
            continue
        avg_conf = sum(payload["conf"]) / len(payload["conf"])
        lines.append({
            "text": joined,
            "confidence": avg_conf,
            "bbox": (payload["x0"], payload["y0"], payload["x1"], payload["y1"]),
        })
    return lines


@lru_cache(maxsize=1)
def _build_table_detector(cfg: str, thresh: float):
    if lp is None:
        raise RuntimeError(
            "Table detection requires layoutparser; install layoutparser[layoutmodels] to enable this mode."
        )
    if np is None:
        raise RuntimeError("Table detection requires numpy; install numpy to enable this mode.")
    return lp.Detectron2LayoutModel(
        cfg,
        extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", thresh],
        label_map=LAYOUT_LABEL_MAP,
        device="cpu",
    )


def _ensure_table_detector(config: str, score_thresh: float):
    return _build_table_detector(config, score_thresh)


def _table_lines_with_detector(
    page: pdfplumber.page.Page,
    resolution: int,
    lang: str,
    min_conf: int,
    detector_config: str,
    score_thresh: float,
) -> List[LineInfo]:
    try:
        detector = _ensure_table_detector(detector_config, score_thresh)
    except RuntimeError as exc:
        raise RuntimeError(str(exc))
    pil_image = page.to_image(resolution=resolution).original.convert("RGB")
    layout = detector.detect(np.array(pil_image))  # type: ignore[arg-type]
    table_blocks = [blk for blk in layout if blk.type and blk.type.lower() == "table"]
    lines: List[LineInfo] = []
    for block in table_blocks:
        x0, y0, x1, y1 = map(int, block.coordinates)
        table_lines = _ocr_table_crop(pil_image, (x0, y0, x1, y1), lang, min_conf)
        lines.extend(table_lines)
    return lines


def _table_lines_with_opencv(
    page: pdfplumber.page.Page,
    resolution: int,
    lang: str,
    min_conf: int,
) -> List[LineInfo]:
    if np is None or cv2 is None:
        raise RuntimeError("OpenCV table mode requires numpy and opencv-python to be installed.")
    pil_image = page.to_image(resolution=resolution).original.convert("L")
    boxes = _detect_table_boxes_opencv(pil_image)
    lines: List[LineInfo] = []
    color_image = pil_image.convert("RGB")
    for bbox in boxes:
        lines.extend(_ocr_table_crop(color_image, bbox, lang, min_conf))
    return lines


def _detect_table_boxes_opencv(image: "Image.Image") -> List[Tuple[int, int, int, int]]:
    if np is None or cv2 is None:
        return []
    gray = np.array(image)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )

    height, width = binary.shape
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 30, 10), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(height // 25, 10)))
    horizontal = cv2.dilate(cv2.erode(binary, horizontal_kernel, iterations=1), horizontal_kernel, iterations=1)
    vertical = cv2.dilate(cv2.erode(binary, vertical_kernel, iterations=1), vertical_kernel, iterations=1)

    table_mask = cv2.bitwise_or(horizontal, vertical)
    table_mask = cv2.dilate(table_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=2)

    contours = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]
    min_area = 0.003 * width * height

    boxes: List[Tuple[int, int, int, int]] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < min_area or h < 25 or w < 60:
            continue
        boxes.append((x, y, x + w, y + h))

    boxes = _merge_overlapping_boxes(boxes, pad=40)
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


def _merge_overlapping_boxes(
    boxes: List[Tuple[int, int, int, int]],
    *,
    pad: int = 30,
) -> List[Tuple[int, int, int, int]]:
    if not boxes:
        return []

    merged: List[Tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda b: (b[1], b[0])):
        if not merged:
            merged.append(box)
            continue
        last = merged[-1]
        if _boxes_touch_or_overlap(last, box, pad):
            merged[-1] = (
                min(last[0], box[0]),
                min(last[1], box[1]),
                max(last[2], box[2]),
                max(last[3], box[3]),
            )
        else:
            merged.append(box)
    return merged


def _boxes_touch_or_overlap(
    a: Tuple[int, int, int, int],
    b: Tuple[int, int, int, int],
    pad: int,
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (
        bx0 > ax1 + pad
        or bx1 < ax0 - pad
        or by0 > ay1 + pad
        or by1 < ay0 - pad
    )


def _ocr_table_crop(
    page_image: "Image.Image",
    bbox: Tuple[int, int, int, int],
    lang: str,
    min_conf: int,
) -> List[LineInfo]:
    crop = page_image.crop(bbox).convert("L")
    crop = ImageOps.autocontrast(crop)
    crop = crop.filter(ImageFilter.MedianFilter(size=3))

    data = pytesseract.image_to_data(
        crop,
        lang=lang,
        config=OCR_CONFIG,
        output_type=Output.DICT,
    )

    tokens: List[Dict[str, Any]] = []
    for idx, raw in enumerate(data["text"]):
        text = raw.strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][idx])
        except (KeyError, ValueError):
            conf = 0.0
        if conf < min_conf:
            continue
        left = bbox[0] + int(data.get("left", [0])[idx])
        top = bbox[1] + int(data.get("top", [0])[idx])
        width = int(data.get("width", [0])[idx])
        height = int(data.get("height", [0])[idx])
        token = {
            "text": text,
            "conf": conf,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "right": left + width,
            "bottom": top + height,
            "cx": left + width / 2,
            "cy": top + height / 2,
        }
        tokens.append(token)

    if not tokens:
        return []

    heights = [tok["height"] for tok in tokens if tok["height"] > 0]
    median_height = statistics.median(heights) if heights else 10
    row_tolerance = max(int(median_height * 0.7), 8)

    rows: List[Dict[str, Any]] = []
    for token in sorted(tokens, key=lambda t: t["cy"]):
        assigned = False
        for row in rows:
            if abs(token["cy"] - row["cy"]) <= row_tolerance:
                row["tokens"].append(token)
                row["cy"] = (row["cy"] * row["count"] + token["cy"]) / (row["count"] + 1)
                row["bbox"][0] = min(row["bbox"][0], token["left"])
                row["bbox"][1] = min(row["bbox"][1], token["top"])
                row["bbox"][2] = max(row["bbox"][2], token["right"])
                row["bbox"][3] = max(row["bbox"][3], token["bottom"])
                row["count"] += 1
                assigned = True
                break
        if not assigned:
            rows.append(
                {
                    "tokens": [token],
                    "cy": token["cy"],
                    "count": 1,
                    "bbox": [token["left"], token["top"], token["right"], token["bottom"]],
                }
            )

    clustered_lines: List[LineInfo] = []
    for row in rows:
        row_tokens = sorted(row["tokens"], key=lambda t: t["left"])
        row_text = " | ".join(_merge_row_columns(row_tokens))
        if not row_text.strip():
            continue
        avg_conf = sum(t["conf"] for t in row_tokens) / len(row_tokens)
        clustered_lines.append(
            {
                "text": row_text.strip(),
                "confidence": avg_conf,
                "bbox": (int(row["bbox"][0]), int(row["bbox"][1]), int(row["bbox"][2]), int(row["bbox"][3])),
            }
        )

    return clustered_lines


def _merge_row_columns(tokens: List[Dict[str, Any]]) -> List[str]:
    widths = [tok["width"] for tok in tokens if tok["width"] > 0]
    median_width = statistics.median(widths) if widths else 20
    col_tolerance = max(int(median_width * 0.8), 15)

    column_centers: List[float] = []
    for token in sorted(tokens, key=lambda t: t["cx"]):
        placed = False
        for idx, center in enumerate(column_centers):
            if abs(token["cx"] - center) <= col_tolerance:
                column_centers[idx] = (center + token["cx"]) / 2
                token["col_idx"] = idx
                placed = True
                break
        if not placed:
            column_centers.append(token["cx"])
            token["col_idx"] = len(column_centers) - 1

    column_text: List[str] = []
    for idx in range(len(column_centers)):
        col_tokens = [tok for tok in tokens if tok.get("col_idx") == idx]
        if not col_tokens:
            column_text.append("")
            continue
        column_text.append(" ".join(tok["text"] for tok in sorted(col_tokens, key=lambda t: t["left"])))

    cleaned = [txt.strip() for txt in column_text if txt.strip()]
    return cleaned or [" ".join(tok["text"] for tok in tokens)]


def _find_hint(lines: Sequence[str], pattern: re.Pattern[str]) -> Optional[str]:
    for text in reversed(lines):
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def _build_record(
    amount_txt: str,
    line_text: str,
    confidence: float,
    page_no: int,
    source: str,
    context: Sequence[str],
) -> Optional[DLGRecord]:
    try:
        amount = float(amount_txt.replace(",", ""))
    except ValueError:
        return None

    hints_input = list(context) + [line_text]
    lender_hint = _find_hint(hints_input, LENDER_REGEX)
    portfolio_hint = _find_hint(hints_input, PORTFOLIO_REGEX)

    ctx = " | ".join(list(context)[-2:]) if context else None

    return DLGRecord(
        page=page_no,
        amount=amount,
        amount_text=amount_txt,
        line_text=line_text,
        source=source,
        confidence=confidence,
        lender_hint=lender_hint,
        portfolio_hint=portfolio_hint,
        context_before=ctx,
    )


def _extract_from_lines(
    lines: List[LineInfo],
    page_no: int,
    source: str,
    y_margin: int,
) -> List[DLGRecord]:
    records: List[DLGRecord] = []
    history: List[str] = []
    pending_keyword_line: Optional[str] = None
    pending_confidence: float = 0.0
    keyword_window = 0
    last_keyword_bbox: Optional[Tuple[int, int, int, int]] = None

    for entry in lines:
        text = entry["text"].strip()
        if not text:
            continue

        confidence = float(entry.get("confidence", 0.0))
        lower = text.lower()
        has_keyword = any(k in lower for k in DLG_KEYWORDS)
        if has_keyword:
            keyword_window = KEYWORD_WINDOW_SIZE
            last_keyword_bbox = entry.get("bbox")

        amounts = [tok for tok in AMOUNT_REGEX.findall(text) if _looks_like_real_amount(tok)]
        if "cin" in lower:
            amounts = []

        allow_without_keyword = keyword_window > 0

        def save_record(line_text: str, candidates: Iterable[str], base_conf: float) -> None:
            for amt_txt in candidates:
                rec = _build_record(amt_txt, line_text, base_conf, page_no, source, history)
                if rec:
                    records.append(rec)
                break

        if has_keyword and amounts:
            save_record(text, amounts, confidence)
            pending_keyword_line = None
        elif has_keyword:
            pending_keyword_line = text
            pending_confidence = confidence
        elif amounts and pending_keyword_line:
            combined = f"{pending_keyword_line} | {text}"
            save_record(combined, amounts, min(confidence, pending_confidence))
            pending_keyword_line = None
        elif amounts and allow_without_keyword:
            same_column = False
            if last_keyword_bbox and "bbox" in entry:
                _, y0_kw, _, y1_kw = last_keyword_bbox
                _, y0_curr, _, y1_curr = entry["bbox"]
                kw_top = y0_kw - y_margin
                kw_bottom = y1_kw + y_margin
                curr_top = y0_curr - y_margin
                curr_bottom = y1_curr + y_margin
                overlap = min(kw_bottom, curr_bottom) - max(kw_top, curr_top)
                height = max((y1_kw - y0_kw) + 2 * y_margin, 1)
                same_column = overlap / height >= 0.3
            if same_column:
                save_record(text, amounts, confidence)
        else:
            pending_keyword_line = None

        history.append(text)
        if len(history) > 6:
            history.pop(0)

        if keyword_window > 0:
            keyword_window -= 1

    return records


def _deduplicate(records: List[DLGRecord]) -> List[DLGRecord]:
    seen = set()
    deduped: List[DLGRecord] = []
    for rec in records:
        key = (rec.page, rec.line_text.lower(), rec.amount_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    return deduped


def extract_dlg_with_ocr(
    pdf_path: Path,
    *,
    resolution: int = 300,
    lang: str = "eng",
    min_conf: int = 60,
    ocr_only: bool = False,
    force_ocr: bool = False,
    dump_lines: Optional[Path] = None,
    skip_text: bool = False,
    y_margin: int = 40,
    table_mode: str = "simple",
    table_detector_config: str = DEFAULT_TABLE_DETECTOR_CONFIG,
    table_score_thresh: float = 0.5,
) -> List[DLGRecord]:
    records: List[DLGRecord] = []
    debug_rows: List[Dict[str, Any]] = [] if dump_lines else []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            page_records: List[DLGRecord] = []

            if not skip_text and not ocr_only:
                text_lines = _page_lines_from_text(page)
                if dump_lines:
                    for ln in text_lines:
                        debug_rows.append({
                            "page": page_idx,
                            "mode": "text",
                            "confidence": ln["confidence"],
                            "text": ln["text"],
                            "bbox": ln.get("bbox"),
                        })
                page_records.extend(_extract_from_lines(text_lines, page_idx, "text", y_margin))

            if table_mode == "detector":
                try:
                    detector_lines = _table_lines_with_detector(
                        page,
                        resolution,
                        lang,
                        min_conf,
                        table_detector_config,
                        table_score_thresh,
                    )
                except RuntimeError as exc:
                    print(f"[table-detector] {exc}", file=sys.stderr)
                    detector_lines = []

                if dump_lines:
                    for ln in detector_lines:
                        debug_rows.append({
                            "page": page_idx,
                            "mode": "table-detector",
                            "confidence": ln.get("confidence", 0.0),
                            "text": ln.get("text", ""),
                            "bbox": ln.get("bbox"),
                        })

                if detector_lines:
                    page_records.extend(_extract_from_lines(detector_lines, page_idx, "table", y_margin))

            elif table_mode == "opencv":
                try:
                    opencv_lines = _table_lines_with_opencv(page, resolution, lang, min_conf)
                except RuntimeError as exc:
                    print(f"[table-opencv] {exc}", file=sys.stderr)
                    opencv_lines = []

                if dump_lines:
                    for ln in opencv_lines:
                        debug_rows.append({
                            "page": page_idx,
                            "mode": "table-opencv",
                            "confidence": ln.get("confidence", 0.0),
                            "text": ln.get("text", ""),
                            "bbox": ln.get("bbox"),
                        })

                if opencv_lines:
                    page_records.extend(_extract_from_lines(opencv_lines, page_idx, "table", y_margin))

            should_run_ocr = ocr_only or force_ocr or not page_records
            if should_run_ocr:
                ocr_lines = _page_lines_from_ocr(page, resolution, lang, min_conf)
                if dump_lines:
                    for ln in ocr_lines:
                        debug_rows.append({
                            "page": page_idx,
                            "mode": "ocr",
                            "confidence": ln.get("confidence", 0.0),
                            "text": ln.get("text", ""),
                            "bbox": ln.get("bbox"),
                        })
                page_records.extend(_extract_from_lines(ocr_lines, page_idx, "ocr", y_margin))

            if page_records:
                records.extend(page_records)

    result = _deduplicate(records)
    if dump_lines:
        _write_debug_lines(debug_rows, dump_lines)
    return result


def _write_output(records: List[DLGRecord], output: Path) -> None:
    data = [asdict(r) for r in records]
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    elif output.suffix.lower() == ".csv":
        fieldnames = list(data[0].keys()) if data else [
            "page",
            "amount",
            "amount_text",
            "line_text",
            "source",
            "confidence",
            "lender_hint",
            "portfolio_hint",
            "context_before",
        ]
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
    else:
        raise ValueError("Unsupported output extension. Use .json or .csv.")


def _write_debug_lines(entries: List[Dict[str, Any]], output: Path) -> None:
    output.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _print_records(records: List[DLGRecord]) -> None:
    for rec in records:
        lender = rec.lender_hint or "?"
        portfolio = rec.portfolio_hint or "?"
        print(
            f"Page {rec.page:02d} | {rec.source.upper():3} | Amount={rec.amount_text} | "
            f"Lender={lender} | Portfolio={portfolio} | Context={rec.context_before or '-'}",
            flush=True,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract DLG values from PDFs using OCR fallback.")
    parser.add_argument("pdf", type=Path, help="Path to the disclosure PDF")
    parser.add_argument("-o", "--output", type=Path, help="Optional CSV or JSON output path")
    parser.add_argument("--resolution", type=int, default=300, help="Rasterization DPI for OCR")
    parser.add_argument("--lang", default="eng", help="Tesseract language code (default: eng)")
    parser.add_argument("--min-conf", type=int, default=60, help="Minimum OCR word confidence to keep")
    parser.add_argument("--ocr-only", action="store_true", help="Skip the text extraction stage")
    parser.add_argument("--force-ocr", action="store_true", help="Run OCR even if text extraction succeeded")
    parser.add_argument("--skip-text", action="store_true", help="Disable the text extraction pass")
    parser.add_argument("--tesseract-cmd", type=str, help="Absolute path to the tesseract executable")
    parser.add_argument("--no-print", action="store_true", help="Suppress stdout logging of extracted rows")
    parser.add_argument("--dump-lines", type=Path, help="Dump every extracted line (text + OCR) to JSON")
    parser.add_argument(
        "--y-margin",
        type=int,
        default=40,
        help="Vertical tolerance (in px) when matching amount lines to keywords",
    )
    parser.add_argument(
        "--table-mode",
        choices=["simple", "detector", "opencv"],
        default="simple",
        help="How to pre-segment tables before OCR (simple = legacy page scan, detector = layoutparser).",
    )
    parser.add_argument(
        "--table-detector-config",
        default=DEFAULT_TABLE_DETECTOR_CONFIG,
        help="layoutparser config URI or path used when --table-mode=detector",
    )
    parser.add_argument(
        "--table-score-thresh",
        type=float,
        default=0.5,
        help="Minimum detection confidence for table blocks when using the detector mode",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract_cmd

    records = extract_dlg_with_ocr(
        pdf_path=args.pdf,
        resolution=args.resolution,
        lang=args.lang,
        min_conf=args.min_conf,
        ocr_only=args.ocr_only,
        force_ocr=args.force_ocr,
        dump_lines=args.dump_lines,
        skip_text=args.skip_text,
        y_margin=args.y_margin,
        table_mode=args.table_mode,
        table_detector_config=args.table_detector_config,
        table_score_thresh=args.table_score_thresh,
    )

    if not args.no_print:
        _print_records(records)

    if args.output:
        _write_output(records, args.output)


if __name__ == "__main__":
    main()
