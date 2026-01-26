"""Lightweight OCR-first DLG extractor.

This script keeps the pipeline intentionally simple: it rasterizes each PDF page,
performs Tesseract OCR, stitches words into lines, and looks for amounts that sit
near mentions of "DLG" or "Default Loss Guarantee". It skips the heavier table
segmentation used by ocr_dlg_extractor.py, so the output may need light manual
review, but it is fast to run and easy to tweak.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import io
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, List, Optional, Tuple, Union

import pdfplumber
import pytesseract
from PIL import ImageFilter, ImageOps
from pytesseract import Output

KEYWORDS = ("dlg", "default loss guarantee")
AMOUNT_REGEX = re.compile(
    r"(?:₹|INR|Rs\.?)?\s*([0-9OolI|S,/\.\-]{1}[0-9OolI|S,/\.\- ,]{2,})\s*(?:Cr|Crores?)?",
    re.IGNORECASE,
)
PORTFOLIO_REGEX = re.compile(r"^\s*portfolio\s+\d+", re.IGNORECASE)


def _normalize_amount_text(raw: str) -> Optional[str]:
    if not raw:
        return None
    translation = str.maketrans({
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "b": "8",
        "/": "7",
    })
    cleaned = raw.translate(translation)
    cleaned = re.sub(r"[^0-9.,-]", "", cleaned)
    cleaned = cleaned.strip(".,")
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    digit_count = len(re.sub(r"[^0-9]", "", cleaned))
    if digit_count < 3:
        return None
    # normalize thousand separators
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = parts[0] + "." + "".join(parts[1:])
    return cleaned


def _amount_to_float(text: str) -> Optional[float]:
    if not text:
        return None
    normalized = text.replace(",", "")
    try:
        return float(normalized)
    except ValueError:
        return None


@dataclass
class SimpleRecord:
    page: int
    amount: float
    amount_text: str
    line_text: str
    source: str
    confidence: float
    lender_hint: Optional[str]
    portfolio_hint: Optional[str]
    context_before: Optional[str]


def _ocr_lines(
    page: pdfplumber.page.Page,
    *,
    resolution: int,
    lang: str,
    min_conf: int,
    crop_top_pct: Optional[float],
    crop_bottom_pct: Optional[float],
    slice_count: Optional[int],
) -> List[str]:
    """

    :param page:
    :param resolution:
    :param lang:
    :param min_conf:
    :param crop_top_pct:
    :param crop_bottom_pct:
    :param slice_count:
    :return:
    """
    base_image = page.to_image(resolution=resolution).original.convert("L")
    width, height = base_image.size

    auto_band = _auto_detect_table_band(base_image, lang, min_conf) if (crop_top_pct is None or crop_bottom_pct is None) else None
    auto_y0, auto_y1 = auto_band if auto_band else (0, height)

    manual_y0 = (
        int(max(0.0, min(100.0, crop_top_pct)) / 100.0 * height)
        if crop_top_pct is not None
        else None
    )
    manual_y1 = (
        int(max(0.0, min(100.0, crop_bottom_pct)) / 100.0 * height)
        if crop_bottom_pct is not None
        else None
    )

    y0 = manual_y0 if manual_y0 is not None else auto_y0
    y1 = manual_y1 if manual_y1 is not None else auto_y1
    y1 = max(y0 + 10, min(height, y1))

    cropped = base_image.crop((0, y0, width, y1))

    if not slice_count or slice_count <= 0:
        band_height = y1 - y0
        slice_count = max(1, min(12, math.ceil(band_height / 150)))

    combined_lines: List[str] = []
    seen = set()
    slice_height = cropped.size[1] / slice_count

    for idx in range(slice_count):
        slice_top = int(idx * slice_height)
        slice_bottom = int(min(cropped.size[1], (idx + 1) * slice_height))
        if slice_bottom - slice_top < 10:
            continue
        slice_img = cropped.crop((0, slice_top, cropped.size[0], slice_bottom))
        slice_img = ImageOps.autocontrast(slice_img)
        slice_img = slice_img.filter(ImageFilter.MedianFilter(size=3))
        lines = _lines_from_image(slice_img, lang, min_conf)
        for line in lines:
            normalized = line.strip()
            if normalized and normalized not in seen:
                combined_lines.append(normalized)
                seen.add(normalized)

    return combined_lines


def _lines_from_image(image, lang: str, min_conf: int) -> List[str]:
    payloads = _ocr_line_payloads(image, lang, min_conf)
    return [payload["text"] for payload in payloads if payload["text"]]


def _ocr_line_payloads(
    image,
    lang: str,
    min_conf: int,
) -> List[dict]:
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config="--psm 6 --oem 3",
        output_type=Output.DICT,
    )
    grouped: dict[Tuple[int, int, int], dict] = {}
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
        bucket = grouped.setdefault(
            key,
            {"text": [], "conf": [], "x0": 10**9, "y0": 10**9, "x1": 0, "y1": 0},
        )
        bucket["text"].append(text)
        bucket["conf"].append(conf)
        left = data.get("left", [0])[idx]
        top = data.get("top", [0])[idx]
        width = data.get("width", [0])[idx]
        height = data.get("height", [0])[idx]
        bucket["x0"] = min(bucket["x0"], left)
        bucket["y0"] = min(bucket["y0"], top)
        bucket["x1"] = max(bucket["x1"], left + width)
        bucket["y1"] = max(bucket["y1"], top + height)

    payloads: List[dict] = []
    for key in sorted(grouped):
        bucket = grouped[key]
        joined = " ".join(bucket["text"]).strip()
        if not joined:
            continue
        avg_conf = sum(bucket["conf"]) / len(bucket["conf"]) if bucket["conf"] else 0.0
        payloads.append(
            {
                "text": joined,
                "bbox": (bucket["x0"], bucket["y0"], bucket["x1"], bucket["y1"]),
                "confidence": avg_conf,
            }
        )
    return payloads


def _auto_detect_table_band(
    image,
    lang: str,
    min_conf: int,
) -> Optional[Tuple[int, int]]:
    preview_conf = max(10, min_conf // 2)
    preview = ImageOps.autocontrast(image.copy())
    payloads = _ocr_line_payloads(preview, lang, preview_conf)
    boxes = [payload["bbox"] for payload in payloads if "portfolio" in payload["text"].lower()]
    if not boxes:
        return None
    y0 = min(box[1] for box in boxes)
    y1 = max(box[3] for box in boxes)
    pad = int(image.height * 0.05)
    return max(0, y0 - pad), min(image.height, y1 + pad)


def _portfolio_from_line(line: str) -> Optional[str]:
    match = re.search(r"(Portfolio\s+\d+)", line, re.IGNORECASE)
    if match:
        return match.group(1).title()
    return None


def _portfolio_amount_candidate(line: str) -> Optional[List[str]]:
    if not PORTFOLIO_REGEX.search(line):
        return None
    tokens = re.findall(r"[0-9OolI|S,/\.\-]+", line)
    tokens = [tok for tok in tokens if re.search(r"\d", tok)]
    if not tokens:
        return None
    return [tokens[-1]]


def _extract_amounts(lines: List[str], page_no: int) -> List[SimpleRecord]:
    records: List[SimpleRecord] = []
    history: List[str] = []
    keyword_window = 0

    def save(line_text: str, amounts: Iterable[str], ctx: Optional[str]) -> None:
        for amt in amounts:
            normalized = _normalize_amount_text(amt)
            if not normalized:
                continue
            value = _amount_to_float(normalized)
            if value is None:
                continue
            portfolio_hint = _portfolio_from_line(line_text)
            if not portfolio_hint:
                continue
            records.append(
                SimpleRecord(
                    page=page_no,
                    amount=value,
                    amount_text=normalized,
                    line_text=line_text.strip(),
                    source="simple",
                    confidence=0.0,
                    lender_hint=None,
                    portfolio_hint=portfolio_hint,
                    context_before=ctx,
                )
            )
            break

    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in KEYWORDS) or PORTFOLIO_REGEX.search(lower):
            keyword_window = 3

        portfolio_candidates = _portfolio_amount_candidate(line)
        amounts = portfolio_candidates if portfolio_candidates else AMOUNT_REGEX.findall(line)
        if amounts and keyword_window > 0:
            ctx = " | ".join(history[-2:]) if history else None
            save(line, amounts, ctx)
            keyword_window = 0
        elif amounts and PORTFOLIO_REGEX.search(lower):
            ctx = " | ".join(history[-2:]) if history else None
            save(line, amounts, ctx)

        history.append(line)
        if len(history) > 5:
            history.pop(0)

        if keyword_window > 0:
            keyword_window -= 1

    return records


def extract_simple(
    pdf_path: Union[Path, bytes, BinaryIO],
    *,
    resolution: int,
    lang: str,
    min_conf: int,
    dump_text: Optional[Path],
    crop_top: float,
    crop_bottom: float,
    slice_count: int,
) -> List[SimpleRecord]:
    all_records: List[SimpleRecord] = []
    text_dump: List[dict] = [] if dump_text else []

    pdf_source: Union[str, BinaryIO]
    if isinstance(pdf_path, (str, Path)):
        pdf_source = str(pdf_path)
    elif isinstance(pdf_path, bytes):
        pdf_source = io.BytesIO(pdf_path)
    else:
        pdf_source = pdf_path

    with pdfplumber.open(pdf_source) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            lines = _ocr_lines(
                page,
                resolution=resolution,
                lang=lang,
                min_conf=min_conf,
                crop_top_pct=crop_top,
                crop_bottom_pct=crop_bottom,
                slice_count=slice_count,
            )
            if dump_text is not None:
                for raw_line in lines:
                    text_dump.append({"page": page_no, "text": raw_line})
            all_records.extend(_extract_amounts(lines, page_no))

    if dump_text is not None:
        dump_text.write_text(json.dumps(text_dump, indent=2), encoding="utf-8")

    return all_records


def _write_output(records: List[SimpleRecord], output: Path, simple_csv: bool) -> None:
    payload = [asdict(rec) for rec in records]
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    elif output.suffix.lower() == ".csv":
        if simple_csv:
            fieldnames = ["portfolio", "amount_crores"]
            rows = [
                {
                    "portfolio": rec["portfolio_hint"] or rec["line_text"],
                        "amount_crores": round(rec["amount"] / 1e7, 4),
                }
                for rec in payload
                if rec["portfolio_hint"]
            ]
        else:
            fieldnames = [
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
            rows = payload
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        raise ValueError("Output path must end with .json or .csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick OCR-based DLG extractor")
    parser.add_argument("pdf", type=Path, help="Path to the disclosure PDF")
    parser.add_argument("-o", "--output", type=Path, help="Optional CSV/JSON output file")
    parser.add_argument("--resolution", type=int, default=300, help="Rasterization DPI (default: 300)")
    parser.add_argument("--lang", default="eng", help="Tesseract language code (default: eng)")
    parser.add_argument("--min-conf", type=int, default=60, help="Discard OCR words below this confidence")
    parser.add_argument("--dump-text", type=Path, help="Optional JSON dump of every OCR line")
    parser.add_argument("--tesseract-cmd", type=str, help="Override path to the tesseract executable")
    parser.add_argument(
        "--crop-top",
        type=float,
        default=None,
        help="Percent (0-100) from the top of the page to skip before OCR (auto if omitted)",
    )
    parser.add_argument(
        "--crop-bottom",
        type=float,
        default=None,
        help="Percent (0-100) of page height to keep (auto if omitted)",
    )
    parser.add_argument(
        "--slice-count",
        type=int,
        default=0,
        help="Split the cropped zone into this many horizontal slices before OCR (auto if 0)",
    )
    parser.add_argument(
        "--simple-csv",
        action="store_true",
        help="When writing CSV, only emit Portfolio/Amount columns",
    )
    args = parser.parse_args()

    if args.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract_cmd

    records = extract_simple(
        pdf_path=args.pdf,
        resolution=args.resolution,
        lang=args.lang,
        min_conf=args.min_conf,
        dump_text=args.dump_text,
        crop_top=args.crop_top,
        crop_bottom=args.crop_bottom,
        slice_count=args.slice_count,
    )

    if not records:
        print("No candidate DLG rows found.")
    else:
        for rec in records:
            if not rec.portfolio_hint:
                continue
            ctx_preview = rec.context_before or "-"
            print(
                f"Page {rec.page:02d} | Amount={rec.amount_text} | "
                f"Portfolio={rec.portfolio_hint} | Context={ctx_preview}"
            )

    if args.output:
        _write_output(records, args.output, args.simple_csv)


if __name__ == "__main__":
    main()
