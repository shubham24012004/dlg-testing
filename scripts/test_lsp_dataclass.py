import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster

# should construct without id now
lm = LspMaster(
    lsp_name='Example LSP',
    disclosure_url='https://example.com/dlg.pdf',
    is_active=True,
    fetch_hint='auto',
    parse_hint='auto',
    rules_json=None,
    lsp_id='example-lsp',
    home_url='https://example.com'
)
print('Constructed LspMaster:', lm)
