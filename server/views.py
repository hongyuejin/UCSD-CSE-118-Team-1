from flask import request, jsonify
from .storage import make_data_dir, save_raw_json_payload
import json
import logging

LOG = logging.getLogger("sensor_server.views")


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
        return jsonify({"status": "success", "message": "Data saved", "filename": info}), 200

