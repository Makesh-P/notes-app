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
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

# --- VAPID KEYS FOR PUSH NOTIFICATIONS ---
# In production, store these in environment variables
VAPID_PRIVATE_KEY = "ClduS3dHh3e3Iojg9Yna-LDju_2vMOHPEMVWUsg-ATE"
VAPID_PUBLIC_KEY = "BCjE7S3Qg5wOKbwx1Sirc5ElWzhKFjNMfEWUQskfdwNoyQg026mlf6e6-1TvAod_cwaN1oh-Unr6klWxruhi-IY"
# EMAIL for VAPID identification
VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    db = get_db()
    c = db.cursor()

    # Existing tables
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

    # --- NEW TABLES FOR BACKGROUND REMINDERS ---
    c.execute("""CREATE TABLE IF NOT EXISTS reminders (
        id SERIAL PRIMARY KEY,
        note_id INTEGER,
        label TEXT,
        remind_at TIMESTAMP,
        is_sent BOOLEAN DEFAULT FALSE
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY,
        sub_data TEXT
    )""")

    db.commit()
    db.close()

init_db()

# ---------------- EXISTING HTML ROUTES ----------------
@app.route("/")
@app.route("/index.html")
def index(): return send_from_directory(FRONTEND_DIR, "index.html")
@app.route("/note.html")
def note_page(): return send_from_directory(FRONTEND_DIR, "note.html")
@app.route("/to-do.html")
def todo_page(): return send_from_directory(FRONTEND_DIR, "to-do.html")
@app.route("/budget.html")
def budget_page(): return send_from_directory(FRONTEND_DIR, "budget.html")
@app.route("/sw.js")
def sw(): return send_from_directory(FRONTEND_DIR, "../sw.js") # Adjust path if needed

# ---------------- NEW REMINDER ROUTES ----------------

# 1. Save Browser Subscription
@app.route("/subscribe", methods=["POST"])
def subscribe():
    sub_data = json.dumps(request.get_json())
    db = get_db()
    c = db.cursor()
    # Check if exists to avoid duplicates (simplified)
    c.execute("SELECT id FROM subscriptions WHERE sub_data = %s", (sub_data,))
    if not c.fetchone():
        c.execute("INSERT INTO subscriptions (sub_data) VALUES (%s)", (sub_data,))
        db.commit()
    db.close()
    return jsonify({"status": "success"})

# 2. Get Reminders for a Note
@app.route("/reminders/<int:note_id>", methods=["GET"])
def get_reminders(note_id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT id, label, remind_at FROM reminders WHERE note_id = %s AND is_sent = FALSE", (note_id,))
    rows = c.fetchall()
    db.close()
    return jsonify([{"id": r[0], "label": r[1], "time": r[2].isoformat()} for r in rows])

# 3. Add Reminder
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

# 4. Delete Reminder
@app.route("/reminders/<int:id>", methods=["DELETE"])
def delete_reminder(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM reminders WHERE id = %s", (id,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})

# ---------------- EXISTING DATA ROUTES ----------------
@app.route("/home")
def home():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT type, ref_id, title, preview, color, reminder_count FROM items ORDER BY updated_at DESC")
    rows = c.fetchall()
    db.close()
    return jsonify([{"type":r[0],"id":r[1],"title":r[2],"preview":r[3],"color":r[4],"reminderCount":r[5]or 0} for r in rows])

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

# (Include your TODO and BUDGET routes here unchanged...)

# ---------------- BACKGROUND SCHEDULER (THE ENGINE) ----------------
def check_reminders():
    """ Runs in background, checks DB, pushes notifications """
    while True:
        try:
            db = get_db()
            c = db.cursor()
            
            # Find due reminders
            c.execute("""
                SELECT id, note_id, label 
                FROM reminders 
                WHERE remind_at <= NOW() AND is_sent = FALSE
            """)
            due_reminders = c.fetchall()

            if due_reminders:
                # Get all subscriptions (In real app, filter by user_id)
                c.execute("SELECT sub_data FROM subscriptions")
                subs = c.fetchall()

                for reminder in due_reminders:
                    rem_id, note_id, label = reminder
                    
                    # Prepare payload
                    payload = json.dumps({
                        "title": "📝 Note Reminder",
                        "body": label,
                        "url": f"note.html?id={note_id}"
                    })

                    # Send to ALL subscribed browsers
                    for sub in subs:
                        try:
                            sub_info = json.loads(sub[0])
                            webpush(
                                subscription_info=sub_info,
                                data=payload,
                                vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS
                            )
                        except WebPushException as ex:
                            # Subscription is dead/expired
                            print("Push failed: {}", ex)
                        except Exception as e:
                            print(e)

                    # Mark as sent
                    c.execute("UPDATE reminders SET is_sent = TRUE WHERE id = %s", (rem_id,))
                    db.commit()
            
            db.close()
        except Exception as e:
            print("Scheduler error:", e)
        
        # Check every 30 seconds
        time.sleep(30)

# Start background thread
threading.Thread(target=check_reminders, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)