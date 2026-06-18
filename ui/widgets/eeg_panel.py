import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.sources.base import EEGSource

REFRESH_MS = 33
WINDOW_SECONDS = 5
CHANNEL_COLORS = ["#4dd2ff", "#7fff8a", "#ffd24d", "#ff7f7f"]
CHANNEL_SPACING = 6.0


class EEGPanel(QWidget):
    """Scrolling multi-channel EEG plot. Swap the source later for a real headset stream."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: EEGSource | None = None
        self._buffers: list[np.ndarray] = []
        self._curves: list[pg.PlotDataItem] = []

        pg.setConfigOptions(antialias=True)
        self._plot = pg.PlotWidget(background="#11161d")
        self._plot.showGrid(x=True, y=False, alpha=0.2)
        self._plot.setLabel("bottom", "time", units="s")
        self._plot.getAxis("left").hide()
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.addLegend(offset=(10, 10))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

    def set_source(self, source: EEGSource | None) -> None:
        self.stop()
        self._plot.clear()
        self._curves = []
        self._buffers = []
        self._source = source
        if source is None:
            return

        n_channels = len(source.channel_names)
        n_points = int(WINDOW_SECONDS * source.sample_rate)
        self._buffers = [np.zeros(n_points, dtype=np.float32) for _ in range(n_channels)]
        for i, name in enumerate(source.channel_names):
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            curve = self._plot.plot(pen=pg.mkPen(color, width=1.5), name=name)
            self._curves.append(curve)

    def start(self) -> None:
        if self._source is None:
            return
        self._source.start()
        self._timer.start(REFRESH_MS)

    def stop(self) -> None:
        self._timer.stop()
        if self._source is not None:
            self._source.stop()

    def _refresh(self) -> None:
        if self._source is None:
            return
        samples = self._source.get_samples()
        if samples is None or samples.shape[1] == 0:
            return

        n_new = samples.shape[1]
        for i, curve in enumerate(self._curves):
            buf = self._buffers[i]
            buf = np.roll(buf, -n_new)
            buf[-n_new:] = samples[i]
            self._buffers[i] = buf
            offset = (len(self._curves) - i) * CHANNEL_SPACING
            curve.setData(buf + offset)
