import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.sources.base import EEGSource

REFRESH_MS = 33
WINDOW_SECONDS = 5
CHANNEL_COLORS = ["#4dd2ff", "#7fff8a", "#ffd24d", "#ff7f7f"]
NO_CONTACT_COLOR = "#888888"
CHANNEL_SPACING = 6.0
BAND_NAMES = ["Delta", "Theta", "Alpha", "Beta", "Gamma"]
BAND_UPDATE_EVERY_N_FRAMES = round(1000 / REFRESH_MS)  # ~once per second


class EEGPanel(QWidget):
    """Scrolling multi-channel EEG plot with per-channel contact detection and band-power bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: EEGSource | None = None
        self._buffers: list[np.ndarray] = []
        self._curves: list[pg.PlotDataItem] = []
        self._contact_labels: list[QLabel] = []
        self._samples_seen = 0
        self._frame = 0

        pg.setConfigOptions(antialias=True)

        self._contact_row = QHBoxLayout()
        contact_row_widget = QWidget()
        contact_row_widget.setLayout(self._contact_row)

        self._plot = pg.PlotWidget(background="#11161d")
        self._plot.showGrid(x=True, y=False, alpha=0.2)
        self._plot.setLabel("bottom", "time", units="s")
        self._plot.getAxis("left").hide()
        self._plot.setMouseEnabled(x=False, y=False)
        self._legend = self._plot.addLegend(offset=(10, 10))

        self._band_plot = pg.PlotWidget(background="#11161d")
        self._band_plot.setMaximumHeight(120)
        self._band_plot.setMouseEnabled(x=False, y=False)
        self._band_plot.setLabel("left", "Band power")
        xb = np.arange(len(BAND_NAMES))
        self._band_bar = pg.BarGraphItem(x=xb, height=[0] * len(BAND_NAMES), width=0.6, brush="#3273dc")
        self._band_plot.addItem(self._band_bar)
        self._band_plot.getAxis("bottom").setTicks([list(zip(xb, BAND_NAMES))])
        self._band_plot.enableAutoRange("y", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(contact_row_widget)
        layout.addWidget(self._plot, stretch=3)
        layout.addWidget(self._band_plot, stretch=1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

    def set_source(self, source: EEGSource | None) -> None:
        self.stop()
        self._plot.clear()
        self._legend.clear()
        self._clear_contact_row()
        self._curves = []
        self._buffers = []
        self._samples_seen = 0
        self._frame = 0
        self._band_bar.setOpts(height=[0] * len(BAND_NAMES))
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

            label = QLabel(name)
            label.setObjectName("contactLabel")
            self._contact_row.addWidget(label)
            self._contact_labels.append(label)

    def start(self) -> None:
        if self._source is None:
            return
        self._source.start()
        self._timer.start(REFRESH_MS)

    def stop(self) -> None:
        self._timer.stop()
        if self._source is not None:
            self._source.stop()

    def _clear_contact_row(self) -> None:
        while self._contact_row.count():
            item = self._contact_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._contact_labels = []

    def _refresh(self) -> None:
        if self._source is None:
            return
        samples = self._source.get_samples()
        if samples is not None and samples.shape[1] > 0:
            n_new = samples.shape[1]
            self._samples_seen += n_new
            for i in range(len(self._buffers)):
                self._buffers[i] = np.concatenate([self._buffers[i], samples[i]])[-len(self._buffers[i]):]

        # Wait for a full second of real data before trusting filter/contact checks on the
        # zero-initialized buffer (avoids a false "no contact" read at startup).
        warmed_up = self._samples_seen >= self._source.sample_rate
        self._frame += 1
        update_bands = warmed_up and self._frame % BAND_UPDATE_EVERY_N_FRAMES == 0

        good_idx = []
        for i, curve in enumerate(self._curves):
            seg = self._buffers[i]
            offset = (len(self._curves) - i) * CHANNEL_SPACING
            ok = (not warmed_up) or self._source.check_contact(seg)
            if ok:
                good_idx.append(i)
                curve.setPen(pg.mkPen(CHANNEL_COLORS[i % len(CHANNEL_COLORS)], width=1.5))
                y = self._source.filter_for_display(seg) if warmed_up else seg
                curve.setData(y + offset)
            else:
                curve.setPen(pg.mkPen(NO_CONTACT_COLOR, width=1.5))
                curve.setData(np.full_like(seg, offset))
            self._set_contact_label(i, ok)

        if update_bands and good_idx:
            stacked = np.vstack(self._buffers)
            bands = self._source.band_powers(stacked, good_idx)
            if bands is not None:
                self._band_bar.setOpts(height=list(bands))

    def _set_contact_label(self, index: int, ok: bool) -> None:
        label = self._contact_labels[index]
        name = self._source.channel_names[index]
        if ok:
            label.setText(name)
            label.setStyleSheet("color: #7fff8a;")
        else:
            label.setText(f"{name} – NO CONTACT")
            label.setStyleSheet("color: #ff5c5c;")
