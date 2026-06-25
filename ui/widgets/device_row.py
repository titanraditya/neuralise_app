from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class DeviceRow(QWidget):
    """Top bar: persistent camera/EEG connect controls at the rig level (DeviceManager-backed).

    Connecting/disconnecting here is independent of any recording Session — devices keep
    streaming for live preview whether or not a session is currently active.
    """

    camera_toggled = Signal(bool)
    eeg_toggled = Signal(bool)
    calibrate_eeg_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlBar")

        self._camera_btn = QPushButton("Connect Camera")
        self._camera_btn.setCheckable(True)
        self._camera_btn.toggled.connect(self._on_camera_toggled)

        self._eeg_btn = QPushButton("Connect EEG")
        self._eeg_btn.setCheckable(True)
        self._eeg_btn.toggled.connect(self._on_eeg_toggled)

        # Calibration is manual-only — never an automatic side effect of connecting or
        # starting a session — so the subject can get settled before the 30s baseline starts.
        self._calibrate_btn = QPushButton("Kalibrasi EEG")
        self._calibrate_btn.setEnabled(False)
        self._calibrate_btn.clicked.connect(self.calibrate_eeg_clicked)

        self._eeg_contact_label = QLabel("Kontak EEG: –")
        self._eeg_contact_label.setObjectName("contactLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)
        layout.addWidget(self._camera_btn)
        layout.addWidget(self._eeg_btn)
        layout.addWidget(self._calibrate_btn)
        layout.addWidget(self._eeg_contact_label)
        layout.addStretch(1)

    def set_camera_connected(self, connected: bool) -> None:
        self._camera_btn.blockSignals(True)
        self._camera_btn.setChecked(connected)
        self._camera_btn.setText("Disconnect Camera" if connected else "Connect Camera")
        self._camera_btn.blockSignals(False)

    def set_eeg_connected(self, connected: bool) -> None:
        self._eeg_btn.blockSignals(True)
        self._eeg_btn.setChecked(connected)
        self._eeg_btn.setText("Disconnect EEG" if connected else "Connect EEG")
        self._eeg_btn.blockSignals(False)
        self._calibrate_btn.setEnabled(connected)
        if not connected:
            self.set_eeg_contact_text("Kontak EEG: –")

    def set_eeg_connecting(self, connecting: bool) -> None:
        """Disable the button while a connect attempt is in flight on the worker thread —
        the eventual eeg_connected_changed/eeg_connect_failed signal sets the final text."""
        self._eeg_btn.setEnabled(not connecting)
        if connecting:
            self._eeg_btn.setText("Menghubungkan EEG…")

    def set_eeg_contact_text(self, text: str) -> None:
        self._eeg_contact_label.setText(text)

    def _on_camera_toggled(self, checked: bool) -> None:
        self._camera_btn.setText("Disconnect Camera" if checked else "Connect Camera")
        self.camera_toggled.emit(checked)

    def _on_eeg_toggled(self, checked: bool) -> None:
        self._eeg_btn.setText("Disconnect EEG" if checked else "Connect EEG")
        self.eeg_toggled.emit(checked)
