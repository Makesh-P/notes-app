from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import json
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )

def init_db():
    db = get_db()
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id SERIAL PRIMARY KEY,
        type TEXT,
        ref_id INTEGER,
        title TEXT,
        preview TEXT,
        color TEXT,
        updated_at TEXT,
        reminder_count INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id SERIAL PRIMARY KEY,
        title TEXT,
        keywords TEXT,
        content TEXT,
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS todos (
        id SERIAL PRIMARY KEY,
        title TEXT,
        tasks TEXT,
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id SERIAL PRIMARY KEY,
        title TEXT,
        data TEXT,
        updated_at TEXT
    )
    """)

    db.commit()
    db.close()

init_db()

# ---------------- HTML ROUTES ----------------
@app.route("/")
@app.route("/index.html")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/note.html")
def note_page():
    return send_from_directory(FRONTEND_DIR, "note.html")

@app.route("/to-do.html")
def todo_page():
    return send_from_directory(FRONTEND_DIR, "to-do.html")

@app.route("/budget.html")
def budget_page():
    return send_from_directory(FRONTEND_DIR, "budget.html")

# ---------------- HOME ----------------
@app.route("/home")
def home():
    db = get_db()
    c = db.cursor()
    c.execute("""
        SELECT type, ref_id, title, preview, color, reminder_count
        FROM items
        ORDER BY updated_at DESC
    """)
    rows = c.fetchall()
    db.close()

    return jsonify([{
        "type": r[0],
        "id": r[1],
        "title": r[2],
        "preview": r[3],
        "color": r[4],
        "reminderCount": r[5] or 0
    } for r in rows])

# ---------------- NOTES ----------------
@app.route("/note/<int:id>")
def get_note(id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT title, keywords, content FROM notes WHERE id=%s", (id,))
    row = c.fetchone()
    db.close()
    return jsonify({"title": row[0], "keywords": row[1], "content": row[2]}) if row else ({}, 404)

@app.route("/note", methods=["POST"])
def save_note():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()
    db = get_db()
    c = db.cursor()

    if d.get("id"):
        c.execute("""
            UPDATE notes SET title=%s, keywords=%s, content=%s, updated_at=%s WHERE id=%s
        """, (d["title"], d["keywords"], d["content"], now, d["id"]))

        c.execute("""
            UPDATE items SET title=%s, preview=%s, updated_at=%s WHERE type='note' AND ref_id=%s
        """, (d["title"], d["content"][:60], now, d["id"]))

        db.commit()
        db.close()
        return jsonify({"ok": True, "id": d["id"]})

    c.execute("""
        INSERT INTO notes (title, keywords, content, updated_at)
        VALUES (%s,%s,%s,%s) RETURNING id
    """, (d["title"], d["keywords"], d["content"], now))

    nid = c.fetchone()[0]

    c.execute("""
        INSERT INTO items (type, ref_id, title, preview, color, updated_at)
        VALUES ('note',%s,%s,%s,'#fff',%s)
    """, (nid, d["title"], d["content"][:60], now))

    db.commit()
    db.close()
    return jsonify({"ok": True, "id": nid})

# ---------------- TODOS ----------------
@app.route("/todo/<int:id>")
def get_todo(id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT title, tasks FROM todos WHERE id=%s", (id,))
    row = c.fetchone()
    db.close()
    return jsonify({"title": row[0], "tasks": row[1]}) if row else ({}, 404)

@app.route("/todo", methods=["POST"])
def save_todo():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()
    preview = (d.get("tasks") or "").replace("<li>", "").replace("</li>", "")[:60] or "No tasks"

    db = get_db()
    c = db.cursor()

    if d.get("id"):
        c.execute("""
            UPDATE todos SET title=%s, tasks=%s, updated_at=%s WHERE id=%s
        """, (d["title"], d["tasks"], now, d["id"]))

        c.execute("""
            UPDATE items SET title=%s, preview=%s, updated_at=%s WHERE type='todo' AND ref_id=%s
        """, (d["title"], preview, now, d["id"]))

        db.commit()
        db.close()
        return jsonify({"ok": True, "id": d["id"]})

    c.execute("""
        INSERT INTO todos (title, tasks, updated_at)
        VALUES (%s,%s,%s) RETURNING id
    """, (d["title"], d["tasks"], now))

    tid = c.fetchone()[0]

    c.execute("""
        INSERT INTO items (type, ref_id, title, preview, color, updated_at)
        VALUES ('todo',%s,%s,%s,'#e8f1ff',%s)
    """, (tid, d["title"], preview, now))

    db.commit()
    db.close()
    return jsonify({"ok": True, "id": tid})

# ---------------- BUDGETS ----------------
@app.route("/budget/<int:id>")
def get_budget(id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT title, data FROM budgets WHERE id=%s", (id,))
    row = c.fetchone()
    db.close()
    return jsonify({"title": row[0], "data": row[1]}) if row else ({}, 404)

@app.route("/budget", methods=["POST"])
def save_budget():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()

    try:
        items = json.loads(d["data"]) if d["data"] else []
        preview = " | ".join(i["item"][:15] for i in items[:2]) or "Budget"
    except:
        preview = "Budget"

    db = get_db()
    c = db.cursor()

    if d.get("id"):
        c.execute("""
            UPDATE budgets SET title=%s, data=%s, updated_at=%s WHERE id=%s
        """, (d["title"], d["data"], now, d["id"]))

        c.execute("""
            UPDATE items SET title=%s, preview=%s, updated_at=%s WHERE type='budget' AND ref_id=%s
        """, (d["title"], preview, now, d["id"]))

        db.commit()
        db.close()
        return jsonify({"ok": True})

    c.execute("""
        INSERT INTO budgets (title, data, updated_at)
        VALUES (%s,%s,%s) RETURNING id
    """, (d["title"], d["data"], now))

    bid = c.fetchone()[0]

    c.execute("""
        INSERT INTO items (type, ref_id, title, preview, color, updated_at)
        VALUES ('budget',%s,%s,%s,'#fff4e6',%s)
    """, (bid, d["title"], preview, now))

    db.commit()
    db.close()
    return jsonify({"ok": True, "id": bid})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
