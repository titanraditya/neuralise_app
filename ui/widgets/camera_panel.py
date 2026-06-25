import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.effects import apply_card_shadow


class CameraPanel(QWidget):
    """Renders frames pushed in via update_frame(); DeviceManager owns the actual camera feed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._view = QLabel("No camera connected")
        self._view.setObjectName("cameraView")
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumSize(360, 240)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        apply_card_shadow(self._view)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def set_active(self, active: bool) -> None:
        """Marks the externally-driven feed (DeviceManager) as live or stopped.

        Frames delivered via update_frame() while inactive are ignored — this guards
        against a straggler frame_ready signal arriving after the producer thread has
        already been told to stop but before its last queued emit is processed.
        """
        self._active = active

    def update_frame(self, frame) -> None:
        if not self._active:
            return
        self._set_frame(frame)

    def clear(self) -> None:
        self._active = False
        self._view.setPixmap(QPixmap())
        self._view.setText("No camera connected")

    def _set_frame(self, frame) -> None:
        pixmap = self._frame_to_pixmap(frame).scaled(
            self._view.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._view.setPixmap(pixmap)

    @staticmethod
    def _frame_to_pixmap(frame: np.ndarray) -> QPixmap:
        frame = np.ascontiguousarray(frame)
        height, width, channels = frame.shape
        image = QImage(frame.data, width, height, channels * width, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(image)
