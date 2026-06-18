from PySide6.QtCore import QTime, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from core.sources.mock import MockCameraSource, MockEEGSource
from ui.widgets.camera_panel import CameraPanel
from ui.widgets.control_bar import ControlBar
from ui.widgets.eeg_panel import EEGPanel
from ui.widgets.status_panel import StatusPanel


def _section(label: str, widget: QWidget) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    caption = QLabel(label)
    caption.setObjectName("sectionLabel")
    layout.addWidget(caption)
    layout.addWidget(widget)
    return container


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Neuralise — Drowsiness Detection")
        self.resize(1200, 720)

        self._camera_panel = CameraPanel()
        self._eeg_panel = EEGPanel()
        self._status_panel = StatusPanel()
        self._control_bar = ControlBar()

        self._clock_label = QLabel()
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)
        self._update_clock()

        central = QWidget()
        root = QVBoxLayout(central)
        root.addLayout(self._build_header())

        content = QHBoxLayout()
        content.addWidget(_section("Camera", self._camera_panel), stretch=3)

        right_column = QVBoxLayout()
        right_column.addWidget(_section("EEG Signal", self._eeg_panel), stretch=2)
        right_column.addWidget(_section("Status", self._status_panel), stretch=1)
        content.addLayout(right_column, stretch=2)

        root.addLayout(content, stretch=1)
        root.addWidget(self._control_bar)

        self.setCentralWidget(central)
        self._wire_controls()

    def _build_header(self) -> QHBoxLayout:
        title_box = QVBoxLayout()
        title = QLabel("Neuralise")
        title.setObjectName("appTitle")
        subtitle = QLabel("Drowsiness Detection — EEG + Camera Monitoring")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(title_box)
        header.addStretch(1)
        header.addWidget(self._clock_label, alignment=Qt.AlignmentFlag.AlignRight)
        return header

    def _wire_controls(self) -> None:
        self._control_bar.camera_toggled.connect(self._on_camera_toggled)
        self._control_bar.eeg_toggled.connect(self._on_eeg_toggled)
        self._control_bar.session_toggled.connect(self._on_session_toggled)

    def _on_camera_toggled(self, connected: bool) -> None:
        if connected:
            self._camera_panel.set_source(MockCameraSource())
            self._camera_panel.start()
        else:
            self._camera_panel.set_source(None)

    def _on_eeg_toggled(self, connected: bool) -> None:
        if connected:
            self._eeg_panel.set_source(MockEEGSource())
            self._eeg_panel.start()
        else:
            self._eeg_panel.set_source(None)

    def _on_session_toggled(self, running: bool) -> None:
        if running:
            self._status_panel.start_session()
        else:
            self._status_panel.stop_session()

    def _update_clock(self) -> None:
        self._clock_label.setText(QTime.currentTime().toString("hh:mm:ss"))
