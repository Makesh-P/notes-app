from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import json
from datetime import datetime
import os
import threading
import time
from pywebpush import webpush, WebPushException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: Ensure your 'frontend' folder is in the same directory as app.py
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

# --- VAPID KEYS ---
VAPID_PRIVATE_KEY = "ClduS3dHh3e3Iojg9Yna-LDju_2vMOHPEMVWUsg-ATE"
VAPID_PUBLIC_KEY = "BCjE7S3Qg5wOKbwx1Sirc5ElWzhKFjNMfEWUQskfdwNoyQg026mlf6e6-1TvAod_cwaN1oh-Unr6klWxruhi-IY"
VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        id SERIAL PRIMARY KEY, type TEXT, ref_id INTEGER, title TEXT, 
        preview TEXT, color TEXT, updated_at TEXT, reminder_count INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id SERIAL PRIMARY KEY, title TEXT, keywords TEXT, content TEXT, updated_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS todos (
        id SERIAL PRIMARY KEY, title TEXT, tasks TEXT, updated_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS budgets (
        id SERIAL PRIMARY KEY, title TEXT, data TEXT, updated_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS reminders (
        id SERIAL PRIMARY KEY, note_id INTEGER, label TEXT, remind_at TIMESTAMP, is_sent BOOLEAN DEFAULT FALSE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY, sub_data TEXT
    )""")
    db.commit()
    db.close()

init_db()

# ---------------- STATIC ROUTES ----------------
@app.route("/")
@app.route("/index.html")
def index(): return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/note.html")
def note_page(): return send_from_directory(FRONTEND_DIR, "note.html")

@app.route("/to-do.html")
def todo_page(): return send_from_directory(FRONTEND_DIR, "to-do.html")

@app.route("/budget.html")
def budget_page(): return send_from_directory(FRONTEND_DIR, "budget.html")

# FIXED: Service Worker path usually needs to be served from root or same folder
@app.route("/sw.js")
def sw(): 
    # If sw.js is inside the frontend folder, use this:
    return send_from_directory(FRONTEND_DIR, "sw.js")

# ---------------- REMINDER ROUTES ----------------
@app.route("/subscribe", methods=["POST"])
def subscribe():
    sub_data = json.dumps(request.get_json())
    db = get_db()
    c = db.cursor()
    c.execute("SELECT id FROM subscriptions WHERE sub_data = %s", (sub_data,))
    if not c.fetchone():
        c.execute("INSERT INTO subscriptions (sub_data) VALUES (%s)", (sub_data,))
        db.commit()
    db.close()
    return jsonify({"status": "success"})

@app.route("/reminders/<int:note_id>", methods=["GET"])
def get_reminders(note_id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT id, label, remind_at FROM reminders WHERE note_id = %s AND is_sent = FALSE", (note_id,))
    rows = c.fetchall()
    db.close()
    return jsonify([{"id": r[0], "label": r[1], "time": r[2].isoformat()} for r in rows])

@app.route("/reminders", methods=["POST"])
def add_reminder():
    d = request.get_json()
    db = get_db()
    c = db.cursor()
    c.execute("INSERT INTO reminders (note_id, label, remind_at) VALUES (%s, %s, %s)", 
              (d['noteId'], d['label'], d['time']))
    db.commit()
    db.close()
    return jsonify({"status": "success"})

@app.route("/reminders/<int:id>", methods=["DELETE"])
def delete_reminder(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM reminders WHERE id = %s", (id,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})

# ---------------- DATA ROUTES ----------------
@app.route("/home")
def home():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT type, ref_id, title, preview, color, reminder_count FROM items ORDER BY updated_at DESC")
    rows = c.fetchall()
    db.close()
    return jsonify([{"type":r[0],"id":r[1],"title":r[2],"preview":r[3],"color":r[4],"reminderCount":r[5]or 0} for r in rows])

@app.route("/note/<int:id>", methods=["GET"])
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
        c.execute("UPDATE notes SET title=%s, keywords=%s, content=%s, updated_at=%s WHERE id=%s", 
                  (d["title"], d["keywords"], d["content"], now, d["id"]))
        c.execute("UPDATE items SET title=%s, preview=%s, updated_at=%s WHERE type='note' AND ref_id=%s", 
                  (d["title"], d["content"][:60], now, d["id"]))
        nid = d["id"]
    else:
        c.execute("INSERT INTO notes (title, keywords, content, updated_at) VALUES (%s,%s,%s,%s) RETURNING id", 
                  (d["title"], d["keywords"], d["content"], now))
        nid = c.fetchone()[0]
        c.execute("INSERT INTO items (type, ref_id, title, preview, color, updated_at) VALUES ('note',%s,%s,%s,'#fff',%s)", 
                  (nid, d["title"], d["content"][:60], now))
    db.commit()
    db.close()
    return jsonify({"ok": True, "id": nid})

# FIXED: Added missing "/" in route
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
        c.execute("UPDATE todos SET title=%s, tasks=%s, updated_at=%s WHERE id=%s", (d["title"], d["tasks"], now, d["id"]))
        c.execute("UPDATE items SET title=%s, preview=%s, updated_at=%s WHERE type='todo' AND ref_id=%s", (d["title"], preview, now, d["id"]))
        db.commit()
        db.close()
        return jsonify({"ok": True, "id": d["id"]})
    c.execute("INSERT INTO todos (title, tasks, updated_at) VALUES (%s,%s,%s) RETURNING id", (d["title"], d["tasks"], now))
    tid = c.fetchone()[0]
    c.execute("INSERT INTO items (type, ref_id, title, preview, color, updated_at) VALUES ('todo',%s,%s,%s,'#e8f1ff',%s)", (tid, d["title"], preview, now))
    db.commit()
    db.close()
    return jsonify({"ok": True, "id": tid})

# FIXED: Added missing "/" in route
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
        c.execute("UPDATE budgets SET title=%s, data=%s, updated_at=%s WHERE id=%s", (d["title"], d["data"], now, d["id"]))
        c.execute("UPDATE items SET title=%s, preview=%s, updated_at=%s WHERE type='budget' AND ref_id=%s", (d["title"], preview, now, d["id"]))
        db.commit()
        db.close()
        return jsonify({"ok": True})
    c.execute("INSERT INTO budgets (title, data, updated_at) VALUES (%s,%s,%s) RETURNING id", (d["title"], d["data"], now))
    bid = c.fetchone()[0]
    c.execute("INSERT INTO items (type, ref_id, title, preview, color, updated_at) VALUES ('budget',%s,%s,%s,'#fff4e6',%s)", (bid, d["title"], preview, now))
    db.commit()
    db.close()
    return jsonify({"ok": True, "id": bid})

# ---------------- BACKGROUND SCHEDULER ----------------
def check_reminders():
    while True:
        try:
            db = get_db()
            c = db.cursor()

            c.execute("""
                SELECT id, note_id, label
                FROM reminders
                WHERE remind_at <= CURRENT_TIMESTAMP
                AND is_sent = FALSE
            """)
            reminders = c.fetchall()

            if reminders:
                c.execute("SELECT sub_data FROM subscriptions")
                subs = c.fetchall()

                for rid, note_id, label in reminders:
                    payload = json.dumps({
                        "title": "📝 Note Reminder",
                        "body": label,
                        "url": f"/note.html?id={note_id}"
                    })

                    for sub in subs:
                        try:
                            webpush(
                                subscription_info=json.loads(sub[0]),
                                data=payload,
                                vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS
                            )
                        except Exception as e:
                            print("Push error:", e)

                    c.execute(
                        "UPDATE reminders SET is_sent = TRUE WHERE id = %s",
                        (rid,)
                    )

                db.commit()
            db.close()
        except Exception as e:
            print("Reminder loop error:", e)

        time.sleep(20)

    while True:
        try:
            db = get_db()
            c = db.cursor()
            c.execute("""
                SELECT id, note_id, label 
                FROM reminders 
                WHERE remind_at <= CURRENT_TIMESTAMP AND is_sent = FALSE
            """)
            due_reminders = c.fetchall()

            if due_reminders:
                c.execute("SELECT sub_data FROM subscriptions")
                subs = c.fetchall()

                for reminder in due_reminders:
                    rem_id, note_id, label = reminder
                    payload = json.dumps({
                        "title": "📝 Note Reminder",
                        "body": label,
                        "url": f"/note.html?id={note_id}"
                    })

                    for sub in subs:
                        try:
                            webpush(
                                subscription_info=json.loads(sub[0]),
                                data=payload,
                                vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS
                            )
                        except WebPushException as ex:
                            print(f"WebPush error: {ex}")
                        except Exception as e:
                            print(f"Generic Push error: {e}")

                    c.execute("UPDATE reminders SET is_sent = TRUE WHERE id = %s", (rem_id,))
                db.commit()
            db.close()
        except Exception as e:
            print(f"Scheduler loop error: {e}")
        time.sleep(20)  # Check every 20 seconds

    while True:
        try:
            db = get_db()
            c = db.cursor()
            # PostgreSQL: use CURRENT_TIMESTAMP to be timezone-safe
            c.execute("""
                SELECT id, note_id, label 
                FROM reminders 
                WHERE remind_at <= CURRENT_TIMESTAMP AND is_sent = FALSE
            """)
            due_reminders = c.fetchall()

            if due_reminders:
                c.execute("SELECT sub_data FROM subscriptions")
                subs = c.fetchall()

                for reminder in due_reminders:
                    rem_id, note_id, label = reminder
                    payload = json.dumps({
                        "title": "📝 Note Reminder",
                        "body": label,
                        "url": f"/note.html?id={note_id}"
                    })

                    for sub in subs:
                        try:
                            webpush(
                                subscription_info=json.loads(sub[0]),
                                data=payload,
                                vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS
                            )
                        except WebPushException as ex:
                            print(f"WebPush error: {ex}")
                        except Exception as e:
                            print(f"Generic Push error: {e}")

                    c.execute("UPDATE reminders SET is_sent = TRUE WHERE id = %s", (rem_id,))
                    db.commit()
            db.close()
        except Exception as e:
            print(f"Scheduler loop error: {e}")
        time.sleep(20) # Checked slightly faster
    while True:
        try:
            db = get_db()
            c = db.cursor()
            # PostgreSQL requires NOW() at UTC or specific timezone depending on your input
            c.execute("SELECT id, note_id, label FROM reminders WHERE remind_at <= CURRENT_TIMESTAMP AND is_sent = FALSE")
            due_reminders = c.fetchall()
            if due_reminders:
                c.execute("SELECT sub_data FROM subscriptions")
                subs = c.fetchall()
                for reminder in due_reminders:
                    rem_id, note_id, label = reminder
                    payload = json.dumps({
                        "title": "📝 Note Reminder",
                        "body": label,
                        "url": f"/note.html?id={note_id}"
                    })
                    for sub in subs:
                        try:
                            webpush(
                                subscription_info=json.loads(sub[0]),
                                data=payload,
                                vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS
                            )
                        except Exception as e:
                            print(f"Push failed: {e}")
                    c.execute("UPDATE reminders SET is_sent = TRUE WHERE id = %s", (rem_id,))
                    db.commit()
            db.close()
        except Exception as e:
            print(f"Scheduler error: {e}")
        time.sleep(30)

threading.Thread(target=check_reminders, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)