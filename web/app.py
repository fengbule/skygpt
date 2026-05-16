# -*- coding: utf-8 -*-
"""
SkyGPT Web Application Entry Point
Flask + SocketIO for real-time log streaming
"""
import os
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from web.api_tasks import task_bp
from web.api_proxies import proxy_bp
from web.api_cpa import cpa_bp
from core.pausable_registration import RegistrationManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CPA_DIR = BASE_DIR / "cpa_files"
LOGS_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CPA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "skygpt-secret-key-2026")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

app.register_blueprint(task_bp)
app.register_blueprint(proxy_bp)
app.register_blueprint(cpa_bp)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

reg_manager = RegistrationManager.get_instance()
reg_manager.set_socketio(socketio)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/tasks")
def tasks_page():
    return render_template("tasks.html")

@app.route("/proxies")
def proxies_page():
    return render_template("proxies.html")

@app.route("/cpa")
def cpa_page():
    return render_template("cpa.html")

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "SkyGPT Web App is running"})

@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"message": "Connected to SkyGPT WebSocket"})

@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on("subscribe_task")
def handle_subscribe_task(data):
    task_id = data.get("task_id")
    logger.info(f"Client {request.sid} subscribed to task {task_id}")
    emit("subscribed", {"task_id": task_id, "message": f"Successfully subscribed to task {task_id}"})

if __name__ == "__main__":
    logger.info("Starting SkyGPT Web Application...")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)