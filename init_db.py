"""Create the Colour-Fit database (colourfit.db, next to app.py).

    python init_db.py            create the tables if they are missing (safe to repeat)
    python init_db.py --demo     also add a demo account and a few sample clothes
    python init_db.py --reset    delete the existing database first (asks you to confirm)
    python init_db.py --reset --yes   same, without asking
"""
import argparse
import os
import sqlite3
import sys

import app as colourfit
from werkzeug.security import generate_password_hash

DEMO_USER, DEMO_PASSWORD = "demo", "demo123"
DEMO_CLOTHES = [                       # category, colour, style
    ("shirt", "navy", "Casual"), ("shirt", "white", "Formal"), ("shirt", "mustard", "Casual"),
    ("trousers", "beige", "Casual"), ("trousers", "charcoal", "Formal"), ("trousers", "denim", "Casual"),
    ("shoes", "white", "Casual"), ("shoes", "black", "Formal"),
]


def add_demo(path):
    code = colourfit._new_recovery_code()
    with sqlite3.connect(path) as db:
        if db.execute("SELECT 1 FROM users WHERE username = ?", (DEMO_USER,)).fetchone():
            print(f"Demo account '{DEMO_USER}' already exists, left unchanged.")
            return
        uid = db.execute(
            "INSERT INTO users (username, password_hash, recovery_hash) VALUES (?, ?, ?)",
            (DEMO_USER, generate_password_hash(DEMO_PASSWORD),
             generate_password_hash(colourfit._norm_code(code))),
        ).lastrowid
        db.executemany(
            "INSERT INTO clothes (user_id, category, colour, style) VALUES (?, ?, ?, ?)",
            [(uid, c, col, st) for c, col, st in DEMO_CLOTHES],
        )
    print(f"Demo account created:  username '{DEMO_USER}'  password '{DEMO_PASSWORD}'")
    print(f"Its recovery code:     {code}")


def main():
    ap = argparse.ArgumentParser(description="Create the Colour-Fit database.")
    ap.add_argument("--demo", action="store_true", help="add a demo account with sample clothes")
    ap.add_argument("--reset", action="store_true", help="delete the existing database first")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation with --reset")
    args = ap.parse_args()

    path = colourfit.DATABASE
    if args.reset and os.path.exists(path):
        if not args.yes and input(f"This deletes all accounts and clothes in {path}. Type 'yes' to continue: ").strip().lower() != "yes":
            print("Cancelled. Nothing was changed.")
            return 1
        os.remove(path)
        print("Old database deleted.")

    existed = os.path.exists(path)
    colourfit.init_db()                                  # creates tables, indexes and the uploads folder
    print(("Database already existed, tables checked: " if existed else "Database created: ") + path)

    with sqlite3.connect(path) as db:
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            rows = db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"  table {name:<8} {rows} row(s)")

    if args.demo:
        add_demo(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())