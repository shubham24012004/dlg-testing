"""Test Bajaj Finserv field matching."""
from utils.utils import pick_by_keys

# Simulate the HTML table row
row = {
    "Regulated Entity": "Bajaj Finance Limited",
    "Business Segment": "Business Loan",
    "Portfolio Count": "1",
    "Portfolio Value (₹)*": "94,81,23,630"
}

# Test field mapping
field_map = {
    "lender": "Regulated Entity",
    "portfolio": "Business Segment",
    "amount": "Portfolio Value (?)*",
    "as_on": {"constant": "2025-12-31"}
}

print("Row data:")
for k, v in row.items():
    print(f"  '{k}': '{v}'")

print("\n--- Testing field extraction ---")

# Test lender
lender_keys = [field_map["lender"]]
lender_val = pick_by_keys(row, lender_keys)
print(f"Lender (key='{lender_keys[0]}'): '{lender_val}'")

# Test portfolio
portfolio_keys = [field_map["portfolio"]]
portfolio_val = pick_by_keys(row, portfolio_keys)
print(f"Portfolio (key='{portfolio_keys[0]}'): '{portfolio_val}'")

# Test amount
amount_keys = [field_map["amount"]]
amount_val = pick_by_keys(row, amount_keys)
print(f"Amount (key='{amount_keys[0]}'): '{amount_val}'")

# Test parsing
if amount_val:
    from utils.utils import parse_amount_any, normalize_amount_to_crores
    parsed = parse_amount_any(amount_val)
    normalized = normalize_amount_to_crores(parsed)
    print(f"\nParsed: {parsed}")
    print(f"Normalized to crores: {normalized}")
else:
    print(f"\n❌ Amount extraction FAILED - couldn't find column")
