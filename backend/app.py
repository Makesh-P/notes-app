from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS notes(
      id SERIAL PRIMARY KEY,
      title TEXT,
      keywords TEXT,
      content TEXT,
      updated_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS items(
      id SERIAL PRIMARY KEY,
      type TEXT,
      ref_id INTEGER,
      title TEXT,
      preview TEXT,
      color TEXT,
      updated_at TEXT
    )
    """)
    db.commit()
    db.close()

init_db()

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR,"index.html")

@app.route("/note.html")
def note_page():
    return send_from_directory(FRONTEND_DIR,"note.html")

@app.route("/home")
def home():
    db=get_db()
    c=db.cursor()
    c.execute("SELECT type,ref_id,title,preview,color FROM items ORDER BY updated_at DESC")
    rows=c.fetchall()
    db.close()
    return jsonify([{
        "type":r[0],"id":r[1],"title":r[2],"preview":r[3],"color":r[4]
    } for r in rows])

@app.route("/note/<int:id>")
def get_note(id):
    db=get_db()
    c=db.cursor()
    c.execute("SELECT title,keywords,content FROM notes WHERE id=%s",(id,))
    r=c.fetchone()
    db.close()
    return jsonify({"title":r[0],"keywords":r[1],"content":r[2]}) if r else ({},404)

@app.route("/note",methods=["POST"])
def save_note():
    d=request.get_json()
    now=datetime.now().isoformat()
    db=get_db()
    c=db.cursor()

    if d.get("id"):
        c.execute("UPDATE notes SET title=%s,keywords=%s,content=%s,updated_at=%s WHERE id=%s",
                  (d["title"],d["keywords"],d["content"],now,d["id"]))
        c.execute("UPDATE items SET title=%s,preview=%s,updated_at=%s WHERE ref_id=%s AND type='note'",
                  (d["title"],d["content"][:60],now,d["id"]))
        db.commit()
        db.close()
        return jsonify({"ok":True,"id":d["id"]})

    c.execute("INSERT INTO notes(title,keywords,content,updated_at) VALUES(%s,%s,%s,%s) RETURNING id",
              (d["title"],d["keywords"],d["content"],now))
    nid=c.fetchone()[0]
    c.execute("INSERT INTO items(type,ref_id,title,preview,color,updated_at) VALUES('note',%s,%s,%s,'#fff',%s)",
              (nid,d["title"],d["content"][:60],now))
    db.commit()
    db.close()
    return jsonify({"ok":True,"id":nid})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000)
