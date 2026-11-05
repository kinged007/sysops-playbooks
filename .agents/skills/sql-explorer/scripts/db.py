#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["psycopg[binary]", "pymysql"]
# ///
"""db.py: run SQL using a secrets file the agent never needs to read.

Usage (run from repo root):
  scripts/db.py --exec runs/sql-explorer-<suffix> tables
  scripts/db.py --exec runs/sql-explorer-<suffix> schema [table]
  scripts/db.py --exec runs/sql-explorer-<suffix> q "SELECT ..." [--limit N] [--csv out.csv]
  scripts/db.py --exec runs/sql-explorer-<suffix> exec "UPDATE ..." --yes [--csv out.csv]

Secrets live in <exec>/secrets/db.env (KEY=VALUE, see templates/db.env.example).
Values already in the environment win. Nothing secret is ever printed.
"""

import argparse
import csv
import os
import re
import sqlite3
import sys

READ_RE = re.compile(r"\s*(select|with|values|table|explain|show|describe|desc)\b", re.I)


def load_env(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.removeprefix("export ").strip()
                os.environ.setdefault(k, v.strip().strip("'\""))
    except FileNotFoundError:
        sys.exit(f"error: secrets file not found: {path}")


def connect():
    t = os.environ.get("DB_TYPE", "postgres").lower()
    if t == "sqlite":
        if not os.environ.get("DB_PATH"):
            sys.exit("error: DB_PATH is not set")
        return sqlite3.connect(os.environ["DB_PATH"]), t
    if t == "postgres":
        try:
            from psycopg import connect as pgconnect
        except ImportError:
            sys.exit("error: psycopg missing (run via the uv shebang, not plain python)")
        kw = {k: os.environ.get(v) for k, v in {
            "host": "DB_HOST", "port": "DB_PORT", "dbname": "DB_NAME",
            "user": "DB_USER", "password": "DB_PASSWORD", "sslmode": "DB_SSLMODE"}.items()}
        return pgconnect(**{k: v for k, v in kw.items() if v}), t
    if t == "mysql":
        try:
            import pymysql
        except ImportError:
            sys.exit("error: pymysql missing (run via the uv shebang, not plain python)")
        return pymysql.connect(
            host=os.environ.get("DB_HOST"), port=int(os.environ.get("DB_PORT", 3306)),
            database=os.environ.get("DB_NAME"), user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD")), t
    sys.exit(f"error: unknown DB_TYPE: {t} (want postgres|mysql|sqlite)")


def list_tables(cur, dialect):
    if dialect == "sqlite":
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name NOT LIKE 'sqlite_%' ORDER BY 1")
        return ("table",), [(r[0],) for r in cur.fetchall()]
    if dialect == "postgres":
        cur.execute("SELECT table_schema || '.' || table_name FROM information_schema.tables"
                    " WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1")
    else:
        cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES"
                    " WHERE TABLE_SCHEMA = DATABASE() ORDER BY 1")
    return ("table",), [(r[0],) for r in cur.fetchall()]


def describe(cur, dialect, table):
    if dialect == "sqlite":
        names = [r[0] for r in list_tables(cur, dialect)[1]]
        targets = [table] if table else names
        if table and table not in names:
            sys.exit(f"error: no such table: {table}")
        rows = []
        for t in targets:
            cur.execute(f'PRAGMA table_info("{t.replace(chr(34), "")}")')
            rows += [(t,) + tuple(r[1:3]) + (bool(r[3]),) for r in cur.fetchall()]
        return ("table", "column", "type", "notnull"), rows
    if dialect == "postgres":
        q = ("SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns"
             " WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")
        args = ()
        if table:
            q += " AND table_name = %s"
            args = (table,)
        cur.execute(q + " ORDER BY 1, ordinal_position", args)
    else:
        q = ("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM information_schema.COLUMNS"
             " WHERE TABLE_SCHEMA = DATABASE()")
        args = ()
        if table:
            q += " AND TABLE_NAME = %s"
            args = (table,)
        cur.execute(q + " ORDER BY 1, ORDINAL_POSITION", args)
    return ("table", "column", "type", "nullable"), [tuple(r) for r in cur.fetchall()]


def show(header, rows):
    widths = [max(len(str(v)) for v in [h, *[r[i] for r in rows]]) for i, h in enumerate(header)]
    fmt = " | ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*header))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*[str(v) for v in r]))


# ponytail: single-statement execute only (no multi-statement scripts);
# upgrade to executescript/split when a run needs it.
def main():
    ap = argparse.ArgumentParser(description="Query a database via its execution-folder secrets.")
    ap.add_argument("--exec", default=None, help="execution folder (reads <exec>/secrets/db.env)")
    ap.add_argument("--secrets", default=None, help="secrets file path (overrides --exec)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tables", help="list tables")
    sc = sub.add_parser("schema", help="show columns (all tables or one)")
    sc.add_argument("table", nargs="?")
    for name in ("q", "exec"):
        c = sub.add_parser(name, help="read query (q)" if name == "q" else "write query (exec, needs --yes)")
        c.add_argument("sql")
        c.add_argument("--limit", type=int, default=100, help="max rows (0 = all)")
        c.add_argument("--csv", default=None, help="also write rows to this CSV file")
        if name == "exec":
            c.add_argument("--yes", action="store_true", help="confirm the write")
    a = ap.parse_args()
    secrets = a.secrets or (os.path.join(a.exec, "secrets", "db.env") if a.exec else None)
    if not secrets:
        sys.exit("error: pass --exec <folder> or --secrets <file>")
    load_env(secrets)
    if a.cmd == "exec" and not a.yes:
        sys.exit("error: write refused without --yes (needs plan approval first)")

    try:
        con, dialect = connect()
        cur = con.cursor()
        if a.cmd == "tables":
            header, rows = list_tables(cur, dialect)
        elif a.cmd == "schema":
            header, rows = describe(cur, dialect, a.table)
        else:
            if a.cmd == "q" and not READ_RE.match(a.sql):
                sys.exit("error: q takes reads only (use exec for writes)")
            cur.execute(a.sql)
            header = tuple(d[0] for d in cur.description) if cur.description else ("affected",)
            fetched = cur.fetchall() if cur.description else []
            rows = [tuple(r) for r in fetched]
            if not cur.description:
                rows = [(cur.rowcount,)]
            con.commit() if a.cmd == "exec" else con.rollback()
        limit = getattr(a, "limit", 0)
        if limit and len(rows) > limit:
            rows, truncated = rows[:limit], True
        else:
            truncated = False
        if rows or a.cmd in ("tables", "schema"):
            show(header, rows)
        out_csv = getattr(a, "csv", None)
        if out_csv:
            with open(out_csv, "w", newline="") as f:
                csv.writer(f).writerows([header, *rows])
        print(f"{len(rows)} row(s){' (truncated, raise --limit)' if truncated else ''}"
              f"{f' -> {out_csv}' if out_csv else ''}", file=sys.stderr)
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
