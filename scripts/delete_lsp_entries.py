"""Delete specified LSP ids from DB."""
import sys, os
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import LspMasterORM, DlgCrawlerConfigORM

DB = Path('dlg_analysis.db')
IDS = ['my-lsp-1','lsp-a','lsp-b']

cf = ConnectionFactory(str(DB))
session = cf.get_session()
try:
    for i in IDS:
        # try numeric id first, else treat as legacy id
        try:
            int_id = int(i)
            lm = session.query(LspMasterORM).filter_by(id=int_id).one_or_none()
        except Exception:
            lm = session.query(LspMasterORM).filter_by(legacy_id=i).one_or_none()
        if lm:
            print('Deleting LSP:', i)
            cfg = session.query(DlgCrawlerConfigORM).filter_by(lsp_id=lm.id).one_or_none()
            if cfg:
                session.delete(cfg)
            session.delete(lm)
        else:
            print('Not found:', i)
    session.commit()
    print('Done')
except Exception as e:
    session.rollback()
    print('Error:', e)
finally:
    session.close()
