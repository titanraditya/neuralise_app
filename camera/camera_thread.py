import datetime
from pathlib import Path

import cv2
from PySide6.QtCore import QThread, Signal

from camera.detector import EyeDetector
from camera.perclos import PerclosCalculator
from camera.recorder import SessionRecorder
from core.sources.mock import MockCameraSource


class CameraThread(QThread):
    frame_ready = Signal(object)                               # np.ndarray RGB
    analysis_ready = Signal(float, float, float, float, str)  # ear_l, ear_r, ear_avg, perclos, status
    recording_saved = Signal(str)                             # saved CSV path
    camera_error = Signal(str)                                # error message

    def __init__(self, parent=None, use_mock: bool = False) -> None:
        super().__init__(parent)
        self._running = False
        self._recording = False
        self._use_mock = use_mock
        self._perclos = PerclosCalculator()
        self._recorder = SessionRecorder()

    def start_camera(self) -> None:
        self._running = True
        self.start()

    def stop_camera(self) -> None:
        self._running = False
        if self._recording:
            self.stop_recording()
        self.wait()

    def start_recording(self, path: str | Path | None = None) -> None:
        self._perclos.reset()
        self._recorder.start(path)
        self._recording = True

    def stop_recording(self) -> None:
        self._recording = False
        path = self._recorder.stop()
        if path:
            self.recording_saved.emit(str(path))

    def run(self) -> None:
        if self._use_mock:
            self._run_mock()
        else:
            self._run_camera()

    def _run_camera(self) -> None:
        detector = EyeDetector()

        # On Windows, DirectShow backend is more reliable than the default MSMF
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)  # fallback
        if not cap.isOpened():
            self.camera_error.emit("Cannot open camera. Check that no other app is using it.")
            detector.close()
            return

        fail_count = 0
        try:
            while self._running:
                ret, frame_bgr = cap.read()
                if not ret:
                    fail_count += 1
                    if fail_count > 30:
                        self.camera_error.emit("Camera stopped sending frames.")
                        break
                    continue
                fail_count = 0

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                annotated, ear_left, ear_right, ear_avg = detector.process(frame_rgb)
                self._emit_analysis(annotated, ear_left, ear_right, ear_avg)
        finally:
            cap.release()
            detector.close()

    def _run_mock(self) -> None:
        source = MockCameraSource()
        source.start()
        try:
            while self._running:
                frame = source.get_frame()
                ear_left, ear_right, ear_avg = source.get_ear()
                self._emit_analysis(frame, ear_left, ear_right, ear_avg)
                self.msleep(33)  # ~30 fps, matches the real camera loop's pace
        finally:
            source.stop()

    def _emit_analysis(
        self,
        frame,
        ear_left: float | None,
        ear_right: float | None,
        ear_avg: float | None,
    ) -> None:
        perclos = self._perclos.update(ear_avg)
        status = "drowsy" if self._perclos.is_drowsy(perclos) else "normal"

        self.frame_ready.emit(frame)
        self.analysis_ready.emit(
            ear_left or 0.0,
            ear_right or 0.0,
            ear_avg or 0.0,
            perclos,
            status,
        )

        if self._recording:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._recorder.write_row(ts, ear_left, ear_right, ear_avg, perclos, status, face_detected=ear_avg is not None)
