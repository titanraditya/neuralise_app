from PySide6.QtCore import QTime, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.effects import apply_card_shadow
from ui.widgets.camera_panel import CameraPanel
from ui.widgets.device_row import DeviceRow
from ui.widgets.eeg_panel import EEGPanel
from ui.widgets.history_drawer import HistoryDrawer
from ui.widgets.session_strip import SessionControlStrip
from ui.widgets.status_panel import StatusPanel


def _section(label: str, widget: QWidget) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    caption = QLabel(label)
    caption.setObjectName("sectionLabel")
    layout.addWidget(caption)
    layout.addWidget(widget, stretch=1)
    return container


class MainScreen(QWidget):
    """Single screen, two modes (SIAP / SESI AKTIF) — replaces the old 4-page wizard.

    Pure composition + child widgets exposed as public attributes; DeviceManager/Session
    lifecycle and signal wiring live in MainWindow.
    """

    history_toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.device_row = DeviceRow()
        apply_card_shadow(self.device_row)

        self.camera_panel = CameraPanel()
        self.eeg_panel = EEGPanel()
        self.status_panel = StatusPanel()

        self.control_strip = SessionControlStrip()
        apply_card_shadow(self.control_strip)

        self.history_drawer = HistoryDrawer()
        apply_card_shadow(self.history_drawer)
        self.history_drawer.setVisible(False)

        self._clock_label = QLabel()
        self._clock_label.setObjectName("clockLabel")
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)
        self._update_clock()

        main_column = QVBoxLayout()
        main_column.setContentsMargins(0, 0, 0, 0)
        main_column.setSpacing(14)
        main_column.addWidget(self._build_header())
        main_column.addWidget(self.device_row)

        content = QHBoxLayout()
        content.setSpacing(16)
        content.addWidget(_section("Camera", self.camera_panel), stretch=3)

        right_column = QVBoxLayout()
        right_column.setSpacing(16)
        right_column.addWidget(_section("EEG Signal", self.eeg_panel), stretch=2)
        right_column.addWidget(_section("Status", self.status_panel), stretch=1)
        content.addLayout(right_column, stretch=2)

        content_widget = QWidget()
        content_widget.setLayout(content)

        # Camera/EEG/Status want a fairly tall minimum size to stay legible. On a short screen
        # that no longer fits, so this scrolls instead of pushing control_strip off-screen below.
        content_scroll = QScrollArea()
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setWidget(content_widget)

        main_column.addWidget(content_scroll, stretch=1)
        main_column.addWidget(self.control_strip)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        root.addLayout(main_column, stretch=1)
        root.addWidget(self.history_drawer)

    def _build_header(self) -> QWidget:
        title_box = QVBoxLayout()
        title = QLabel("Neuralise")
        title.setObjectName("appTitle")
        subtitle = QLabel("Drowsiness Detection — EEG + Camera Monitoring")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        history_btn = QPushButton("Riwayat")
        history_btn.clicked.connect(self.history_toggle_requested)

        header_bar = QFrame()
        header_bar.setObjectName("headerBar")
        apply_card_shadow(header_bar)
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(16, 12, 16, 12)
        header.addLayout(title_box)
        header.addStretch(1)
        header.addWidget(history_btn)
        header.addWidget(self._clock_label, alignment=Qt.AlignmentFlag.AlignRight)
        return header_bar

    def _update_clock(self) -> None:
        self._clock_label.setText(QTime.currentTime().toString("hh:mm:ss"))
