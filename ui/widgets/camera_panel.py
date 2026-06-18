import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.sources.base import CameraSource

REFRESH_MS = 33  # ~30 fps


class CameraPanel(QWidget):
    """Displays frames pulled from a CameraSource. Swap the source later for a real webcam feed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: CameraSource | None = None

        self._view = QLabel("No camera connected")
        self._view.setObjectName("cameraView")
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumSize(480, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

    def set_source(self, source: CameraSource | None) -> None:
        self.stop()
        self._source = source

    def start(self) -> None:
        if self._source is None:
            return
        self._source.start()
        self._timer.start(REFRESH_MS)

    def stop(self) -> None:
        self._timer.stop()
        if self._source is not None:
            self._source.stop()
        self._view.setText("No camera connected")
        self._view.setPixmap(QPixmap())

    def _refresh(self) -> None:
        if self._source is None:
            return
        frame = self._source.get_frame()
        if frame is None:
            return
        self._view.setPixmap(self._frame_to_pixmap(frame))

    @staticmethod
    def _frame_to_pixmap(frame: np.ndarray) -> QPixmap:
        frame = np.ascontiguousarray(frame)
        height, width, channels = frame.shape
        image = QImage(frame.data, width, height, channels * width, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(image)
