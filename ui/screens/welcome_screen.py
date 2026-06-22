import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.effects import apply_card_shadow


class WelcomeScreen(QWidget):
    start_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        badge = QLabel("N")
        badge.setObjectName("heroBadge")
        badge.setFixedSize(56, 56)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tag = QLabel("Penelitian Drowsiness")
        tag.setObjectName("welcomeTag")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Neuralise")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Drowsiness Detection — EEG + Camera Monitoring")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "Sebelum memulai sesi, Anda akan diminta mengisi kuesioner DASS-21 "
            "sebagai kriteria inklusi subjek penelitian."
        )
        desc.setObjectName("welcomeDesc")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        start_btn = QPushButton("Mulai Sesi")
        start_btn.setObjectName("primaryButton")
        start_btn.setFixedWidth(220)
        start_btn.clicked.connect(self.start_clicked)

        report_btn = QPushButton("Unduh Laporan")
        report_btn.setFixedWidth(220)
        report_btn.clicked.connect(self._on_report)

        card = QFrame()
        card.setObjectName("heroCard")
        card.setFixedWidth(440)
        apply_card_shadow(card, blur_radius=36, y_offset=10, alpha=35)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(0)
        card_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(16)
        card_layout.addWidget(tag, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(14)
        card_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(18)
        card_layout.addWidget(desc)
        card_layout.addSpacing(30)
        card_layout.addWidget(start_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addSpacing(10)
        card_layout.addWidget(report_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        center_row.addWidget(card)
        center_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addStretch(2)
        layout.addLayout(center_row)
        layout.addStretch(3)

    def _on_report(self) -> None:
        recordings = Path("recordings")
        if not recordings.exists() or not any(recordings.iterdir()):
            QMessageBox.information(self, "Laporan", "Belum ada data rekaman.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Laporan", "laporan_neuralise.zip", "ZIP Archive (*.zip)"
        )
        if not path:
            return

        files = list(recordings.iterdir())
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if f.is_file():
                    zf.write(f, f.name)

        QMessageBox.information(
            self, "Laporan Tersimpan", f"{len(files)} file disimpan ke:\n{path}"
        )
