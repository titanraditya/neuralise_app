import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = Path(__file__).parent / "face_landmarker.task"

# 6 landmark indices per eye (MediaPipe Face Mesh 478-point model)
LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]


def _ensure_model() -> str:
    if not MODEL_PATH.exists():
        print("Downloading face landmarker model (~3 MB)…")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Model downloaded.")
    return str(MODEL_PATH)


def _ear(pts: list[tuple[int, int]]) -> float:
    a = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    b = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    c = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
    return (a + b) / (2.0 * c) if c > 0 else 0.0


class EyeDetector:
    def __init__(self) -> None:
        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=_ensure_model()),
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._detector = mp_vision.FaceLandmarker.create_from_options(options)

    def process(
        self, frame_rgb: np.ndarray
    ) -> tuple[np.ndarray, float | None, float | None, float | None]:
        h, w = frame_rgb.shape[:2]
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._detector.detect(mp_image)
        annotated = frame_rgb.copy()

        if not result.face_landmarks:
            return annotated, None, None, None

        lms = result.face_landmarks[0]

        def to_px(idx: int) -> tuple[int, int]:
            return (int(lms[idx].x * w), int(lms[idx].y * h))

        left_pts  = [to_px(i) for i in LEFT_EYE]
        right_pts = [to_px(i) for i in RIGHT_EYE]

        ear_left  = _ear(left_pts)
        ear_right = _ear(right_pts)
        ear_avg   = (ear_left + ear_right) / 2.0

        for pt in left_pts + right_pts:
            cv2.circle(annotated, pt, 2, (0, 255, 128), -1)

        cv2.putText(
            annotated, f"EAR {ear_avg:.2f}", (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 128), 2,
        )

        return annotated, ear_left, ear_right, ear_avg

    def close(self) -> None:
        self._detector.close()
