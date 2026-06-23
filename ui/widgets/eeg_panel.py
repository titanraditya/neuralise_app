import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from ui.effects import apply_card_shadow

CHANNEL_COLORS = ["#2f6fed", "#1f9d55", "#d68910", "#d6453d"]
NO_CONTACT_COLOR = "#aab2c0"
CHANNEL_SPACING = 6.0
BAND_NAMES = ["Delta", "Theta", "Alpha", "Beta", "Gamma"]
NOT_CONNECTED_MESSAGE = 'EEG belum terhubung — klik "Connect EEG" untuk mulai streaming.'


class EEGPanel(QWidget):
    """Scrolling multi-channel EEG plot + band-power bars.

    Pure renderer: DeviceManager owns the EEG source/connection/polling and pushes
    ready-to-draw data in via set_channels()/update_frame()/update_bands().
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._channel_names: list[str] = []
        self._curves: list[pg.PlotDataItem] = []
        self._contact_labels: list[QLabel] = []

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # antialias=False: antialiased line rendering for 4 channels x ~1280 points was a
        # major contributor to GUI lag while EEG is connected.
        pg.setConfigOptions(antialias=False, foreground="#5b6573")

        self._contact_row = QHBoxLayout()
        contact_row_widget = QWidget()
        contact_row_widget.setLayout(self._contact_row)

        self._plot = pg.PlotWidget(background="#ffffff")
        self._plot.setObjectName("eegPlot")
        self._plot.setMinimumHeight(180)
        self._plot.showGrid(x=True, y=False, alpha=0.15)
        self._plot.setLabel("bottom", "time", units="s")
        self._plot.getAxis("left").hide()
        self._plot.setMouseEnabled(x=False, y=False)
        self._legend = self._plot.addLegend(offset=(10, 10), labelTextColor="#1c2430")
        apply_card_shadow(self._plot)

        self._band_plot = pg.PlotWidget(background="#ffffff")
        self._band_plot.setObjectName("eegPlot")
        apply_card_shadow(self._band_plot)
        self._band_plot.setMaximumHeight(120)
        self._band_plot.setMinimumHeight(100)
        self._band_plot.setMouseEnabled(x=False, y=False)
        self._band_plot.setLabel("left", "Band power")
        self._band_plot.getAxis("left").enableAutoSIPrefix(False)
        xb = np.arange(len(BAND_NAMES))
        self._band_bar = pg.BarGraphItem(x=xb, height=[0] * len(BAND_NAMES), width=0.6, brush="#2f6fed")
        self._band_plot.addItem(self._band_bar)
        self._band_plot.getAxis("bottom").setTicks([list(zip(xb, BAND_NAMES))])
        self._band_plot.enableAutoRange("y", True)

        self._placeholder = QLabel(NOT_CONNECTED_MESSAGE)
        self._placeholder.setObjectName("cameraView")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        apply_card_shadow(self._placeholder)

        self._live_widget = QWidget()
        live_layout = QVBoxLayout(self._live_widget)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.addWidget(self._plot, stretch=3)
        live_layout.addWidget(self._band_plot, stretch=1)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._live_widget)
        self._stack.setCurrentWidget(self._placeholder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(contact_row_widget)
        layout.addWidget(self._stack, stretch=1)

    def set_channels(self, channel_names: list[str]) -> None:
        """(Re)build the plot for a fresh EEG connection. Call with [] on disconnect."""
        self._plot.clear()
        self._legend.clear()
        self._clear_contact_row()
        self._curves = []
        self._band_bar.setOpts(height=[0] * len(BAND_NAMES))
        self._channel_names = list(channel_names)

        if not self._channel_names:
            self._stack.setCurrentWidget(self._placeholder)
            return
        self._stack.setCurrentWidget(self._live_widget)

        for i, name in enumerate(self._channel_names):
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            curve = self._plot.plot(pen=pg.mkPen(color, width=1.5), name=name)
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)
            self._curves.append(curve)

            label = QLabel(name)
            label.setObjectName("contactLabel")
            self._contact_row.addWidget(label)
            self._contact_labels.append(label)

    def update_frame(self, segments: list, contact_ok: list) -> None:
        for i, curve in enumerate(self._curves):
            if i >= len(segments):
                break
            seg = segments[i]
            ok = contact_ok[i]
            offset = (len(self._curves) - i) * CHANNEL_SPACING
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)] if ok else NO_CONTACT_COLOR
            curve.setPen(pg.mkPen(color, width=1.5))
            # Keep drawing the real (filtered) line even on bad contact — only the color/label
            # changes — so the trace never just goes flat while the headset is being adjusted.
            curve.setData(seg + offset)
            self._set_contact_label(i, ok)

    def update_bands(self, bands: list) -> None:
        self._band_bar.setOpts(height=list(bands))

    def _clear_contact_row(self) -> None:
        while self._contact_row.count():
            item = self._contact_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._contact_labels = []

    def _set_contact_label(self, index: int, ok: bool) -> None:
        label = self._contact_labels[index]
        name = self._channel_names[index]
        if ok:
            label.setText(name)
            label.setStyleSheet("color: #1f9d55; font-weight: 600;")
        else:
            label.setText(f"{name} – NO CONTACT")
            label.setStyleSheet("color: #d6453d; font-weight: 600;")
