"""One self-check for db.py (sqlite only, stdlib). Run: python3 scripts/test_db.py"""
import importlib.util
import os
import sqlite3
import sys
import tempfile

spec = importlib.util.spec_from_file_location("db", os.path.join(os.path.dirname(__file__), "db.py"))
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)

tmp = tempfile.mkdtemp()
os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_PATH"] = os.path.join(tmp, "t.db")
con = sqlite3.connect(os.environ["DB_PATH"])
con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
con.execute("INSERT INTO users (name) VALUES ('ann'), ('bob')")
con.commit()

with open(os.path.join(tmp, "s.env"), "w") as f:
    f.write("# comment\nexport DB_TYPE='sqlite'\nDB_PATH=\"%s\"\nEMPTY=\n" % os.environ["DB_PATH"])
os.environ["DB_TYPE"] = "postgres"  # preset env must win over file
db.load_env(os.path.join(tmp, "s.env"))
assert os.environ["DB_TYPE"] == "postgres", "preset env must win"
os.environ["DB_TYPE"] = "sqlite"

assert db.READ_RE.match("  WITH x AS (SELECT 1) SELECT * FROM x")
assert db.READ_RE.match("select 1") and not db.READ_RE.match("DELETE FROM users")

con2, dialect = db.connect()
cur = con2.cursor()
assert dialect == "sqlite"
assert db.list_tables(cur, dialect)[1] == [("users",)]
h, rows = db.describe(cur, dialect, "users")
assert [r[1] for r in rows] == ["id", "name"], rows
cur.execute("SELECT name FROM users ORDER BY 1")
assert [tuple(r) for r in cur.fetchall()] == [("ann",), ("bob",)]
try:
    db.describe(cur, dialect, "nope")
    sys.exit("FAIL: bad table accepted")
except SystemExit:
    pass
print("ok: load_env, read-guard, tables, schema, select, bad-table")
