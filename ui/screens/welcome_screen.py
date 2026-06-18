import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WelcomeScreen(QWidget):
    start_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("Neuralise")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Drowsiness Detection — EEG + Camera Monitoring")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "Sebelum memulai sesi, Anda akan diminta mengisi kuesioner DASS-21 "
            "sebagai kriteria inklusi subjek penelitian."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        start_btn = QPushButton("Mulai Sesi")
        start_btn.setObjectName("primaryButton")
        start_btn.setFixedWidth(220)
        start_btn.clicked.connect(self.start_clicked)

        report_btn = QPushButton("Unduh Laporan")
        report_btn.setFixedWidth(220)
        report_btn.clicked.connect(self._on_report)

        layout = QVBoxLayout(self)
        layout.addStretch(2)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(desc)
        layout.addSpacing(40)
        layout.addWidget(start_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(report_btn, alignment=Qt.AlignmentFlag.AlignCenter)
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
