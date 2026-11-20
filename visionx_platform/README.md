# VisionX — Intelligent Computer Vision Platform

A local-first web dashboard for live object detection, multi-object tracking, counting, and video analytics.

## Included in this first build

- Live camera input from the computer running the Flask server.
- Upload and analyze MP4, AVI, MOV, MKV, WEBM, and M4V videos (up to 500 MB).
- YOLO11n object detection for people, bicycles, cars, motorcycles, buses, and trucks.
- ByteTrack tracking with track IDs and short trajectory trails.
- Current-frame counts, session-unique track counts, FPS, inference time, and a 60-second activity chart.
- Responsive dark dashboard inspired by the supplied VisionX reference image.

## Requirements

- Windows 10/11, macOS, or Linux.
- Python 3.10–3.12 recommended.
- A webcam for live camera mode.
- Internet access the first time the application starts so pip can install packages and Ultralytics can download `yolo11n.pt` model weights.
- CPU works for a basic trial. NVIDIA GPU + compatible PyTorch/CUDA can improve throughput, but setup depends on the exact GPU and driver.

## Run on Windows

1. Extract the ZIP file.
2. Open the `visionx_platform` folder.
3. Double-click `run.bat`.
4. When the server starts, open `http://127.0.0.1:5000` in Chrome or Edge.
5. Press **Start Camera**, or upload a video.

The first launch installs the Python requirements and may download the model weights. This can take time and requires internet access.

## Run on macOS / Linux

```bash
chmod +x run.sh
./run.sh
```

Then open `http://127.0.0.1:5000`.

## Manual setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

## Configuration

Optional environment variables:

- `VISIONX_MODEL`: model weights path/name. Default: `yolo11n.pt`.
- `VISIONX_CONFIDENCE`: detection confidence threshold. Default: `0.35`.
- `VISIONX_HOST`: bind address. Default: `127.0.0.1` (local computer only).
- `VISIONX_PORT`: port. Default: `5000`.
- `VISIONX_SECRET_KEY`: Flask secret key. Replace before any non-local deployment.

To use a custom trained model, set `VISIONX_MODEL` to its `.pt` path.

## Important operating notes

- In this local-first build, the camera is opened by the Python process. Therefore, live camera mode uses a camera attached to the computer running VisionX, not automatically the phone or remote visitor's camera.
- Uploaded videos are saved temporarily in `uploads/` and processed locally by the server. Remove files from this directory when they are no longer needed.
- The traffic level is a simple heuristic based on the number of vehicles visible in the current frame. It is not calibrated traffic-flow engineering analysis.
- “Unique IDs” are tracker IDs observed during the current session. Trackers can occasionally change IDs or lose tracks when objects are occluded or leave the frame; these values are not guaranteed person/vehicle identities.
- FPS is the inference-loop throughput estimate. It varies with resolution, model, CPU/GPU, and scene complexity.
- The included dashboard uses Chart.js and Google Fonts from CDNs. If the machine is offline after setup, the core detector can still run, but those hosted assets may not load.

## Project structure

```text
visionx_platform/
├── app.py                 # Flask routes and MJPEG video endpoint
├── vision_engine.py       # OpenCV + YOLO + ByteTrack worker
├── requirements.txt
├── run.bat
├── run.sh
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   └── js/app.js
└── uploads/               # Temporary uploaded videos
```

## Current scope / next engineering steps

This is a functional first MVP, not yet a production multi-user service. The next steps for a production release would include per-user source isolation, multiple simultaneous camera streams, persistent analytics storage, configurable counting lines/zones, authentication, HTTPS, retention controls, a WebSocket-based event channel, and deployment hardening.

## Model licensing notice

This build uses Ultralytics YOLO weights and the Ultralytics Python package. Ultralytics currently describes its Community license as AGPL-3.0 and states that proprietary/private commercial deployment may require an Enterprise license. Review the current license terms for your exact distribution and business model before publishing or selling VisionX; this README is not legal advice. See https://www.ultralytics.com/license.
