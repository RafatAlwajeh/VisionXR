"""VisionX real-time object detection and tracking engine."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import cv2


TRACKED_CLASS_IDS = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck (COCO)
VEHICLE_NAMES = {"car", "motorcycle", "bus", "truck"}


class VisionEngine:
    """Runs a single camera/video source in a worker thread and exposes snapshots."""

    def __init__(self, model_path: str = "yolo11n.pt", confidence: float = 0.35):
        self.model_path = model_path
        self.confidence = confidence
        self._control_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None
        self._latest_jpeg: bytes | None = None
        self._frame_version = 0
        self._status: dict[str, Any] = self._empty_status()
        self._unique_tracks: dict[str, set[str]] = defaultdict(set)
        self._history: deque[dict[str, Any]] = deque(maxlen=60)
        self._last_history_at = 0.0
        self._track_paths: dict[str, deque[tuple[int, int]]] = defaultdict(lambda: deque(maxlen=24))

    @staticmethod
    def _empty_status() -> dict[str, Any]:
        return {
            "running": False,
            "state": "stopped",
            "source": "None",
            "source_type": None,
            "message": "No video source selected",
            "fps": 0.0,
            "processing_ms": 0.0,
            "people": 0,
            "vehicles": 0,
            "bicycles": 0,
            "unique_people": 0,
            "unique_vehicles": 0,
            "unique_bicycles": 0,
            "detections": 0,
            "traffic": "No data",
            "updated_at": None,
            "history": [],
        }

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            data = dict(self._status)
            data["history"] = list(self._history)
            return data

    def get_frame(self) -> tuple[bytes | None, int]:
        with self._state_lock:
            return self._latest_jpeg, self._frame_version

    def start_camera(self, camera_index: int = 0) -> tuple[bool, str]:
        return self._start_source(camera_index, "camera", f"Camera {camera_index}")

    def start_video(self, video_path: str, display_name: str) -> tuple[bool, str]:
        return self._start_source(video_path, "video", display_name)

    def _start_source(self, source: Any, source_type: str, source_label: str) -> tuple[bool, str]:
        with self._control_lock:
            self.stop()
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                return False, "Could not open the selected camera or video. Check the source and permissions."

            stop_event = threading.Event()
            with self._state_lock:
                self._latest_jpeg = None
                self._frame_version = 0
                self._unique_tracks.clear()
                self._history.clear()
                self._track_paths.clear()
                self._last_history_at = 0.0
                self._status = self._empty_status()
                self._status.update({
                    "running": True,
                    "state": "loading_model",
                    "source": source_label,
                    "source_type": source_type,
                    "message": "Loading AI model…",
                })

            self._cap = cap
            self._stop_event = stop_event
            self._thread = threading.Thread(
                target=self._process_loop,
                args=(cap, stop_event, source_type),
                name="VisionX-Processor",
                daemon=True,
            )
            self._thread.start()
            return True, "Source started. The AI model is initializing if this is the first run."

    def stop(self) -> None:
        with self._control_lock:
            event = self._stop_event
            thread = self._thread
            cap = self._cap
            if event:
                event.set()
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=3.0)
            if cap:
                cap.release()
            self._stop_event = None
            self._thread = None
            self._cap = None
            with self._state_lock:
                self._status["running"] = False
                self._status["state"] = "stopped"
                if self._status.get("message") not in {"Video ended", "Processing stopped", "No video source selected"}:
                    self._status["message"] = "Processing stopped"

    def _process_loop(self, cap: cv2.VideoCapture, stop_event: threading.Event, source_type: str) -> None:
        try:
            # Lazy import keeps the dashboard importable before PyTorch/Ultralytics is installed.
            from ultralytics import YOLO

            model = YOLO(self.model_path)
            with self._state_lock:
                self._status["state"] = "running"
                self._status["message"] = "AI detection and tracking active"

            smoothed_fps = 0.0
            while not stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    message = "Video ended" if source_type == "video" else "Camera frame unavailable"
                    break

                started = time.perf_counter()
                result = model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    conf=self.confidence,
                    imgsz=640,
                    classes=TRACKED_CLASS_IDS,
                    verbose=False,
                )[0]

                annotated, counts, track_ids = self._annotate(result, frame)
                elapsed = max(time.perf_counter() - started, 1e-6)
                instant_fps = 1.0 / elapsed
                smoothed_fps = instant_fps if smoothed_fps == 0 else (0.85 * smoothed_fps + 0.15 * instant_fps)
                processing_ms = elapsed * 1000.0

                ok_jpeg, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
                if ok_jpeg:
                    with self._state_lock:
                        self._latest_jpeg = encoded.tobytes()
                        self._frame_version += 1
                        self._status.update({
                            "running": True,
                            "state": "running",
                            "fps": round(smoothed_fps, 1),
                            "processing_ms": round(processing_ms, 1),
                            "people": counts["people"],
                            "vehicles": counts["vehicles"],
                            "bicycles": counts["bicycles"],
                            "unique_people": len(self._unique_tracks["people"]),
                            "unique_vehicles": len(self._unique_tracks["vehicles"]),
                            "unique_bicycles": len(self._unique_tracks["bicycles"]),
                            "detections": sum(counts.values()),
                            "traffic": self._traffic_level(counts["vehicles"]),
                            "updated_at": time.time(),
                        })
                        now = time.time()
                        if now - self._last_history_at >= 1.0:
                            self._history.append({
                                "time": time.strftime("%H:%M:%S"),
                                "people": counts["people"],
                                "vehicles": counts["vehicles"],
                                "bicycles": counts["bicycles"],
                            })
                            self._last_history_at = now

                # Avoid pegging a CPU when processing a high-FPS file faster than real time.
                if source_type == "video":
                    source_fps = cap.get(cv2.CAP_PROP_FPS)
                    if source_fps and source_fps > 0:
                        remaining = (1.0 / min(source_fps, 60.0)) - elapsed
                        if remaining > 0:
                            stop_event.wait(min(remaining, 0.05))

            with self._state_lock:
                self._status["running"] = False
                self._status["state"] = "stopped"
                self._status["message"] = message if "message" in locals() else "Processing stopped"
        except Exception as exc:  # surfaced to the dashboard for troubleshooting
            with self._state_lock:
                self._status["running"] = False
                self._status["state"] = "error"
                self._status["message"] = f"Processing error: {type(exc).__name__}: {exc}"
        finally:
            cap.release()

    def _annotate(self, result: Any, frame: Any) -> tuple[Any, dict[str, int], list[str]]:
        counts = {"people": 0, "vehicles": 0, "bicycles": 0}
        current_track_ids: list[str] = []
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return frame, counts, current_track_ids

        xyxy = boxes.xyxy.cpu().numpy().astype(int)
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confidences = boxes.conf.cpu().numpy()
        ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(xyxy)
        names = result.names

        colors = {
            "people": (26, 180, 255),
            "vehicles": (35, 90, 255),
            "bicycles": (205, 85, 255),
        }
        for coords, class_id, confidence, track_id in zip(xyxy, cls_ids, confidences, ids):
            name = str(names.get(int(class_id), class_id)).lower()
            if name == "person":
                group = "people"
            elif name == "bicycle":
                group = "bicycles"
            elif name in VEHICLE_NAMES:
                group = "vehicles"
            else:
                continue

            counts[group] += 1
            x1, y1, x2, y2 = [int(v) for v in coords]
            color = colors[group]
            track_label = f" #{track_id}" if track_id is not None else ""
            label = f"{name} {float(confidence):.2f}{track_label}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            top = max(0, y1 - text_h - baseline - 8)
            cv2.rectangle(frame, (x1, top), (x1 + text_w + 10, y1), color, -1)
            cv2.putText(frame, label, (x1 + 5, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

            if track_id is not None:
                key = f"{group}:{track_id}"
                self._unique_tracks[group].add(str(track_id))
                current_track_ids.append(key)
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                self._track_paths[key].append(center)
                points = list(self._track_paths[key])
                if len(points) > 1:
                    import numpy as np
                    cv2.polylines(frame, [np.array(points, dtype="int32")], False, color, 2, cv2.LINE_AA)
        return frame, counts, current_track_ids

    @staticmethod
    def _traffic_level(vehicle_count: int) -> str:
        if vehicle_count <= 2:
            return "Light"
        if vehicle_count <= 6:
            return "Moderate"
        return "Heavy"
