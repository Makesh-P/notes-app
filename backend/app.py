from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
from datetime import datetime
import os
import threading
import time
from pywebpush import webpush
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)

DB_FILE = "notes.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


# --- VAPID KEYS ---
VAPID_PRIVATE_KEY = "ClduS3dHh3e3Iojg9Yna-LDju_2vMOHPEMVWUsg-ATE"
VAPID_PUBLIC_KEY = "BCjE7S3Qg5wOKbwx1Sirc5ElWzhKFjNMfEWUQskfdwNoyQg026mlf6e6-1TvAod_cwaN1oh-Unr6klWxruhi-IY"
VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}


def init_db():
    db = get_db()
    c = db.cursor()

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

    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        keywords TEXT,
        content TEXT,
        updated_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        tasks TEXT,
        updated_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        data TEXT,
        updated_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER,
        label TEXT,
        remind_at TEXT,
        is_sent INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_data TEXT
    )""")

    db.commit()
    db.close()


init_db()

# ---------------- STATIC ROUTES ----------------
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


@app.route("/sw.js")
def sw():
    return send_from_directory(FRONTEND_DIR, "sw.js")


# ---------------- REMINDER ROUTES ----------------
@app.route("/subscribe", methods=["POST"])
def subscribe():
    sub_data = json.dumps(request.get_json())

    db = get_db()
    c = db.cursor()

    c.execute("SELECT id FROM subscriptions WHERE sub_data = ?", (sub_data,))
    if not c.fetchone():
        c.execute("INSERT INTO subscriptions (sub_data) VALUES (?)", (sub_data,))
        db.commit()

    db.close()
    return jsonify({"status": "success"})


@app.route("/reminders/<int:note_id>", methods=["GET"])
def get_reminders(note_id):
    db = get_db()
    c = db.cursor()

    c.execute(
        "SELECT id, label, remind_at FROM reminders WHERE note_id = ? AND is_sent = 0",
        (note_id,),
    )

    rows = c.fetchall()
    db.close()

    return jsonify(
        [{"id": r["id"], "label": r["label"], "time": r["remind_at"]} for r in rows]
    )


@app.route("/reminders", methods=["POST"])
def add_reminder():
    d = request.get_json()

    db = get_db()
    c = db.cursor()

    c.execute(
        "INSERT INTO reminders (note_id, label, remind_at) VALUES (?, ?, ?)",
        (d["noteId"], d["label"], d["time"]),
    )

    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/reminders/<int:id>", methods=["DELETE"])
def delete_reminder(id):
    db = get_db()
    c = db.cursor()

    c.execute("DELETE FROM reminders WHERE id = ?", (id,))
    db.commit()
    db.close()

    return jsonify({"status": "success"})


# ---------------- HOME ROUTE ----------------
@app.route("/home")
def home():
    db = get_db()
    c = db.cursor()

    c.execute(
        "SELECT type, ref_id, title, preview, color, reminder_count FROM items ORDER BY updated_at DESC"
    )

    rows = c.fetchall()
    db.close()

    return jsonify(
        [
            {
                "type": r["type"],
                "id": r["ref_id"],
                "title": r["title"],
                "preview": r["preview"],
                "color": r["color"],
                "reminderCount": r["reminder_count"] or 0,
            }
            for r in rows
        ]
    )


# ---------------- NOTE ROUTES ----------------
@app.route("/note/<int:id>", methods=["GET"])
def get_note(id):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT title, keywords, content FROM notes WHERE id=?", (id,))
    row = c.fetchone()
    db.close()

    if row:
        return jsonify(
            {"title": row["title"], "keywords": row["keywords"], "content": row["content"]}
        )
    return ({}, 404)


@app.route("/note", methods=["POST"])
def save_note():
    d = request.get_json(force=True)
    now = datetime.now().isoformat()

    db = get_db()
    c = db.cursor()

    if d.get("id"):
        c.execute(
            "UPDATE notes SET title=?, keywords=?, content=?, updated_at=? WHERE id=?",
            (d["title"], d["keywords"], d["content"], now, d["id"]),
        )

        c.execute(
            "UPDATE items SET title=?, preview=?, updated_at=? WHERE type='note' AND ref_id=?",
            (d["title"], d["content"][:60], now, d["id"]),
        )

        nid = d["id"]

    else:
        c.execute(
            "INSERT INTO notes (title, keywords, content, updated_at) VALUES (?, ?, ?, ?)",
            (d["title"], d["keywords"], d["content"], now),
        )
        nid = c.lastrowid

        c.execute(
            "INSERT INTO items (type, ref_id, title, preview, color, updated_at) VALUES ('note', ?, ?, ?, '#fff', ?)",
            (nid, d["title"], d["content"][:60], now),
        )

    db.commit()
    db.close()
    return jsonify({"ok": True, "id": nid})


# ---------------- BACKGROUND REMINDER CHECK ----------------
def check_reminders():
    while True:
        try:
            db = get_db()
            c = db.cursor()

            now = datetime.now().isoformat()

            c.execute(
                "SELECT id, note_id, label FROM reminders WHERE remind_at <= ? AND is_sent = 0",
                (now,),
            )

            due = c.fetchall()

            if due:
                c.execute("SELECT sub_data FROM subscriptions")
                subs = c.fetchall()

                for reminder in due:
                    rid, note_id, label = reminder

                    payload = json.dumps(
                        {
                            "title": "📝 Note Reminder",
                            "body": label,
                            "url": f"/note.html?id={note_id}",
                        }
                    )

                    for sub in subs:
                        try:
                            webpush(
                                subscription_info=json.loads(sub["sub_data"]),
                                data=payload,
                                vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS,
                            )
                        except Exception as e:
                            print("Push error:", e)

                    c.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (rid,))

                db.commit()

            db.close()

        except Exception as e:
            print("Reminder loop error:", e)

        time.sleep(20)


threading.Thread(target=check_reminders, daemon=True).start()


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
