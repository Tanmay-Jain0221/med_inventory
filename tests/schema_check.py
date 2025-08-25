import sqlite3, pathlib
p = pathlib.Path("db/inventory.sqlite")
print("DB exists:", p.exists(), p.resolve())
con = sqlite3.connect(p)
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", cur.fetchall())
