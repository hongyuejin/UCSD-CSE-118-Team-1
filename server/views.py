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

    @app.route("/analyze_dual", methods=["POST"])
    def analyze_dual():
        try:
            req_data = request.get_json()
            if not req_data:
                return jsonify({"status": "error", "message": "Empty request body"}), 400
                
            wear_id = req_data.get("wear_session_id")
            shinai_id = req_data.get("shinai_session_id")
            
            # Load data (simplification: we need to find the files based on ID or filename)
            # For now, let's assume the client sends the raw filenames or we look them up
            # In a real app, we'd query the DB. Here, we'll assume filenames are passed or look up by ID.
            # To keep it simple and robust given current storage.py, let's assume filenames are passed 
            # OR we implement a helper to load by ID.
            
            # Let's try to load by filename from data/raw_data
            from .storage import make_data_dir
            data_dir = make_data_dir()
            raw_dir = data_dir / "raw_data"
            
            def load_payload(filename):
                p = raw_dir / filename
                if not p.exists():
                    return None
                return json.loads(p.read_text(encoding="utf-8"))

            wear_payload = load_payload(wear_id)
            shinai_payload = load_payload(shinai_id)
            
            if not wear_payload or not shinai_payload:
                 return jsonify({"status": "error", "message": "Session data not found"}), 404

            from .dual_analysis import analyze_dual_session
            report = analyze_dual_session(wear_payload, shinai_payload, req_data)
            
            return jsonify({"status": "success", "report": report}), 200
            
        except Exception as e:
            LOG.exception("Dual analysis failed")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/dual_analysis", methods=["GET"])
    def dual_analysis_form():
        db_path, _, _ = _repo_data_paths()
        wear_sessions = []
        shinai_sessions = []
        
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # Get wear sessions
                cur.execute(
                    "SELECT id, created_at, strike_count FROM sessions WHERE device_type = 'wear' ORDER BY id DESC"
                )
                wear_sessions = [
                    {**dict(r), "created_at": _format_ts(r["created_at"])}
                    for r in cur.fetchall()
                ]
                
                # Get shinai sessions
                cur.execute(
                    "SELECT id, created_at, strike_count FROM sessions WHERE device_type = 'shinai' ORDER BY id DESC"
                )
                shinai_sessions = [
                    {**dict(r), "created_at": _format_ts(r["created_at"])}
                    for r in cur.fetchall()
                ]
                
                conn.close()
            except Exception as exc:
                LOG.exception("Failed to load sessions: %s", exc)
        
        return render_template("dual_analysis.html", wear_sessions=wear_sessions, shinai_sessions=shinai_sessions)

    @app.route("/analyze_dual_web", methods=["POST"])
    def analyze_dual_web():
        try:
            wear_id = request.form.get("wear_session_id")
            shinai_id = request.form.get("shinai_session_id")
            distance_inches = float(request.form.get("distance_inches", 30))
            sword_weight_lbs = float(request.form.get("sword_weight_lbs", 1.1))
            
            db_path, _, raw_dir = _repo_data_paths()
            
            # Load sessions from database
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute("SELECT * FROM sessions WHERE id = ?", (wear_id,))
            wear_row = cur.fetchone()
            cur.execute("SELECT * FROM sessions WHERE id = ?", (shinai_id,))
            shinai_row = cur.fetchone()
            
            conn.close()
            
            if not wear_row or not shinai_row:
                abort(404)
            
            wear_session = dict(wear_row)
            shinai_session = dict(shinai_row)
            wear_session["created_at"] = _format_ts(wear_session.get("created_at"))
            shinai_session["created_at"] = _format_ts(shinai_session.get("created_at"))
            
            # Load raw data files
            def load_payload(filename):
                p = raw_dir / filename
                if not p.exists():
                    return None
                return json.loads(p.read_text(encoding="utf-8"))
            
            wear_payload = load_payload(wear_session["raw_filename"])
            shinai_payload = load_payload(shinai_session["raw_filename"])
            
            if not wear_payload or not shinai_payload:
                abort(404)
            
            # Run dual analysis
            from .dual_analysis import analyze_dual_session
            params = {
                "distance_inches": distance_inches,
                "sword_weight_lbs": sword_weight_lbs
            }
            results = analyze_dual_session(wear_payload, shinai_payload, params)
            
            return render_template(
                "dual_results.html",
                wear_session=wear_session,
                shinai_session=shinai_session,
                results=results
            )
            
        except Exception as e:
            LOG.exception("Dual analysis web failed")
            abort(500)
    
    
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
                    "SELECT id, created_at, duration, heart_mean, heart_max, imu_csv, heart_csv, raw_filename, strike_count, max_strike_force, avg_intensity, device_type FROM sessions ORDER BY id DESC"
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



