from PySide6.QtCore import QTime, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from camera.camera_thread import CameraThread
from core.sources.muse import MuseEEGSource
from ui.screens.questionnaire_screen import QuestionnaireScreen
from ui.screens.welcome_screen import WelcomeScreen
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

        self._camera_thread: CameraThread | None = None

        # Panels (shared across monitoring widget)
        self._camera_panel = CameraPanel()
        self._eeg_panel = EEGPanel()
        self._status_panel = StatusPanel()
        self._control_bar = ControlBar()
        self._clock_label = QLabel()

        # Screens
        self._welcome = WelcomeScreen()
        self._questionnaire = QuestionnaireScreen()
        self._monitoring = self._build_monitoring_widget()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._welcome)       # 0
        self._stack.addWidget(self._questionnaire) # 1
        self._stack.addWidget(self._monitoring)    # 2

        self.setCentralWidget(self._stack)

        # Navigation
        self._welcome.start_clicked.connect(lambda: self._stack.setCurrentIndex(1))
        self._questionnaire.completed.connect(self._on_questionnaire_done)

        self._wire_controls()

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _build_monitoring_widget(self) -> QWidget:
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)
        self._update_clock()

        widget = QWidget()
        root = QVBoxLayout(widget)
        root.addLayout(self._build_header())

        content = QHBoxLayout()
        content.addWidget(_section("Camera", self._camera_panel), stretch=3)

        right_column = QVBoxLayout()
        right_column.addWidget(_section("EEG Signal", self._eeg_panel), stretch=2)
        right_column.addWidget(_section("Status", self._status_panel), stretch=1)
        content.addLayout(right_column, stretch=2)

        root.addLayout(content, stretch=1)
        root.addWidget(self._control_bar)
        return widget

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

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_controls(self) -> None:
        self._control_bar.camera_toggled.connect(self._on_camera_toggled)
        self._control_bar.eeg_toggled.connect(self._on_eeg_toggled)
        self._control_bar.session_toggled.connect(self._on_session_toggled)
        self._control_bar.record_toggled.connect(self._on_record_toggled)

    # ------------------------------------------------------------------
    # Navigation handlers
    # ------------------------------------------------------------------

    def _on_questionnaire_done(self, _data: dict) -> None:
        self._questionnaire.reset()
        self._stack.setCurrentIndex(2)

    # ------------------------------------------------------------------
    # Camera handlers
    # ------------------------------------------------------------------

    def _on_camera_toggled(self, connected: bool) -> None:
        if connected:
            self._camera_thread = CameraThread(self)
            self._camera_thread.frame_ready.connect(self._camera_panel.update_frame)
            self._camera_thread.analysis_ready.connect(self._on_analysis)
            self._camera_thread.recording_saved.connect(self._on_recording_saved)
            self._camera_thread.camera_error.connect(self._on_camera_error)
            self._camera_thread.start_camera()
            self._control_bar.set_record_enabled(True)
        else:
            self._control_bar.set_record_enabled(False)
            if self._camera_thread:
                self._camera_thread.stop_camera()
                self._camera_thread = None
            self._camera_panel.clear()
            self._status_panel.set_status("idle")
            self._status_panel.set_metric("perclos", "--")

    def _on_record_toggled(self, recording: bool) -> None:
        if self._camera_thread is None:
            return
        if recording:
            self._camera_thread.start_recording()
        else:
            self._camera_thread.stop_recording()

    def _on_analysis(
        self,
        _ear_l: float,
        _ear_r: float,
        _ear_avg: float,
        perclos: float,
        status: str,
    ) -> None:
        self._status_panel.set_metric("perclos", f"{perclos * 100:.1f}%")
        self._status_panel.set_status("drowsy" if status == "drowsy" else "awake")

    def _on_recording_saved(self, path: str) -> None:
        QMessageBox.information(self, "Recording Tersimpan", f"CSV disimpan ke:\n{path}")

    def _on_camera_error(self, message: str) -> None:
        self._control_bar.set_record_enabled(False)
        QMessageBox.critical(self, "Camera Error", message)

    # ------------------------------------------------------------------
    # EEG handlers
    # ------------------------------------------------------------------

    def _on_eeg_toggled(self, connected: bool) -> None:
        if connected:
            source = MuseEEGSource()
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            try:
                self._eeg_panel.set_source(source)
                self._eeg_panel.start()
            except Exception as exc:
                self._eeg_panel.set_source(None)
                self._control_bar.set_eeg_connected(False)
                QMessageBox.critical(self, "EEG Connection Error", str(exc))
            finally:
                QApplication.restoreOverrideCursor()
        else:
            self._eeg_panel.set_source(None)

    def _on_session_toggled(self, running: bool) -> None:
        if running:
            self._status_panel.start_session()
        else:
            self._status_panel.stop_session()

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _update_clock(self) -> None:
        self._clock_label.setText(QTime.currentTime().toString("hh:mm:ss"))
