# dlg-analysis
Default Loan Guarantee Web Scraping and Data Analysis

## OCR fallback for scanned disclosures

Some LSP disclosures embed the DLG table as an image, which means the regular
PDF parser cannot see the numbers. Use `ocr_dlg_extractor.py` whenever you run
into such files.

1. Install the Tesseract executable (https://github.com/tesseract-ocr/tesseract)
	and add it to `PATH`. On Windows you can pass the executable location to the
	script via `--tesseract-cmd` if you prefer not to adjust environment
	variables.
2. Install the Python dependencies: `pip install -r requirements.txt`.
3. Run the extractor:

	```bash
	python ocr_dlg_extractor.py "d:\path\to\DLG.pdf" --output data\ocr_results.json
	```

`ocr_dlg_extractor.py` first attempts to reuse searchable text and then falls
back to OCR for pages where no DLG values were detected. Use `--ocr-only` to
force OCR for every page, or `--force-ocr` to combine both methods. The script
prints each hit to stdout and can additionally emit CSV/JSON files for further
post-processing.
