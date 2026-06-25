from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QWidget,
)

BADGE_SIAP = (
    "background-color: #7a8699; color: #ffffff; font-weight: 700;"
    "border-radius: 8px; padding: 8px 14px;"
)
BADGE_MEREKAM = (
    "background-color: #d6453d; color: #ffffff; font-weight: 700;"
    "border-radius: 8px; padding: 8px 14px;"
)


class SessionControlStrip(QWidget):
    """Bottom control strip — swaps content per mode, but the recording badge is always visible.

    Mode SIAP: just the "Sesi Baru" button.
    Mode SESI AKTIF: session_id + editable subject_code (nama) + Rekam + Selesai.
    """

    new_session_clicked = Signal()
    record_toggled = Signal(bool)
    selesai_clicked = Signal()
    subject_code_changed = Signal(str)
    dass21_clicked = Signal()
    sart_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlBar")

        # --- mode SIAP ---
        self._new_session_btn = QPushButton("Sesi Baru")
        self._new_session_btn.setObjectName("primaryButton")
        self._new_session_btn.clicked.connect(self.new_session_clicked)

        siap_widget = QWidget()
        siap_layout = QHBoxLayout(siap_widget)
        siap_layout.setContentsMargins(0, 0, 0, 0)
        siap_layout.addWidget(self._new_session_btn)
        siap_layout.addStretch(1)

        # --- mode SESI AKTIF ---
        self._session_id_label = QLabel()
        self._session_id_label.setStyleSheet("font-weight: 700;")

        self._subject_edit = QLineEdit()
        self._subject_edit.setPlaceholderText("Nama (opsional)")
        self._subject_edit.editingFinished.connect(
            lambda: self.subject_code_changed.emit(self._subject_edit.text())
        )

        self._dass21_btn = QPushButton("DASS-21")
        self._dass21_btn.clicked.connect(self.dass21_clicked)

        self._sart_btn = QPushButton("SART")
        self._sart_btn.clicked.connect(self.sart_clicked)

        self._record_btn = QPushButton("Rekam")
        self._record_btn.setObjectName("primaryButton")
        self._record_btn.setCheckable(True)
        self._record_btn.toggled.connect(self._on_record_toggled)

        self._selesai_btn = QPushButton("Selesai")
        self._selesai_btn.setObjectName("selesaiButton")
        self._selesai_btn.clicked.connect(self.selesai_clicked)

        aktif_widget = QWidget()
        aktif_layout = QHBoxLayout(aktif_widget)
        aktif_layout.setContentsMargins(0, 0, 0, 0)
        aktif_layout.setSpacing(10)
        aktif_layout.addWidget(self._session_id_label)
        aktif_layout.addWidget(self._subject_edit)
        aktif_layout.addStretch(1)
        aktif_layout.addWidget(self._dass21_btn)
        aktif_layout.addWidget(self._sart_btn)
        aktif_layout.addWidget(self._record_btn)
        aktif_layout.addWidget(self._selesai_btn)

        self._mode_stack = QStackedWidget()
        self._mode_stack.addWidget(siap_widget)   # 0
        self._mode_stack.addWidget(aktif_widget)  # 1

        self._recording_badge = QLabel()
        self._set_badge(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(14)
        layout.addWidget(self._mode_stack, stretch=1)
        layout.addWidget(self._recording_badge)

        self.set_mode("siap")

    def set_mode(self, mode: str) -> None:
        self._mode_stack.setCurrentIndex(0 if mode == "siap" else 1)
        if mode == "siap":
            self.set_recording(False)

    def set_session_id(self, session_id: str) -> None:
        self._session_id_label.setText(session_id)

    def set_subject_code(self, text: str) -> None:
        self._subject_edit.setText(text)

    def set_recording(self, recording: bool) -> None:
        self._record_btn.blockSignals(True)
        self._record_btn.setChecked(recording)
        self._record_btn.setText("Stop Rekam" if recording else "Rekam")
        self._record_btn.blockSignals(False)
        self._set_badge(recording)

    def _set_badge(self, recording: bool) -> None:
        self._recording_badge.setText("● MEREKAM" if recording else "SIAP")
        self._recording_badge.setStyleSheet(BADGE_MEREKAM if recording else BADGE_SIAP)

    def _on_record_toggled(self, checked: bool) -> None:
        self._record_btn.setText("Stop Rekam" if checked else "Rekam")
        self._set_badge(checked)
        self.record_toggled.emit(checked)
