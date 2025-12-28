from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)

DB = "notes.db"

def get_db():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    db = get_db()
    c = db.cursor()
    # ✅ UPDATED: Added reminder_count column
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        type TEXT, 
        ref_id INTEGER, 
        title TEXT, 
        preview TEXT, 
        color TEXT, 
        updated_at TEXT,
        reminder_count INTEGER DEFAULT 0
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, keywords TEXT, content TEXT, updated_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, tasks TEXT, updated_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS budgets (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, data TEXT, updated_at TEXT)")
    db.commit()
    db.close()

init_db()

# ========== HTML ROUTES (ALL 3 files) ==========
@app.route("/")
@app.route("/index.html")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/note.html")
def serve_note():
    return send_from_directory(FRONTEND_DIR, "note.html")

@app.route("/to-do.html")
def serve_todo():
    return send_from_directory(FRONTEND_DIR, "to-do.html")

@app.route("/budget.html")
def serve_budget():
    return send_from_directory(FRONTEND_DIR, "budget.html")


# ========== API ROUTES ==========
@app.route("/home")
def home():
    db = get_db()
    c = db.cursor()
    # ✅ UPDATED: Include reminder_count for Instagram badge
    c.execute("SELECT type, ref_id, title, preview, color, reminder_count FROM items ORDER BY updated_at DESC")
    rows = c.fetchall()
    db.close()
    return jsonify([{
        "type": r[0], 
        "id": r[1], 
        "title": r[2], 
        "preview": r[3], 
        "color": r[4],
        "reminderCount": r[5] or 0  # ✅ Instagram-style badge number
    } for r in rows])

# ---------- NOTES (UPDATED WITH REMINDER COUNT) ----------
@app.route("/note/<int:id>", methods=["GET"])
def get_note(id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT title, keywords, content FROM notes WHERE id=?", (id,))
    row = c.fetchone()
    db.close()
    if row:
        return jsonify({"title": row[0], "keywords": row[1], "content": row[2]})
    return jsonify({}), 404

@app.route("/note", methods=["POST"])
def save_note():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()
    db = get_db()
    c = db.cursor()
    
    # EXTRA SAFETY: Prevent duplicates for new notes
    if not d.get("id"):
        c.execute("DELETE FROM notes WHERE title=? AND content=?", (d["title"], d["content"][:100]))
        c.execute("DELETE FROM items WHERE type='note' AND title=? AND preview=?", (d["title"], d["content"][:60]))

    if d.get("id") and int(d.get("id")) > 0:
        # ✅ UPDATED: Save reminder_count
        c.execute("""UPDATE notes SET title=?, keywords=?, content=?, updated_at=? WHERE id=?""", 
                 (d["title"], d["keywords"], d["content"], now, d["id"]))
        c.execute("""UPDATE items SET title=?, preview=?, updated_at=?, reminder_count=? WHERE type='note' AND ref_id=?""", 
                 (d["title"], d["content"][:60], now, d.get("reminderCount", 0), d["id"]))
        db.commit()
        db.close()
        return jsonify({"ok": True, "id": d["id"]})
    else:
        # ✅ UPDATED: Save reminder_count for new notes
        c.execute("INSERT INTO notes VALUES(NULL,?,?,?,?)", (d["title"], d["keywords"], d["content"], now))
        nid = c.lastrowid
        c.execute("""INSERT INTO items VALUES(NULL,?,?,?,?,?,?,?)""", 
                 ("note", nid, d["title"], d["content"][:60], "#fff", now, d.get("reminderCount", 0)))
        db.commit()
        db.close()
        return jsonify({"ok": True, "id": nid})

@app.route("/note/<int:id>", methods=["DELETE"])
def delete_note(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM notes WHERE id=?", (id,))
    c.execute("DELETE FROM items WHERE type='note' AND ref_id=?", (id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})

# ---------- TODOS ----------
@app.route("/todo", methods=["POST"])
def save_todo():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()
    db = get_db()
    c = db.cursor()
    
    raw_tasks = d.get("tasks", "")
    preview = raw_tasks.replace('<li>', '').replace('</li>', '').replace('<span>', '').replace('<div>', '')[:60]
    if not preview.strip():
        preview = "No tasks"
    
    if d.get("id") and int(d.get("id")) > 0:
        # UPDATE existing todo
        c.execute(
            "UPDATE todos SET title=?, tasks=?, updated_at=? WHERE id=?",
            (d["title"], d["tasks"], now, d["id"])
        )
        c.execute(
            "UPDATE items SET title=?, preview=?, updated_at=? WHERE type='todo' AND ref_id=?",
            (d["title"], preview, now, d["id"])
        )
        db.commit()
        db.close()
        return jsonify({"ok": True, "id": d["id"]})
    else:
        # CREATE new todo
        c.execute(
            "INSERT INTO todos VALUES (NULL,?,?,?)",
            (d["title"], d["tasks"], now)
        )
        tid = c.lastrowid

        c.execute(
            "INSERT INTO items VALUES (NULL,?,?,?,?,?,?,?)",
            ("todo", tid, d["title"], preview, "#e8f1ff", now, 0)
        )

        db.commit()
        db.close()
        return jsonify({"ok": True, "id": tid})


@app.route("/todo/<int:id>")
def get_todo(id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT title, tasks FROM todos WHERE id=?", (id,))
    row = c.fetchone()
    db.close()
    return jsonify({"title": row[0], "tasks": row[1]}) if row else ({}, 404)

@app.route("/todo/<int:id>", methods=["DELETE"])
def delete_todo(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM todos WHERE id=?", (id,))
    c.execute("DELETE FROM items WHERE type='todo' AND ref_id=?", (id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})

# ---------- BUDGETS (FIXED) ----------
@app.route("/budget", methods=["POST"])
def save_budget():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()
    db = get_db()
    c = db.cursor()

    # Build preview
    try:
        data = json.loads(d.get("data", "[]"))
        preview_items = [item.get("item", "Item")[:20] for item in data[:2]]
        preview = " | ".join(preview_items)
        if preview:
            preview += f" | Total: ₹{d.get('total', 0)}"
        else:
            preview = "New budget"
    except:
        preview = "Budget items"

    # UPDATE existing budget
    if d.get("id") and int(d.get("id")) > 0:
        c.execute(
            "UPDATE budgets SET title=?, data=?, updated_at=? WHERE id=?",
            (d["title"], d["data"], now, d["id"])
        )
        c.execute(
            "UPDATE items SET title=?, preview=?, updated_at=? WHERE type='budget' AND ref_id=?",
            (d["title"], preview, now, d["id"])
        )
        db.commit()
        db.close()
        return jsonify({"ok": True, "id": d["id"]})

    # CREATE new budget
    else:
        c.execute(
            "INSERT INTO budgets VALUES (NULL,?,?,?)",
            (d["title"], d["data"], now)
        )
        bid = c.lastrowid

        c.execute(
            "INSERT INTO items VALUES (NULL,?,?,?,?,?,?,?)",
            ("budget", bid, d["title"], preview, "#fff4e6", now, 0)
        )

        db.commit()
        db.close()
        return jsonify({"ok": True, "id": bid})


@app.route("/budget/<int:id>", methods=["DELETE"])
def delete_budget(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM budgets WHERE id=?", (id,))
    c.execute("DELETE FROM items WHERE type='budget' AND ref_id=?", (id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
