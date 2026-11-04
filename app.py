import os
import sqlite3
import uuid
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from colour_rules import find_combinations

app = Flask(__name__)
# Set this in your environment: export SECRET_KEY="a-long-random-string"
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DATABASE = "colourfit.db"

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
                   password_hash TEXT NOT NULL
               )"""
        )
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
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("wardrobe"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Username or password is incorrect. Check both and try again.", "error")
            return render_template("login.html", mode="login", username=username)

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("wardrobe"))

    return render_template("login.html", mode="login", username="")


@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    error = None
    if len(username) < 3:
        error = "Username needs at least 3 characters."
    elif len(password) < 6:
        error = "Password needs at least 6 characters."
    elif password != confirm:
        error = "The two passwords don't match."

    if error is None:
        try:
            db = get_db()
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            db.commit()
        except sqlite3.IntegrityError:
            error = "That username is taken. Pick another one."

    if error:
        flash(error, "error")
        return render_template("login.html", mode="register", username=username)

    flash("Account created. Log in to start your wardrobe.", "success")
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


@app.route("/wardrobe/add", methods=["POST"])
@login_required
def add_item():
    category = request.form.get("category", "")
    colour = request.form.get("colour", "")
    style = request.form.get("style", "")
    photo = request.files.get("photo")

    if category not in CATEGORIES:
        flash("Pick a category for this item.", "error")
        return redirect(url_for("wardrobe"))
    if colour not in COLOURS:
        flash("Pick a colour for this item.", "error")
        return redirect(url_for("wardrobe"))
    if style not in STYLES:
        flash("Pick a style for this item.", "error")
        return redirect(url_for("wardrobe"))

    filename = None
    if photo and photo.filename:
        ext = secure_filename(photo.filename).rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            flash("Photos must be JPG, PNG or WebP.", "error")
            return redirect(url_for("wardrobe"))
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{ext}"
        photo.save(os.path.join(UPLOAD_FOLDER, filename))

    db = get_db()
    db.execute(
        "INSERT INTO clothes (user_id, category, colour, style, image) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], category, colour, style, filename),
    )
    db.commit()
    flash(f"Added a {colour} {category} to your wardrobe.", "success")
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
    flash("That photo is over 5 MB. Choose a smaller one.", "error")
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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
