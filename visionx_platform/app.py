from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from werkzeug.utils import secure_filename

from vision_engine import VisionEngine

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm", "m4v"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SECRET_KEY"] = os.environ.get("VISIONX_SECRET_KEY", "change-this-local-dev-key")
engine = VisionEngine(
    model_path=os.environ.get("VISIONX_MODEL", "yolo11n.pt"),
    confidence=float(os.environ.get("VISIONX_CONFIDENCE", "0.35")),
)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    return jsonify(engine.snapshot())


@app.post("/api/camera/start")
def api_camera_start():
    payload = request.get_json(silent=True) or {}
    try:
        camera_index = int(payload.get("camera_index", 0))
        if camera_index < 0 or camera_index > 8:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Camera index must be an integer from 0 to 8."}), 400
    ok, message = engine.start_camera(camera_index)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 503)


@app.post("/api/video/upload")
def api_video_upload():
    if "video" not in request.files:
        return jsonify({"ok": False, "message": "Choose a video file first."}), 400
    file = request.files["video"]
    if not file.filename:
        return jsonify({"ok": False, "message": "No file was selected."}), 400
    if not allowed_file(file.filename):
        return jsonify({"ok": False, "message": "Unsupported format. Use MP4, AVI, MOV, MKV, WEBM or M4V."}), 400

    original = secure_filename(file.filename)
    suffix = Path(original).suffix.lower()
    stored_name = f"{uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / stored_name
    file.save(destination)
    size_mb = destination.stat().st_size / (1024 * 1024)
    return jsonify({
        "ok": True,
        "filename": stored_name,
        "original_name": original,
        "size_mb": round(size_mb, 2),
        "message": "Video uploaded successfully.",
    })


@app.post("/api/video/start")
def api_video_start():
    payload = request.get_json(silent=True) or {}
    filename = Path(str(payload.get("filename", ""))).name
    if not filename or filename != payload.get("filename"):
        return jsonify({"ok": False, "message": "Invalid uploaded video reference."}), 400
    path = UPLOAD_DIR / filename
    if not path.is_file() or path.suffix.lower().lstrip(".") not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "message": "Uploaded video not found. Upload it again."}), 404
    ok, message = engine.start_video(str(path), path.name)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 422)


@app.post("/api/stop")
def api_stop():
    engine.stop()
    return jsonify({"ok": True, "message": "Processing stopped."})


@app.get("/video_feed")
def video_feed():
    @stream_with_context
    def generate():
        last_version = -1
        while True:
            frame, version = engine.get_frame()
            if frame is not None and version != last_version:
                last_version = version
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Cache-Control: no-cache\r\n\r\n" + frame + b"\r\n")
            else:
                status = engine.snapshot()
                if not status.get("running") and frame is None:
                    break
                import time
                time.sleep(0.03)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.errorhandler(413)
def request_entity_too_large(_error):
    return jsonify({"ok": False, "message": "The uploaded file exceeds the 500 MB limit."}), 413


@app.teardown_appcontext
def cleanup(_exception=None):
    # Do not stop the worker at the end of each request; Flask creates app contexts per request.
    pass


if __name__ == "__main__":
    host = os.environ.get("VISIONX_HOST", "127.0.0.1")
    port = int(os.environ.get("VISIONX_PORT", "5000"))
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
