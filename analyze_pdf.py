import pdfplumber
import json

pdf_path = r'd:\Users\Suhird\Downloads\DLG_Declaration.pdf'

with pdfplumber.open(pdf_path) as pdf:
    print(f'Total pages: {len(pdf.pages)}\n')
    
    for i, page in enumerate(pdf.pages):
        print(f'=== PAGE {i+1} ===')
        print(f'Page dimensions: {page.width} x {page.height}')
        print()
        
        # Extract text
        text = page.extract_text()
        if text:
            print('TEXT CONTENT:')
            print(text)
            print()
        
        # Try different table extraction settings
        table_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "explicit_vertical_lines": [],
            "explicit_horizontal_lines": [],
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 3,
            "min_words_vertical": 3,
            "min_words_horizontal": 1,
        }
        
        # Extract tables with default settings
        tables = page.extract_tables()
        print(f'Tables (default): {len(tables)}\n')
        
        for j, table in enumerate(tables):
            print(f'TABLE {j+1} (default):')
            print(f'Total rows: {len(table)}')
            
            for row_idx, row in enumerate(table):
                print(f'Row {row_idx}: {row}')
            print()
        
        # Try with text-based extraction
        tables_text = page.extract_tables(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})
        print(f'\nTables (text strategy): {len(tables_text)}\n')
        
        for j, table in enumerate(tables_text):
            print(f'TABLE {j+1} (text):')
            print(f'Total rows: {len(table)}')
            
            for row_idx, row in enumerate(table):
                print(f'Row {row_idx}: {row}')
            print()
        
        print('-' * 80)
        print()
