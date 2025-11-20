from flask import request, jsonify, render_template, send_from_directory, abort
from .storage import make_data_dir, save_raw_json_payload
import json
import logging
from pathlib import Path
import sqlite3
import datetime

LOG = logging.getLogger("sensor_server.views")

def _repo_data_paths():
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    db_path = data_dir / "sessions.db"
    processed_dir = data_dir / "processed_data"
    raw_dir = data_dir / "raw_data"
    return db_path, processed_dir, raw_dir

def _format_ts(ts):
    try:
        return datetime.datetime.fromtimestamp(int(ts)).isoformat(sep=" ")
    except Exception:
        return ts


def register_routes(app):
    @app.route("/end", methods=["POST"])
    def receive_end():
        raw = request.get_data(as_text=True)
        if not raw:
            return jsonify({"status": "error", "message": "Empty request body"}), 400
        try:
            json.loads(raw)
        except Exception as exc:
            LOG.warning("Invalid JSON received: %s", exc)
            return jsonify({"status": "error", "message": "Invalid JSON payload", "error": str(exc)}), 400
        data_dir = make_data_dir()
        ok, info = save_raw_json_payload(data_dir, raw)
        if not ok:
            return jsonify({"status": "error", "message": "Failed to save data", "error": info}), 500
        # info is a session_meta dict with processed filenames and stats
        return jsonify({"status": "success", "message": "Data saved", "session": info}), 200
    
    @app.route("/", methods=["GET"])
    def index():
        db_path, _, _ = _repo_data_paths()
        sessions = []
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, created_at, duration, heart_mean, heart_max, imu_csv, heart_csv, raw_filename FROM sessions ORDER BY id DESC"
                )
                
                # Fetch data and format the timestamp
                sessions = [
                    {
                        **dict(r),
                        "created_at": _format_ts(r["created_at"])
                    }
                    for r in cur.fetchall()
                ]
                conn.close()
            except Exception as exc:
                LOG.exception("Failed to read sessions DB: %s", exc)

        # Pass the list of sessions directly to the template
        return render_template("index.html", sessions=sessions)

    @app.route("/session/<int:session_id>", methods=["GET"])
    def session_detail(session_id: int):
        db_path, _, _ = _repo_data_paths()
        if not db_path.exists():
            abort(404)
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                abort(404)
            session = dict(row)
            session["created_at_human"] = _format_ts(session.get("created_at"))
            return render_template("session.html", session=session)
        except Exception as exc:
            LOG.exception("Failed to load session %s: %s", session_id, exc)
            abort(500)



