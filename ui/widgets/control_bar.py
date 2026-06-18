from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ControlBar(QWidget):
    camera_toggled = Signal(bool)
    eeg_toggled = Signal(bool)
    session_toggled = Signal(bool)
    record_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._camera_btn = QPushButton("Connect Camera")
        self._camera_btn.setCheckable(True)
        self._camera_btn.toggled.connect(self._on_camera_toggled)

        self._eeg_btn = QPushButton("Connect EEG")
        self._eeg_btn.setCheckable(True)
        self._eeg_btn.toggled.connect(self._on_eeg_toggled)

        self._record_btn = QPushButton("Start Recording")
        self._record_btn.setCheckable(True)
        self._record_btn.setEnabled(False)
        self._record_btn.toggled.connect(self._on_record_toggled)

        self._session_btn = QPushButton("Start Monitoring")
        self._session_btn.setObjectName("primaryButton")
        self._session_btn.setCheckable(True)
        self._session_btn.toggled.connect(self._on_session_toggled)

        layout = QHBoxLayout(self)
        layout.addWidget(self._camera_btn)
        layout.addWidget(self._eeg_btn)
        layout.addWidget(self._record_btn)
        layout.addStretch(1)
        layout.addWidget(self._session_btn)

    def set_record_enabled(self, enabled: bool) -> None:
        self._record_btn.setEnabled(enabled)
        if not enabled:
            self._record_btn.setChecked(False)

    def set_eeg_connected(self, connected: bool) -> None:
        self._eeg_btn.blockSignals(True)
        self._eeg_btn.setChecked(connected)
        self._eeg_btn.setText("Disconnect EEG" if connected else "Connect EEG")
        self._eeg_btn.blockSignals(False)

    def _on_camera_toggled(self, checked: bool) -> None:
        self._camera_btn.setText("Disconnect Camera" if checked else "Connect Camera")
        self.camera_toggled.emit(checked)

    def _on_eeg_toggled(self, checked: bool) -> None:
        self._eeg_btn.setText("Disconnect EEG" if checked else "Connect EEG")
        self.eeg_toggled.emit(checked)

    def _on_record_toggled(self, checked: bool) -> None:
        self._record_btn.setText("Stop Recording" if checked else "Start Recording")
        self.record_toggled.emit(checked)

    def _on_session_toggled(self, checked: bool) -> None:
        self._session_btn.setText("Stop Monitoring" if checked else "Start Monitoring")
        self.session_toggled.emit(checked)
