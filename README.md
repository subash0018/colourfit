# Colour-Fit

Wardrobe manager with automatic colour detection, background removal, outfit matching, an avatar try-on and an AI style assistant (Google Gemini).

## Run in VS Code

1. Install Python 3.10 or newer (python.org). On Windows, tick "Add Python to PATH".
2. In VS Code: File > Open Folder, choose this `colour-fit` folder.
3. Open the terminal (Ctrl + `) and create a virtual environment:

   Windows:
   ```
   py -m venv .venv
   .venv\Scripts\activate
   ```
   Mac / Linux:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   If VS Code asks to use the new environment, click Yes.
4. Install the packages:
   ```
   pip install -r requirements.txt
   ```
5. Start the app:
   ```
   python app.py
   ```
   (or press F5 and pick "Colour-Fit (Flask)")
6. Open http://127.0.0.1:5000 in your browser.

Optional: set your own secret key first.
- Windows PowerShell: `$env:SECRET_KEY="any-long-random-text"`
- Mac / Linux: `export SECRET_KEY="any-long-random-text"`

Stop the app with Ctrl + C.

## Database

Colour-Fit stores accounts and clothes in a SQLite file, `colourfit.db`, next to `app.py`. The app creates it automatically on first run, so you normally do nothing. To create it yourself:

```
python init_db.py            create the tables (safe to run again)
python init_db.py --demo     also add a demo account: username demo, password demo123, with sample clothes
python init_db.py --reset    delete everything and start fresh (asks you to confirm)
```

Tables (see `schema.sql`):
- `users`: id, username, password_hash, recovery_hash
- `clothes`: id, user_id, category, colour, style, image

To look inside the file, open it with DB Browser for SQLite (free) or the "SQLite Viewer" extension in VS Code. To back it up, copy `colourfit.db`, and copy the `static/uploads` folder too, because the photos are stored there.

## Accounts and sign-in

- **Sign up** creates an account and shows a one-time **recovery code**. Save it.
- **Remember me** keeps you signed in for 30 days on that browser.
- **Forgot password?** asks for your username and recovery code, then lets you set a new password and gives you a fresh recovery code.
- Five wrong attempts in a row pause sign-in for a minute.
- Passwords and recovery codes are stored hashed, never as plain text.

## Login page picture

The left side of the login page shows `static/login-scene.svg`, an illustration of a person choosing clothes from a rack.

To use your own photo instead, save it in the `static` folder as `login-hero.jpg` (or `.png`, `.webp`) and refresh the page. A blue tint is added so it matches the page. Delete the file to go back to the illustration. Use a photo you have the right to use (for example from Unsplash or Pexels, or your own).

## Style assistant (Gemini)

The **Style assistant** page answers questions about dressing and outfit pairing. It needs a free Gemini API key.

1. Get a key at https://aistudio.google.com/apikey
2. Copy `.env.example` to a new file named `.env` (same folder as `app.py`) and paste your key:
   ```
   GEMINI_API_KEY=your-key-here
   ```
3. Restart the app (`python app.py`). The assistant page now works.

Notes:
- The key stays on the server and is never sent to the browser. Keep `.env` private (it is already in `.gitignore`).
- Tick "Use my wardrobe" on the page so answers use the clothes you have added.
- If Google renames its models and you see "model not found", set `GEMINI_MODEL` in `.env` to a current model name from AI Studio (several names can be separated by commas).
- Without a key, the rest of the app works normally and the assistant page shows a setup message.

## Project structure

```
colour-fit/
├── app.py               Flask app: login, wardrobe, uploads, combinations
├── colour_rules.py      Colour matching rules and scores
├── garment_image.py     Background removal and automatic colour detection
├── init_db.py           Creates the database (python init_db.py)
├── schema.sql           The database tables, for reference
├── colourfit.db         The SQLite database (created automatically if missing)
├── assistant.py         Gemini style assistant
├── .env.example         Copy to .env and add your Gemini key
├── requirements.txt
├── static/
│   ├── site.css         Shared styles
│   ├── login-scene.svg  Login page picture (person choosing clothes from a rack)
│   └── uploads/         Saved clothing photos (created automatically)
└── templates/
    ├── _header.html     Top bar
    ├── _icons.html      Icons
    ├── assistant.html
    ├── login.html
    ├── wardrobe.html
    └── combinations.html
```

The database file `colourfit.db` is created on first run.

## Troubleshooting

- `python` not recognised: use `py` on Windows, or `python3` on Mac / Linux.
- `No module named flask` (or PIL / numpy): activate the virtual environment, then run `pip install -r requirements.txt`.
- `TemplateNotFound`: the HTML files must stay inside the `templates` folder.
- Old database errors after updating: stop the app and delete `colourfit.db`, then start again (this removes saved accounts and items).
- Photos that keep their background: use one item on a plain background, or install `rembg`.