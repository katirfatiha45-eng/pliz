from flask import Flask, request, jsonify, render_template_string, session, redirect
import os, datetime, secrets, psycopg2, psycopg2.extras, json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "2001.")
DATABASE_URL   = os.environ.get("DATABASE_URL", "")

# ──────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────
def get_conn():
    url = DATABASE_URL
    # Railway préfixe parfois avec "postgres://" au lieu de "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, sslmode="require", cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    """Crée les tables si elles n'existent pas."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    hwid        TEXT PRIMARY KEY,
                    username    TEXT,
                    status      TEXT DEFAULT 'active',
                    created_at  TEXT,
                    last_seen   TEXT,
                    ip          TEXT,
                    use_count   INTEGER DEFAULT 0,
                    reset_cache BOOLEAN DEFAULT FALSE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending (
                    hwid        TEXT PRIMARY KEY,
                    username    TEXT,
                    first_seen  TEXT,
                    ip          TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id         SERIAL PRIMARY KEY,
                    hwid       TEXT,
                    username   TEXT,
                    time       TEXT,
                    ip         TEXT,
                    result     TEXT
                );
            """)
        conn.commit()

# Init au démarrage
try:
    init_db()
    print("✅ Base de données initialisée")
except Exception as e:
    print(f"⚠ Erreur init DB: {e}")

# ──────────────────────────────────────────────────────────
# HELPERS DB
# ──────────────────────────────────────────────────────────
def db_get_client(hwid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM clients WHERE hwid = %s", (hwid,))
            return cur.fetchone()

def db_get_pending(hwid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pending WHERE hwid = %s", (hwid,))
            return cur.fetchone()

def db_add_log(hwid, username, ip, result):
    with get_conn() as conn:
        with conn.cursor() as cur:
            now = datetime.datetime.now().isoformat()
            cur.execute(
                "INSERT INTO logs (hwid, username, time, ip, result) VALUES (%s,%s,%s,%s,%s)",
                (hwid, username, now, ip, result)
            )
            # Garde seulement les 300 derniers logs
            cur.execute("""
                DELETE FROM logs WHERE id NOT IN (
                    SELECT id FROM logs ORDER BY id DESC LIMIT 300
                )
            """)
        conn.commit()

def db_all_clients():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM clients ORDER BY created_at DESC")
            return cur.fetchall()

def db_all_pending():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pending ORDER BY first_seen DESC")
            return cur.fetchall()

def db_recent_logs(limit=300):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT %s", (limit,))
            return cur.fetchall()

# ──────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────
@app.route("/check", methods=["POST"])
def check():
    data     = request.json or {}
    hwid     = data.get("hwid", "").strip()
    username = data.get("username", "Inconnu").strip()
    ip       = request.remote_addr
    now      = datetime.datetime.now().isoformat()

    client = db_get_client(hwid)

    if not client:
        # Pas encore enregistré → pending
        if not db_get_pending(hwid):
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO pending (hwid, username, first_seen, ip) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (hwid, username, now, ip)
                    )
                conn.commit()
        db_add_log(hwid, username, ip, "pending")
        return jsonify({"status": "pending"})

    status = client["status"]

    if status in ("banned", "paused"):
        db_add_log(hwid, username, ip, status)
        return jsonify({"status": status})

    if status == "active":
        reset = bool(client["reset_cache"])
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE clients
                    SET last_seen = %s, ip = %s, use_count = use_count + 1, reset_cache = FALSE
                    WHERE hwid = %s
                """, (now, ip, hwid))
            conn.commit()
        db_add_log(hwid, username, ip, "ok")
        return jsonify({"status": "ok", "reset_cache": reset})

    db_add_log(hwid, username, ip, "denied")
    return jsonify({"status": "denied"})


@app.route("/api/approve", methods=["POST"])
def approve():
    if not session.get("admin"): return jsonify({"error": "Non autorisé"}), 403
    hwid = request.json.get("hwid")
    pending = db_get_pending(hwid)
    if not pending: return jsonify({"error": "Introuvable"}), 404
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO clients (hwid, username, status, created_at, last_seen, ip, use_count, reset_cache)
                VALUES (%s,%s,'active',%s,NULL,%s,0,FALSE)
                ON CONFLICT (hwid) DO UPDATE SET status='active'
            """, (hwid, pending["username"], now, pending["ip"]))
            cur.execute("DELETE FROM pending WHERE hwid = %s", (hwid,))
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/set_status", methods=["POST"])
def set_status():
    if not session.get("admin"): return jsonify({"error": "Non autorisé"}), 403
    data   = request.json or {}
    hwid   = data.get("hwid")
    status = data.get("status")
    if status not in ("active", "paused", "banned"):
        return jsonify({"error": "Status invalide"}), 400
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE clients SET status = %s WHERE hwid = %s", (status, hwid))
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/reset_cache", methods=["POST"])
def reset_cache():
    if not session.get("admin"): return jsonify({"error": "Non autorisé"}), 403
    hwid = request.json.get("hwid")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE clients SET reset_cache = TRUE WHERE hwid = %s", (hwid,))
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/delete", methods=["POST"])
def delete():
    if not session.get("admin"): return jsonify({"error": "Non autorisé"}), 403
    hwid = request.json.get("hwid")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clients WHERE hwid = %s", (hwid,))
            cur.execute("DELETE FROM pending WHERE hwid = %s", (hwid,))
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/reject_pending", methods=["POST"])
def reject_pending():
    if not session.get("admin"): return jsonify({"error": "Non autorisé"}), 403
    hwid = request.json.get("hwid")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pending WHERE hwid = %s", (hwid,))
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/data")
def api_data():
    if not session.get("admin"): return jsonify({"error": "Non autorisé"}), 403
    clients = {r["hwid"]: dict(r) for r in db_all_clients()}
    pending = {r["hwid"]: dict(r) for r in db_all_pending()}
    logs    = [dict(r) for r in db_recent_logs()]
    # Rename created_at → created pour compatibilité dashboard
    for c in clients.values():
        c["created"] = c.pop("created_at", None)
    return jsonify({"clients": clients, "pending": pending, "logs": logs})


@app.route("/login", methods=["POST"])
def login():
    if request.json.get("password") == ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/")
def index():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "dashboard.html"), encoding="utf-8") as f:
        return render_template_string(f.read())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Dashboard : http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
