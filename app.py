import base64
import io
import os
import secrets
import sqlite3
import time
import uuid
from datetime import timedelta
from collections import defaultdict, deque
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from assistant import (AssistantError, ask, is_configured, load_env_file,
                       wardrobe_summary)
from colour_rules import find_combinations
from garment_image import PhotoError, process_photo

# Optional .env file (e.g. GEMINI_API_KEY=...) next to app.py
load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.permanent_session_lifetime = timedelta(days=30)      # used when "Remember me" is ticked
# Set this in your environment: export SECRET_KEY="a-long-random-string"
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "colourfit.db")

# Uploads
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB per photo

# Wardrobe options (values must match colour_rules.py)
CATEGORIES = {"shirt": "Shirts", "trousers": "Trousers", "shoes": "Shoes"}
STYLES = ["Casual", "Formal", "Party", "Sports"]
COLOURS = {
    "black": "#1E1E1E", "white": "#FFFFFF", "grey": "#9AA1AE",
    "charcoal": "#3A3D44", "beige": "#E9DFC9", "cream": "#F4EBD0",
    "navy": "#1B2440", "denim": "#3F5F8A", "blue": "#2F6FD0",
    "red": "#C62828", "maroon": "#7A1F2B", "burgundy": "#6D1A36",
    "orange": "#E8741C", "mustard": "#D9A21B", "yellow": "#F2D230",
    "olive": "#6B7A3A", "green": "#2E8B4F", "teal": "#1F7A74",
    "purple": "#6F3FA0", "pink": "#E58AB0",
}


# ---------- Database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password_hash TEXT NOT NULL,
                   recovery_hash TEXT
               )"""
        )
        cols = [r[1] for r in db.execute("PRAGMA table_info(users)")]
        if "recovery_hash" not in cols:                     # database from an older version
            db.execute("ALTER TABLE users ADD COLUMN recovery_hash TEXT")
        db.execute(
            """CREATE TABLE IF NOT EXISTS clothes (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL REFERENCES users(id),
                   category TEXT NOT NULL,
                   colour TEXT NOT NULL,
                   style TEXT NOT NULL,
                   image TEXT
               )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_clothes_user ON clothes(user_id)")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------- Auth helpers ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Log in to see your wardrobe.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ---------- Routes ----------
# --- recovery codes: lets a user reset a forgotten password without email ---
_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"          # no look-alike characters


def _new_recovery_code():
    raw = "".join(secrets.choice(_CODE_CHARS) for _ in range(12))
    return "-".join(raw[i:i + 4] for i in range(0, 12, 4))


def _norm_code(code):
    return "".join(ch for ch in code.upper() if ch.isalnum())


# --- slow down repeated wrong guesses (per address + username) ---
_failures = defaultdict(deque)
_MAX_FAILS, _FAIL_WINDOW, _LOCK_SECONDS = 5, 300, 60


def _throttle_key(username):
    return (request.remote_addr or "?", username)


def _seconds_locked(key):
    now = time.time()
    hits = _failures[key]
    while hits and now - hits[0] > _FAIL_WINDOW:
        hits.popleft()
    if len(hits) >= _MAX_FAILS:
        return max(0, int(hits[-1] + _LOCK_SECONDS - now) + 1)
    return 0


def _login_hero():
    """Picture for the login page: your own photo if you add one, else the built-in scene."""
    for name in ("login-hero.jpg", "login-hero.jpeg", "login-hero.png", "login-hero.webp"):
        if os.path.isfile(os.path.join(app.static_folder, name)):
            return name, True
    return "login-scene.svg", False


def _page(mode, username=""):
    hero, hero_photo = _login_hero()
    return render_template("login.html", mode=mode, username=username,
                           recovery=session.pop("new_recovery", None),
                           hero=hero, hero_photo=hero_photo)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("wardrobe"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        key = _throttle_key(username)

        wait = _seconds_locked(key)
        if wait:
            flash(f"Too many attempts. Try again in {wait} seconds.", "error")
            return _page("login", username)

        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            _failures[key].append(time.time())
            flash("Username or password is incorrect. Check both and try again.", "error")
            return _page("login", username)

        _failures.pop(key, None)
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session.permanent = bool(request.form.get("remember"))      # stay signed in for 30 days
        return redirect(url_for("wardrobe"))

    return _page("login")


@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    error = None
    if len(username) < 3:
        error = "Username needs at least 3 characters."
    elif not all(ch.isalnum() or ch in "._-" for ch in username):
        error = "Username can use letters, numbers, dots, dashes and underscores."
    elif len(password) < 6:
        error = "Password needs at least 6 characters."
    elif password != confirm:
        error = "The two passwords don't match."

    code = _new_recovery_code()
    if error is None:
        try:
            db = get_db()
            db.execute(
                "INSERT INTO users (username, password_hash, recovery_hash) VALUES (?, ?, ?)",
                (username, generate_password_hash(password),
                 generate_password_hash(_norm_code(code))),
            )
            db.commit()
        except sqlite3.IntegrityError:
            error = "That username is taken. Pick another one."

    if error:
        flash(error, "error")
        return _page("register", username)

    session["new_recovery"] = code                       # shown once on the next page
    flash("Account created. Sign in to start your wardrobe.", "success")
    return redirect(url_for("login"))


@app.route("/forgot", methods=["POST"])
def forgot():
    username = request.form.get("username", "").strip().lower()
    code = request.form.get("code", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")
    key = _throttle_key(username)

    wait = _seconds_locked(key)
    if wait:
        flash(f"Too many attempts. Try again in {wait} seconds.", "error")
        return _page("forgot", username)
    if len(password) < 6:
        flash("New password needs at least 6 characters.", "error")
        return _page("forgot", username)
    if password != confirm:
        flash("The two passwords don't match.", "error")
        return _page("forgot", username)

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user is not None and not user["recovery_hash"]:
        flash("This account was created before recovery codes existed, so it can't be reset here.", "error")
        return _page("forgot", username)
    if user is None or not check_password_hash(user["recovery_hash"], _norm_code(code)):
        _failures[key].append(time.time())
        flash("That username and recovery code don't match.", "error")
        return _page("forgot", username)

    new_code = _new_recovery_code()                      # codes are single-use: issue a fresh one
    db.execute(
        "UPDATE users SET password_hash = ?, recovery_hash = ? WHERE id = ?",
        (generate_password_hash(password), generate_password_hash(_norm_code(new_code)), user["id"]),
    )
    db.commit()
    _failures.pop(key, None)
    session["new_recovery"] = new_code
    flash("Password changed. Sign in with your new password.", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You're logged out.", "success")
    return redirect(url_for("login"))


@app.route("/")
def home():
    return redirect(url_for("wardrobe" if "user_id" in session else "login"))


@app.route("/wardrobe")
@login_required
def wardrobe():
    items = get_db().execute(
        "SELECT * FROM clothes WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()
    return render_template(
        "wardrobe.html", items=items, categories=CATEGORIES,
        styles=STYLES, colours=COLOURS,
    )


def _allowed(filename):
    ext = secure_filename(filename).rsplit(".", 1)[-1].lower()
    return ext in ALLOWED_EXTENSIONS


@app.route("/wardrobe/analyze", methods=["POST"])
@login_required
def analyze_photo():
    """Live preview for the upload form: cut-out and detected colour."""
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify(error="Choose a photo first."), 400
    if not _allowed(photo.filename):
        return jsonify(error="Photos must be JPG, PNG or WebP."), 400
    try:
        result = process_photo(photo.stream, COLOURS)
    except PhotoError as exc:
        return jsonify(error=str(exc)), 400

    buf = io.BytesIO()
    result["image"].save(buf, "PNG")
    preview = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return jsonify(
        colour=result["colour"], hex=result["hex"], confidence=result["confidence"],
        cutout=result["cutout"], note=result["note"], preview=preview,
    )


@app.route("/wardrobe/add", methods=["POST"])
@login_required
def add_item():
    category = request.form.get("category", "")
    colour = request.form.get("colour", "auto")
    style = request.form.get("style", "")
    photo = request.files.get("photo")
    has_photo = bool(photo and photo.filename)

    if category not in CATEGORIES:
        flash("Pick a category for this item.", "error")
        return redirect(url_for("wardrobe"))
    if style not in STYLES:
        flash("Pick a style for this item.", "error")
        return redirect(url_for("wardrobe"))
    if colour != "auto" and colour not in COLOURS:
        flash("Pick a colour for this item.", "error")
        return redirect(url_for("wardrobe"))
    if colour == "auto" and not has_photo:
        flash("Upload a photo so the colour can be detected, or pick a colour.", "error")
        return redirect(url_for("wardrobe"))

    filename, detected, note = None, False, ""
    if has_photo:
        if not _allowed(photo.filename):
            flash("Photos must be JPG, PNG or WebP.", "error")
            return redirect(url_for("wardrobe"))
        try:
            result = process_photo(photo.stream, COLOURS)
        except PhotoError as exc:
            flash(str(exc), "error")
            return redirect(url_for("wardrobe"))
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"          # cut-outs are transparent PNGs
        result["image"].save(os.path.join(UPLOAD_FOLDER, filename), "PNG", optimize=True)
        if colour == "auto":
            colour, detected = result["colour"], True
        if not result["cutout"]:
            note = " " + result["note"]

    db = get_db()
    db.execute(
        "INSERT INTO clothes (user_id, category, colour, style, image) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], category, colour, style, filename),
    )
    db.commit()
    how = " Colour detected from your photo." if detected else ""
    flash(f"Added a {colour} {category} to your wardrobe.{how}{note}", "success")
    return redirect(url_for("wardrobe"))


@app.route("/wardrobe/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    db = get_db()
    item = db.execute(
        "SELECT * FROM clothes WHERE id = ? AND user_id = ?",
        (item_id, session["user_id"]),
    ).fetchone()
    if item is None:
        flash("That item isn't in your wardrobe.", "error")
        return redirect(url_for("wardrobe"))

    db.execute("DELETE FROM clothes WHERE id = ?", (item_id,))
    db.commit()
    if item["image"]:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, item["image"]))
        except OSError:
            pass
    flash("Item removed.", "success")
    return redirect(url_for("wardrobe"))


@app.errorhandler(413)
def too_large(_e):
    msg = "That photo is over 5 MB. Choose a smaller one."
    if request.path == url_for("analyze_photo"):
        return jsonify(error=msg), 413
    flash(msg, "error")
    return redirect(url_for("wardrobe"))


@app.route("/combinations")
@login_required
def combinations():
    db = get_db()
    uid = session["user_id"]
    shirts = db.execute(
        "SELECT * FROM clothes WHERE user_id = ? AND category = 'shirt'", (uid,)
    ).fetchall()
    trousers = db.execute(
        "SELECT * FROM clothes WHERE user_id = ? AND category = 'trousers'", (uid,)
    ).fetchall()
    shoes = db.execute(
        "SELECT * FROM clothes WHERE user_id = ? AND category = 'shoes'", (uid,)
    ).fetchall()
    return render_template(
        "combinations.html",
        outfits=find_combinations(shirts, trousers),
        shoes=shoes,
        colours=COLOURS,
    )


# ---------- Style assistant ----------
_chat_hits = defaultdict(deque)       # user id -> recent request times


def _chat_rate_ok(user_id, limit=15, window=60):
    now = time.time()
    hits = _chat_hits[user_id]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


@app.route("/assistant")
@login_required
def assistant():
    return render_template("assistant.html", configured=is_configured())


@app.route("/assistant/ask", methods=["POST"])
def assistant_ask():
    if "user_id" not in session:
        return jsonify(error="Your session ended. Please log in again."), 401
    data = request.get_json(silent=True) or {}
    uid = session["user_id"]
    if not _chat_rate_ok(uid):
        return jsonify(error="You're sending messages quickly. Wait a few seconds and try again."), 429

    wardrobe = ""
    if data.get("use_wardrobe", True):
        rows = get_db().execute(
            "SELECT category, colour, style FROM clothes WHERE user_id = ? ORDER BY id DESC LIMIT 80",
            (uid,),
        ).fetchall()
        wardrobe = wardrobe_summary(rows)
    try:
        reply, on_topic = ask(data.get("message", ""), data.get("history") or [], wardrobe)
    except AssistantError as exc:
        return jsonify(error=exc.message), exc.status
    return jsonify(reply=reply, off_topic=not on_topic)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)