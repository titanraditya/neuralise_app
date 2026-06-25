from PySide6.QtCore import QTime, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.effects import apply_card_shadow

STATUS_STYLES = {
    "idle": ("STANDBY", "#7a8699"),
    "calibrating": ("KALIBRASI", "#2f6fed"),
    "awake": ("AWAKE", "#3ddc84"),
    "drowsy": ("DROWSY", "#ffb74d"),
    "critical": ("CRITICAL", "#ff5c5c"),
}

# Final status takes the most urgent state present in either modality (OR rule):
# drowsy if either says drowsy, else awake if either says awake, etc.
_STATUS_PRIORITY = ["drowsy", "awake", "calibrating", "idle"]


def _fuse_status(eeg_status: str, cam_status: str) -> str:
    for status in _STATUS_PRIORITY:
        if eeg_status == status or cam_status == status:
            return status
    return "idle"


class StatusBadge(QFrame):
    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBadgeCard")
        apply_card_shadow(self, blur_radius=16, y_offset=4, alpha=22)
        self.status = "idle"

        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")
        caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._value = QLabel()
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(caption_label)
        layout.addWidget(self._value)

        self.set_status("idle")

    def set_status(self, status: str, detail: str = "") -> None:
        self.status = status
        label, color = STATUS_STYLES.get(status, STATUS_STYLES["idle"])
        self._value.setText(f"{label} {detail}".strip())
        self._value.setStyleSheet(
            f"background-color: {color}; color: #14181f;"
            "font-weight: 700; font-size: 14px; border-radius: 8px; padding: 5px 6px;"
        )


class MetricTile(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricTile")
        apply_card_shadow(self, blur_radius=16, y_offset=4, alpha=22)

        self._value = QLabel("--")
        self._value.setObjectName("metricValue")
        caption = QLabel(label)
        caption.setObjectName("metricCaption")

        layout = QVBoxLayout(self)
        layout.addWidget(self._value, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class StatusPanel(QWidget):
    """EEG and camera drowsiness badges, fused into a final verdict, plus key metrics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._eeg_badge = StatusBadge("EEG")
        self._cam_badge = StatusBadge("Camera")
        self._final_badge = StatusBadge("Final Status")

        self._tiles = {
            "record": MetricTile("Record time"),
            "perclos": MetricTile("PERCLOS"),
        }

        # EEG/Camera badges share a row with the metric tiles — only the fused Final Status
        # gets its own full-width row, to keep it as the most prominent element.
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(self._eeg_badge)
        top_row.addWidget(self._cam_badge)
        top_row.addWidget(self._tiles["record"])
        top_row.addWidget(self._tiles["perclos"])

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addLayout(top_row)
        layout.addWidget(self._final_badge)
        layout.addStretch(1)

        self._record_elapsed = QTime(0, 0, 0)
        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._tick)

    def set_eeg_status(self, status: str, detail: str = "") -> None:
        self._eeg_badge.set_status(status, detail)
        self._recompute_final()

    def set_cam_status(self, status: str) -> None:
        self._cam_badge.set_status(status)
        self._recompute_final()

    def _recompute_final(self) -> None:
        self._final_badge.set_status(_fuse_status(self._eeg_badge.status, self._cam_badge.status))

    def set_metric(self, key: str, text: str) -> None:
        if key in self._tiles:
            self._tiles[key].set_value(text)

    def start_record_timer(self) -> None:
        self._record_elapsed = QTime(0, 0, 0)
        self.set_metric("record", "00:00:00")
        self._record_timer.start(1000)

    def stop_record_timer(self) -> None:
        self._record_timer.stop()

    def _tick(self) -> None:
        self._record_elapsed = self._record_elapsed.addSecs(1)
        self.set_metric("record", self._record_elapsed.toString("hh:mm:ss"))
