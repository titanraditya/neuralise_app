from PySide6.QtCore import QTime, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

STATUS_STYLES = {
    "idle": ("STANDBY", "#7a8699"),
    "awake": ("AWAKE", "#3ddc84"),
    "drowsy": ("DROWSY", "#ffb74d"),
    "critical": ("CRITICAL", "#ff5c5c"),
}


class MetricTile(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricTile")

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
    """Drowsiness status badge + key metrics. Detection logic will feed real values in later."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._badge = QLabel(STATUS_STYLES["idle"][0])
        self._badge.setObjectName("statusBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_badge_color(STATUS_STYLES["idle"][1])

        self._tiles = {
            "session": MetricTile("Session time"),
            "blink_rate": MetricTile("Blink rate (bpm)"),
            "perclos": MetricTile("PERCLOS"),
            "alerts": MetricTile("Alerts triggered"),
        }

        grid = QGridLayout()
        grid.addWidget(self._tiles["session"], 0, 0)
        grid.addWidget(self._tiles["blink_rate"], 0, 1)
        grid.addWidget(self._tiles["perclos"], 1, 0)
        grid.addWidget(self._tiles["alerts"], 1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._badge)
        layout.addLayout(grid)
        layout.addStretch(1)

        self._elapsed = QTime(0, 0, 0)
        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._tick)

    def set_status(self, status: str) -> None:
        label, color = STATUS_STYLES.get(status, STATUS_STYLES["idle"])
        self._badge.setText(label)
        self._apply_badge_color(color)

    def set_metric(self, key: str, text: str) -> None:
        if key in self._tiles:
            self._tiles[key].set_value(text)

    def start_session(self) -> None:
        self._elapsed = QTime(0, 0, 0)
        self.set_metric("session", "00:00:00")
        self._session_timer.start(1000)
        self.set_status("awake")

    def stop_session(self) -> None:
        self._session_timer.stop()
        self.set_status("idle")

    def _tick(self) -> None:
        self._elapsed = self._elapsed.addSecs(1)
        self.set_metric("session", self._elapsed.toString("hh:mm:ss"))

    def _apply_badge_color(self, color: str) -> None:
        self._badge.setStyleSheet(
            f"background-color: {color}; color: #0b0e13;"
            "font-weight: 700; font-size: 16px; border-radius: 6px; padding: 10px;"
        )
