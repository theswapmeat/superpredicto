from flask import Blueprint, jsonify

keepalive_bp = Blueprint("keepalive", __name__)

@keepalive_bp.route("/keep-alive", methods=["GET"])
def keep_alive():
    return jsonify({"status": "ok"}), 200
