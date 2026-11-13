-- Colour-Fit database (SQLite)
-- The app creates this automatically on first run, and `python init_db.py` does the same.
-- This file is for reference and for opening in tools such as DB Browser for SQLite.

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT    NOT NULL UNIQUE,      -- stored in lower case
    password_hash  TEXT    NOT NULL,             -- hashed, never the real password
    recovery_hash  TEXT                          -- hashed recovery code for password reset
);

CREATE TABLE IF NOT EXISTS clothes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id),
    category  TEXT    NOT NULL,                  -- shirt | trousers | shoes
    colour    TEXT    NOT NULL,                  -- e.g. navy, beige, mustard
    style     TEXT    NOT NULL,                  -- Casual | Formal | Party | Sports
    image     TEXT                               -- file name inside static/uploads (optional)
);

CREATE INDEX IF NOT EXISTS idx_clothes_user ON clothes(user_id);