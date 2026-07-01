import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from ui.effects import apply_card_shadow

NOT_CONNECTED_MESSAGE = 'EOG belum terhubung — klik "Connect EOG" untuk mulai streaming.'
STATUS_COLORS = {
    "idle": "#6b7585",
    "calibrating": "#d97706",
    "awake": "#1f9d55",
    "drowsy": "#d6453d",
}
STATUS_LABELS = {
    "idle": "Idle",
    "calibrating": "Kalibrasi",
    "awake": "Awake",
    "drowsy": "Drowsy",
}


class EOGPanel(QWidget):
    """Single-channel (A1) EOG plot + blink rate / EOG-PERCLOS metrics.

    Pure renderer: DeviceManager owns the EOG source/connection/polling and pushes
    ready-to-draw data in via set_channels()/update_frame()/update_metrics()/set_status().
    Reported standalone — this status never feeds the camera+EEG OR-rule in status_panel.py.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sample_rate = 0.0  # set by set_channels(); 0 => plot against sample index
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._plot = pg.PlotWidget(background="#ffffff")
        self._plot.setObjectName("eegPlot")
        self._plot.setMinimumHeight(110)
        self._plot.showGrid(x=True, y=False, alpha=0.15)
        self._plot.setLabel("bottom", "time", units="s")
        self._plot.getAxis("left").hide()
        self._plot.setMouseEnabled(x=False, y=False)
        apply_card_shadow(self._plot)
        self._curve = self._plot.plot(pen=pg.mkPen("#2f6fed", width=1.5))
        self._curve.setDownsampling(auto=True, method="peak")
        self._curve.setClipToView(True)

        self._blink_label = QLabel("Blink rate: –")
        self._perclos_label = QLabel("EOG-PERCLOS: –")
        self._status_label = QLabel("Idle")
        self._status_label.setObjectName("contactLabel")

        metrics_row = QHBoxLayout()
        metrics_row.addWidget(self._blink_label)
        metrics_row.addWidget(self._perclos_label)
        metrics_row.addStretch(1)
        metrics_row.addWidget(self._status_label)
        metrics_row_widget = QWidget()
        metrics_row_widget.setLayout(metrics_row)

        self._placeholder = QLabel(NOT_CONNECTED_MESSAGE)
        self._placeholder.setObjectName("cameraView")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        apply_card_shadow(self._placeholder)

        self._live_widget = QWidget()
        live_layout = QVBoxLayout(self._live_widget)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.addWidget(metrics_row_widget)
        live_layout.addWidget(self._plot, stretch=1)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._live_widget)
        self._stack.setCurrentWidget(self._placeholder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack, stretch=1)

    def set_channels(self, channel_names: list[str], sample_rate: float = 0.0) -> None:
        """(Re)build the view for a fresh EOG connection. Call with [] on disconnect."""
        self._sample_rate = sample_rate
        self._curve.setData([])
        self._blink_label.setText("Blink rate: –")
        self._perclos_label.setText("EOG-PERCLOS: –")
        self._status_label.setText("Idle")
        self._status_label.setStyleSheet(f"color: {STATUS_COLORS['idle']}; font-weight: 600;")
        if not channel_names:
            self._stack.setCurrentWidget(self._placeholder)
            return
        self._stack.setCurrentWidget(self._live_widget)

    def update_frame(self, segment) -> None:
        if self._sample_rate > 0:
            # Plot against real seconds (0..window) so the bottom axis reads in s, not the
            # raw sample index that pyqtgraph was SI-prefixing into "ks".
            x = np.arange(len(segment)) / self._sample_rate
            self._curve.setData(x, segment)
        else:
            self._curve.setData(segment)

    def update_metrics(self, blink_rate: float, eog_perclos: float) -> None:
        self._blink_label.setText(f"Blink rate: {blink_rate:.1f}/min")
        self._perclos_label.setText(f"EOG-PERCLOS: {eog_perclos * 100:.1f}%")

    def set_status(self, status: str, detail: str = "") -> None:
        label = STATUS_LABELS.get(status, status)
        text = f"{label} ({detail})" if detail else label
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {STATUS_COLORS.get(status, '#6b7585')}; font-weight: 600;"
        )
