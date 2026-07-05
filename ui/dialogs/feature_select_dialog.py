from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.effects import apply_card_shadow

# (key, judul, deskripsi) — key mengikuti core.settings.FEATURE_KEYS.
_FEATURES: list[tuple[str, str, str]] = [
    (
        "camera",
        "Kamera",
        "Deteksi kantuk via webcam — EAR dan PERCLOS (MediaPipe).",
    ),
    (
        "eeg",
        "EEG — Muse S Athena",
        "Band power delta–gamma via BrainFlow, klasifikasi drowsy/awake terhadap baseline.",
    ),
    (
        "museeog",
        "EOG — Muse (AF7)",
        "EOG turunan dari elektrode frontal headset Muse — menumpang koneksi EEG, "
        "jadi butuh fitur EEG aktif.",
    ),
    (
        "eog",
        "EOG — BITalino",
        "Blink rate dan PERCLOS EOG dari OpenSignals via stream LSL.",
    ),
]


class FeatureSelectDialog(QDialog):
    """Menu awal: pilih modalitas mana saja yang dipakai di panel monitoring.

    Fitur yang tidak dicentang disembunyikan dari layar utama (panel, tombol connect, badge
    status) — logika deteksi/fusi tidak diubah, modalitas yang mati sekadar tetap "idle".
    Dipakai dua tempat: saat startup (main.py, sebelum MainWindow) dan dari menu
    Pengaturan → Pilih Fitur Monitoring untuk mengubah pilihan tanpa restart.
    """

    def __init__(
        self,
        features: dict[str, bool],
        startup: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Neuralise — Pilih Fitur Monitoring")
        self.setMinimumWidth(460)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._build_ui(features, startup)

    def _build_ui(self, features: dict[str, bool], startup: bool) -> None:
        header = QLabel("Pilih Fitur Monitoring")
        header.setObjectName("appTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel(
            "Fitur yang tidak dipilih disembunyikan dari panel monitoring.\n"
            "Pilihan disimpan dan bisa diubah lagi lewat menu Pengaturan."
        )
        sub.setObjectName("appSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QGroupBox("Fitur")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(10)

        for key, title, description in _FEATURES:
            checkbox = QCheckBox(title)
            checkbox.setChecked(bool(features.get(key, True)))
            checkbox.toggled.connect(self._on_toggled)
            self._checkboxes[key] = checkbox

            desc = QLabel(description)
            desc.setObjectName("featureDesc")
            desc.setWordWrap(True)

            item = QVBoxLayout()
            item.setSpacing(2)
            item.addWidget(checkbox)
            item.addWidget(desc)
            box_layout.addLayout(item)

        apply_card_shadow(box)

        self._cancel_btn = QPushButton("Keluar" if startup else "Batal")
        self._cancel_btn.setObjectName("ghostButton")
        self._cancel_btn.setFixedWidth(140)
        self._cancel_btn.clicked.connect(self.reject)

        self._start_btn = QPushButton("Mulai" if startup else "Terapkan")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setFixedWidth(180)
        self._start_btn.setDefault(True)
        self._start_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._start_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(8)
        layout.addWidget(header)
        layout.addWidget(sub)
        layout.addSpacing(6)
        layout.addWidget(box)
        layout.addSpacing(6)
        layout.addLayout(btn_row)

        self._sync_constraints()

    def selected_features(self) -> dict[str, bool]:
        return {key: cb.isChecked() for key, cb in self._checkboxes.items()}

    def _on_toggled(self, _checked: bool) -> None:
        self._sync_constraints()

    def _sync_constraints(self) -> None:
        # Muse-EOG menumpang koneksi EEG — tanpa EEG ia tidak bisa dipilih.
        museeog = self._checkboxes["museeog"]
        if not self._checkboxes["eeg"].isChecked():
            museeog.blockSignals(True)
            museeog.setChecked(False)
            museeog.blockSignals(False)
            museeog.setEnabled(False)
        else:
            museeog.setEnabled(True)

        # Minimal satu fitur harus dipilih — tanpa modalitas, layar monitoring kosong.
        any_checked = any(cb.isChecked() for cb in self._checkboxes.values())
        self._start_btn.setEnabled(any_checked)
