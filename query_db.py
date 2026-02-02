# query_db.py
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from sqlalchemy import text

factory = ConnectionFactory()
session = factory.get_session()

# Delete old Bajaj data
delete_query = text("""
DELETE FROM dlg.dlg_raw 
WHERE lsp_name LIKE '%Bajaj%';
""")

result = session.execute(delete_query)
session.commit()
print(f"Deleted {result.rowcount} old Bajaj row(s)")

session.close()
print("\nNow restart Flask and re-scrape Bajaj Finserv Direct Limited")