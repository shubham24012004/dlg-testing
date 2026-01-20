import pdfplumber
import io

pdf_path = r'd:\Users\Suhird\Downloads\DLG_Declaration.pdf'

with open(pdf_path, 'rb') as f:
    body = f.read()

with pdfplumber.open(io.BytesIO(body)) as pdf:
    for page_num, page in enumerate(pdf.pages):
        print(f"\n{'='*80}")
        print(f"PAGE {page_num + 1} ANALYSIS")
        print(f"{'='*80}\n")
        
        # Get all text objects
        print("ALL WORDS:")
        words = page.extract_words()
        for idx, word in enumerate(words[:50]):  # First 50 words
            print(f"{idx}: {word}")
        
        print(f"\nTotal words: {len(words)}")
        
        # Get all lines
        print("\n\nLINES DETECTED:")
        lines = page.lines
        print(f"Total lines: {len(lines)}")
        for idx, line in enumerate(lines[:20]):
            print(f"{idx}: {line}")
        
        # Get curves
        print("\n\nCURVES:")
        curves = page.curves
        print(f"Total curves: {len(curves)}")
        
        # Get rectangles
        print("\n\nRECTANGLES:")
        rects = page.rects
        print(f"Total rects: {len(rects)}")
        for idx, rect in enumerate(rects[:10]):
            print(f"{idx}: {rect}")
        
        # Try different table extraction strategies
        print("\n\nTABLE EXTRACTION ATTEMPTS:")
        
        # Strategy 1: Text-based
        print("\n1. Text strategy:")
        try:
            tables = page.extract_tables({
                "vertical_strategy": "text",
                "horizontal_strategy": "text"
            })
            print(f"   Tables found: {len(tables)}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Strategy 2: Lines-based
        print("\n2. Lines strategy:")
        try:
            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })
            print(f"   Tables found: {len(tables)}")
            for t_idx, table in enumerate(tables):
                print(f"   Table {t_idx + 1}: {len(table)} rows")
                for r_idx, row in enumerate(table[:5]):
                    print(f"     Row {r_idx}: {row}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Strategy 3: Explicit lines
        print("\n3. Explicit strategy:")
        try:
            tables = page.extract_tables({
                "vertical_strategy": "explicit",
                "horizontal_strategy": "explicit",
                "explicit_vertical_lines": page.curves + page.edges,
                "explicit_horizontal_lines": page.curves + page.edges
            })
            print(f"   Tables found: {len(tables)}")
        except Exception as e:
            print(f"   Error: {e}")
