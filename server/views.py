from flask import request, jsonify, render_template, send_from_directory, abort
from .storage import make_data_dir, save_raw_json_payload
from .analysis import interpret_session_metrics
from .analysis import compute_and_persist_session_metrics
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
    @app.route("/files/raw/<path:filename>")
    def download_raw(filename):
        # Serve files from data/raw_data
        data_dir = _repo_data_paths()[2]
        return send_from_directory(str(data_dir), filename, as_attachment=False)

    @app.route("/files/processed/<path:filename>")
    def download_processed(filename):
        # Serve files from data/processed_data
        processed_dir = _repo_data_paths()[1]
        return send_from_directory(str(processed_dir), filename, as_attachment=False)
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
                missing = []
                if not wear_payload:
                    missing.append("wear")
                if not shinai_payload:
                    missing.append("shinai")
                session_word = "sessions" if len(missing) > 1 else "session"
                return jsonify({"status": "error", "message": f"{' and '.join(missing)} {session_word} data not found"}), 404

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
                    "SELECT id, created_at, duration, heart_mean, heart_max, imu_csv, heart_csv, raw_filename, strike_count, max_strike_force, avg_intensity, device_type, shinai_strike_count, shinai_max_strike_force, shinai_avg_strike_force, straightness_score, consistency_score, ROW_NUMBER() OVER (ORDER BY id DESC) as display_id FROM sessions WHERE device_type = 'wear' ORDER BY id DESC"
                )
                
                # Fetch data and format the timestamp
                sessions = [
                    {
                        **dict(r),
                        "created_at": _format_ts(r["created_at"])
                    }
                    for r in cur.fetchall()
                ]
                LOG.debug("Loaded %d sessions for index", len(sessions))
                if sessions:
                    LOG.debug("Sample session keys: %s", list(sessions[0].keys()))
                conn.close()
                # Attach friendly summary for each session for beginner UI
                try:
                    from .analysis import interpret_session_metrics as _interp
                    for s in sessions:
                        try:
                            try:
                                LOG.debug("Index control inputs for session %s: straightness=%s, consistency=%s", s.get("id"), s.get("straightness_score"), s.get("consistency_score"))
                            except Exception:
                                pass
                            friendly = _interp(s)
                            s["control_category"] = friendly.get("control_category")
                            s["control_color"] = friendly.get("control_color")
                            s["heart_category"] = friendly.get("heart_category")
                        except Exception:
                            continue
                except Exception:
                    LOG.exception("Failed to compute friendly summaries for index")
                # Build small preview series (sparkline) per session: prefer shinai if matched, else wrist imu
                try:
                    processed_dir = _repo_data_paths()[1]
                    for s in sessions:
                        s['display_series'] = []
                        try:
                            # matched_shinai stored in DB may be JSON list or text
                            matched_raw = s.get('matched_shinai')
                            shinai_path = None
                            if matched_raw:
                                try:
                                    matched_list = json.loads(matched_raw) if isinstance(matched_raw, str) else matched_raw
                                except Exception:
                                    matched_list = matched_raw
                                if isinstance(matched_list, list) and len(matched_list) > 0:
                                    rel = matched_list[0]
                                    p = processed_dir / rel
                                    if p.exists():
                                        shinai_path = p

                            csv_path = None
                            if shinai_path:
                                csv_path = shinai_path
                            else:
                                # fallback to imu_csv stored path
                                imu_rel = s.get('imu_csv')
                                if imu_rel:
                                    p2 = processed_dir / imu_rel
                                    if p2.exists():
                                        csv_path = p2

                            if csv_path:
                                # read accel columns and compute magnitude (fallback to gyro if accel missing/zero)
                                series = []
                                try:
                                    with csv_path.open('r', encoding='utf-8') as fh:
                                        import csv as _csv
                                        reader = _csv.reader(fh)
                                        headers = next(reader, None)
                                        for rowr in reader:
                                            if not rowr:
                                                continue
                                            try:
                                                t = float(rowr[0])
                                            except Exception:
                                                continue
                                            # Parse accel
                                            try:
                                                ax = float(rowr[1]) if rowr[1] != '' else None
                                                ay = float(rowr[2]) if rowr[2] != '' else None
                                                az = float(rowr[3]) if rowr[3] != '' else None
                                            except Exception:
                                                ax = ay = az = None
                                            # Parse gyro (if present)
                                            try:
                                                gx = float(rowr[4]) if len(rowr) > 4 and rowr[4] != '' else None
                                                gy = float(rowr[5]) if len(rowr) > 5 and rowr[5] != '' else None
                                                gz = float(rowr[6]) if len(rowr) > 6 and rowr[6] != '' else None
                                            except Exception:
                                                gx = gy = gz = None
                                            mag = None
                                            try:
                                                if ax is not None and ay is not None and az is not None:
                                                    # Use accel magnitude (gravity compensated to G units)
                                                    mag_acc = (ax*ax + ay*ay + az*az) ** 0.5
                                                    if mag_acc > 0:
                                                        g_units = (mag_acc / 9.80665) - 1.0
                                                        if g_units < 0:
                                                            g_units = 0.0
                                                        mag = g_units
                                            except Exception:
                                                pass
                                            if mag is None:
                                                try:
                                                    if gx is not None and gy is not None and gz is not None:
                    						# Gyro fallback: show raw magnitude (no gravity compensation)
                                                        mag_gyro = (gx*gx + gy*gy + gz*gz) ** 0.5
                                                        mag = mag_gyro
                                                except Exception:
                                                    pass
                                            if mag is not None:
                                                series.append(mag)
                                except Exception:
                                    series = []

                                # downsample to at most 100 points
                                if series:
                                    max_pts = 100
                                    if len(series) <= max_pts:
                                        s['display_series'] = series
                                    else:
                                        step = max(1, len(series) // max_pts)
                                        s['display_series'] = [series[i] for i in range(0, len(series), step)][:max_pts]
                        except Exception:
                            continue
                except Exception:
                    LOG.exception("Failed to build preview series for sessions")
            except Exception as exc:
                LOG.exception("Failed to read sessions DB: %s", exc)

        # Pass the list of sessions directly to the template
        return render_template("index.html", sessions=sessions)
    
    @app.route("/trends", methods=["GET"])
    def trends():
        """Display progress trends over time."""
        db_path, _, _ = _repo_data_paths()
        if not db_path.exists():
            abort(404)
        
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Get last 20 wear sessions with trend data
            cur.execute(
                """SELECT id, created_at, straightness_score, consistency_score, 
                   avg_intensity, heart_mean, strike_count, duration
                   FROM sessions WHERE device_type = 'wear' 
                   ORDER BY id DESC LIMIT 20"""
            )
            sessions = [dict(r) for r in cur.fetchall()]
            sessions.reverse()  # Show oldest first (left to right)
            
            conn.close()
            return render_template("trends.html", sessions=sessions)
        except Exception as exc:
            LOG.exception("Trends failed: %s", exc)
            abort(500)

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
                "SELECT *, (SELECT COUNT(*)+1 FROM sessions s2 WHERE s2.device_type='wear' AND s2.id > sessions.id) as display_id FROM sessions WHERE id = ?", (session_id,)
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                abort(404)
            session = dict(row)
            session["created_at_human"] = _format_ts(session.get("created_at"))
            # Initialize derived fields to None so template checks work
            session.setdefault("max_kinetic_energy_cal", None)
            try:
                session["friendly_summary"] = interpret_session_metrics(session)
            except Exception:
                LOG.exception("Failed to compute friendly summary for session %s", session_id)
                session["friendly_summary"] = None
            # Compute experimental pace metrics if missing: strike rate (/min) and avg interval (ms)
            try:
                rate = session.get("strike_rate_per_min")
                avg_ms = session.get("avg_inter_strike_ms")
                dur = session.get("duration")
                count = session.get("strike_count")
                if (rate is None or rate == 0) and dur and dur > 0 and count and count > 0:
                    session["strike_rate_per_min"] = (float(count) / float(dur)) * 60.0
                if (avg_ms is None or avg_ms == 0) and dur and dur > 0 and count and count and count > 1:
                    session["avg_inter_strike_ms"] = (float(dur) * 1000.0) / float(count)
            except Exception:
                LOG.debug("Failed to derive pace metrics for session %s", session_id)
            # Centralized architecture: avoid on-demand recompute in view
            # Calculate tip speed and energy from wrist IMU if missing
            try:
                tip_speed = session.get("max_tip_speed_mps")
                energy_j = session.get("max_kinetic_energy_joules")
                if (tip_speed is None or energy_j is None):
                    # Load wrist IMU to calculate from gyro
                    imu_csv = session.get("imu_csv")
                    if imu_csv:
                        processed_dir = _repo_data_paths()[1]
                        imu_path = processed_dir / imu_csv
                        if imu_path.exists():
                            import csv as _csv
                            max_gyro_mag = 0.0
                            with imu_path.open("r", encoding="utf-8") as fh:
                                reader = _csv.reader(fh)
                                _ = next(reader, None)
                                for rowr in reader:
                                    if not rowr or len(rowr) < 7:
                                        continue
                                    try:
                                        gx = float(rowr[4]) if rowr[4] != '' else 0.0
                                        gy = float(rowr[5]) if rowr[5] != '' else 0.0
                                        gz = float(rowr[6]) if rowr[6] != '' else 0.0
                                        gyro_mag = (gx*gx + gy*gy + gz*gz) ** 0.5
                                        if gyro_mag > max_gyro_mag:
                                            max_gyro_mag = gyro_mag
                                    except Exception:
                                        continue
                            if max_gyro_mag > 0:
                                # Assume distance from wrist to tip: 1.2 meters (typical shinai length)
                                distance_m = 1.2
                                tip_speed_calc = max_gyro_mag * distance_m  # v = omega * r
                                session["max_tip_speed_mps"] = tip_speed_calc
                                # Calculate kinetic energy: E = 0.5 * m * v^2 (m = 0.57 kg)
                                mass_kg = 0.57
                                energy_j_calc = 0.5 * mass_kg * (tip_speed_calc ** 2)
                                session["max_kinetic_energy_joules"] = energy_j_calc
                                # Convert to calories
                                session["max_kinetic_energy_cal"] = energy_j_calc * 0.000239006
            except Exception:
                LOG.debug("Failed to calculate tip speed/energy for session %s", session_id)
            # Convert energy to calories if present but not yet converted
            try:
                if session.get("max_kinetic_energy_cal") is None:
                    energy_j = session.get("max_kinetic_energy_joules")
                    if energy_j is not None:
                        session["max_kinetic_energy_cal"] = float(energy_j) * 0.000239006
            except Exception:
                pass
            return render_template("session.html", session=session)
        except Exception as exc:
            LOG.exception("Failed to load session %s: %s", session_id, exc)
            abort(500)


    @app.route("/api/session/<int:session_id>/metrics", methods=["GET"])
    def api_session_metrics(session_id: int):
        db_path, processed_dir, _ = _repo_data_paths()
        if not db_path.exists():
            return jsonify({"status": "error", "message": "DB not found"}), 404
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return jsonify({"status": "error", "message": "Session not found"}), 404
            sess = dict(row)

            # Attempt to load first matched shinai series if available
            shinai_series = None
            try:
                matched_raw = sess.get("matched_shinai")
                if matched_raw:
                    # matched_shinai may be stored as JSON list or a text
                    try:
                        matched_list = json.loads(matched_raw) if isinstance(matched_raw, str) else matched_raw
                    except Exception:
                        matched_list = matched_raw
                    if isinstance(matched_list, list) and len(matched_list) > 0:
                        rel = matched_list[0]
                        shinai_path = processed_dir / rel
                        if shinai_path.exists():
                            series = []
                            with shinai_path.open("r", encoding="utf-8") as fh:
                                import csv as _csv
                                r = _csv.reader(fh)
                                headers = next(r, None)
                                for rowr in r:
                                    if not rowr:
                                        continue
                                    try:
                                        t = float(rowr[0])
                                    except Exception:
                                        continue
                                    # Parse accel
                                    try:
                                        ax = float(rowr[1]) if rowr[1] != '' else None
                                        ay = float(rowr[2]) if rowr[2] != '' else None
                                        az = float(rowr[3]) if rowr[3] != '' else None
                                    except Exception:
                                        ax = ay = az = None
                                    # Parse gyro
                                    try:
                                        gx = float(rowr[4]) if len(rowr) > 4 and rowr[4] != '' else None
                                        gy = float(rowr[5]) if len(rowr) > 5 and rowr[5] != '' else None
                                        gz = float(rowr[6]) if len(rowr) > 6 and rowr[6] != '' else None
                                    except Exception:
                                        gx = gy = gz = None
                                    mag = None
                                    try:
                                        if ax is not None and ay is not None and az is not None:
                                            mag_acc = (ax*ax + ay*ay + az*az) ** 0.5
                                            if mag_acc > 0:
                                                g_units = (mag_acc / 9.80665) - 1.0
                                                if g_units < 0:
                                                    g_units = 0.0
                                                mag = g_units
                                    except Exception:
                                        pass
                                    if mag is None:
                                        try:
                                            if gx is not None and gy is not None and gz is not None:
                                                # Gyro fallback: raw magnitude
                                                mag = (gx*gx + gy*gy + gz*gz) ** 0.5
                                        except Exception:
                                            pass
                                    series.append({"t": t, "ax": ax, "ay": ay, "az": az, "gx": gx, "gy": gy, "gz": gz, "mag": mag})
                            shinai_series = series
            except Exception:
                LOG.exception("Failed to load matched shinai series for session %s", session_id)

            conn.close()
            # Add friendly summary to API response
            try:
                friendly = interpret_session_metrics(sess)
            except Exception:
                LOG.exception("Failed to compute friendly summary for api metrics %s", session_id)
                friendly = None
            resp = {"status": "success", "session": sess, "shinai_series": shinai_series, "friendly_summary": friendly}
            return jsonify(resp), 200
        except Exception as exc:
            LOG.exception("API metrics failed for %s", session_id)
            return jsonify({"status": "error", "message": str(exc)}), 500


    @app.route("/api/session/<int:session_id>/strikes", methods=["GET"])
    def api_session_strikes(session_id: int):
        # Deprecated per user request: return empty strikes always
        return jsonify({"status": "success", "strikes": []}), 200


    @app.route("/admin/backfill", methods=["POST"])
    def admin_backfill():
        db_path, _, _ = _repo_data_paths()
        if not db_path.exists():
            return jsonify({"status": "error", "message": "DB not found"}), 404
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Select wear sessions; backfill where key metrics are missing
            cur.execute(
                "SELECT id, straightness_score, consistency_score, shinai_strike_count, shinai_max_strike_force, shinai_avg_strike_force, max_tip_speed_mps, max_kinetic_energy_joules FROM sessions WHERE device_type='wear' ORDER BY id DESC"
            )
            rows = cur.fetchall()
            conn.close()

            processed = []
            failed = []
            for r in rows:
                sess = dict(r)
                sid = sess.get("id")
                missing = (
                    sess.get("straightness_score") is None or
                    sess.get("consistency_score") is None or
                    sess.get("shinai_strike_count") is None or
                    sess.get("shinai_max_strike_force") is None or
                    sess.get("shinai_avg_strike_force") is None or
                    sess.get("max_tip_speed_mps") is None or
                    sess.get("max_kinetic_energy_joules") is None
                )
                if not missing:
                    continue
                try:
                    compute_and_persist_session_metrics(sid)
                    processed.append(sid)
                except Exception as exc:
                    LOG.exception("Backfill failed for session %s: %s", sid, exc)
                    failed.append({"id": sid, "error": str(exc)})

            return jsonify({"status": "success", "processed": processed, "failed": failed}), 200
        except Exception as exc:
            LOG.exception("Admin backfill route failed: %s", exc)
            return jsonify({"status": "error", "message": str(exc)}), 500



