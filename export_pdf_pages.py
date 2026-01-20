"""Export each page of a PDF as a PNG image using pdfplumber.

Example usage:
    python export_pdf_pages.py --pdf D:\path\to\DLG_Declaration.pdf --out images\ --dpi 400
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pdfplumber


def export_pages(pdf_path: Path, output_dir: Path, dpi: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with pdfplumber.open(str(pdf_path)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            image = page.to_image(resolution=dpi)
            out_path = output_dir / f"{pdf_path.stem}_page_{idx:02d}.png"
            image.save(str(out_path), format="PNG")
            print(f"Saved {out_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export PDF pages as PNG images")
    parser.add_argument("--pdf", type=Path, required=True, help="Path to the PDF file")
    parser.add_argument("--out", type=Path, default=Path("images"), help="Folder to store PNG files")
    parser.add_argument("--dpi", type=int, default=300, help="Resolution used when rasterizing pages")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    export_pages(args.pdf, args.out, args.dpi)


if __name__ == "__main__":
    main()
