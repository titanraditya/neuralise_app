import datetime
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# (nomor, teks pertanyaan, subscale: D/A/S)
QUESTIONS: list[tuple[int, str, str]] = [
    (1,  "Saya merasa bahwa diri saya menjadi marah karena hal-hal sepele.", "S"),
    (2,  "Saya merasa mulut saya sering kering.", "A"),
    (3,  "Saya sama sekali tidak dapat merasakan perasaan positif.", "D"),
    (4,  "Saya mengalami kesulitan bernafas (misalnya: sering kali terengah-engah atau tidak dapat bernafas padahal tidak melakukan aktivitas fisik sebelumnya).", "A"),
    (5,  "Saya sepertinya tidak kuat lagi untuk melakukan suatu kegiatan.", "D"),
    (6,  "Saya cenderung bereaksi berlebihan terhadap suatu situasi.", "S"),
    (7,  "Saya merasa gemetar (misalnya: pada tangan).", "A"),
    (8,  "Saya merasa telah menghabiskan banyak energi disaat merasa cemas.", "S"),
    (9,  "Saya merasa khawatir dengan situasi dimana saya mungkin menjadi panik dan mempermalukan diri sendiri.", "A"),
    (10, "Saya merasa tidak ada hal yang dapat diharapkan di masa depan.", "D"),
    (11, "Saya sedang merasa gelisah.", "S"),
    (12, "Saya merasa sulit untuk bersantai.", "S"),
    (13, "Saya merasa sedih dan tertekan.", "D"),
    (14, "Saya sulit untuk sabar dalam menghadapi gangguan terhadap hal yang sedang saya lakukan.", "S"),
    (15, "Saya merasa saya hampir panik.", "A"),
    (16, "Saya tidak merasa antusias dalam hal apapun.", "D"),
    (17, "Saya merasa bahwa saya tidak berharga sebagai seorang manusia.", "D"),
    (18, "Saya merasa bahwa saya mudah tersinggung.", "S"),
    (19, "Saya menyadari perubahan detak jantung, walaupun tidak sehabis melakukan aktivitas fisik (misalnya: merasa detak jantung meningkat atau melemah).", "A"),
    (20, "Saya merasa takut tanpa alasan yang jelas.", "A"),
    (21, "Saya merasa bahwa hidup tidak bermanfaat.", "D"),
]

SUBSCALE_ITEMS: dict[str, list[int]] = {
    "D": [3, 5, 10, 13, 16, 17, 21],
    "A": [2, 4, 7, 9, 15, 19, 20],
    "S": [1, 6, 8, 11, 12, 14, 18],
}

LEVEL_RANGES: dict[str, list[tuple[int, int, str]]] = {
    "D": [(0, 9, "Normal"), (10, 13, "Ringan"), (14, 20, "Sedang"), (21, 27, "Berat"), (28, 999, "Sangat Berat")],
    "A": [(0, 7, "Normal"), (8, 9, "Ringan"), (10, 14, "Sedang"), (15, 19, "Berat"), (20, 999, "Sangat Berat")],
    "S": [(0, 7, "Normal"), (8, 9, "Ringan"), (10, 12, "Sedang"), (13, 16, "Berat"), (17, 999, "Sangat Berat")],
}


def _get_level(score: int, subscale: str) -> str:
    for lo, hi, name in LEVEL_RANGES[subscale]:
        if lo <= score <= hi:
            return name
    return "Sangat Berat"


class QuestionnaireScreen(QWidget):
    completed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._groups: list[QButtonGroup] = []
        self._build_ui()

    def _build_ui(self) -> None:
        header = QLabel("Kuesioner DASS-21")
        header.setObjectName("appTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Depression Anxiety Stress Scale")
        sub.setObjectName("appSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- scroll area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setSpacing(16)

        # Identity fields
        id_box = QGroupBox("Data Responden")
        id_form = QFormLayout(id_box)

        self._nama = QLineEdit()
        self._usia = QLineEdit()
        self._kelamin = QComboBox()
        self._kelamin.addItems(["Laki-laki", "Perempuan"])
        self._level_noise = QLineEdit()
        self._content_noise = QLineEdit()

        id_form.addRow("Nama:", self._nama)
        id_form.addRow("Usia:", self._usia)
        id_form.addRow("Jenis Kelamin:", self._kelamin)
        id_form.addRow("Level Noise:", self._level_noise)
        id_form.addRow("Content Noise:", self._content_noise)
        cl.addWidget(id_box)

        # Instructions
        instr = QLabel(
            "Petunjuk: Pilih angka yang paling sesuai dengan pengalaman Anda selama satu minggu belakangan ini.\n"
            "0 = Tidak sesuai sama sekali  |  1 = Kadang-kadang  |  2 = Lumayan sering  |  3 = Sering sekali"
        )
        instr.setWordWrap(True)
        cl.addWidget(instr)

        # Questions grid
        q_box = QGroupBox("Pertanyaan")
        q_grid = QGridLayout(q_box)
        q_grid.setColumnStretch(1, 1)

        for col, lbl in enumerate(["No.", "Pertanyaan", "0", "1", "2", "3"]):
            h = QLabel(f"<b>{lbl}</b>")
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            q_grid.addWidget(h, 0, col)

        for row, (num, text, _subscale) in enumerate(QUESTIONS, start=1):
            group = QButtonGroup(self)
            self._groups.append(group)

            q_grid.addWidget(QLabel(str(num)), row, 0, Qt.AlignmentFlag.AlignCenter)

            q_lbl = QLabel(text)
            q_lbl.setWordWrap(True)
            q_grid.addWidget(q_lbl, row, 1)

            for val in range(4):
                rb = QRadioButton()
                group.addButton(rb, val)
                q_grid.addWidget(rb, row, 2 + val, Qt.AlignmentFlag.AlignCenter)

        cl.addWidget(q_box)

        self._submit_btn = QPushButton("Selesai")
        self._submit_btn.setObjectName("primaryButton")
        self._submit_btn.setFixedWidth(200)
        self._submit_btn.clicked.connect(self._on_submit)
        cl.addWidget(self._submit_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        cl.addSpacing(16)

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.addWidget(header)
        outer.addWidget(sub)
        outer.addSpacing(8)
        outer.addWidget(scroll, stretch=1)

    def reset(self) -> None:
        self._nama.clear()
        self._usia.clear()
        self._kelamin.setCurrentIndex(0)
        self._level_noise.clear()
        self._content_noise.clear()
        for group in self._groups:
            checked = group.checkedButton()
            if checked:
                group.setExclusive(False)
                checked.setChecked(False)
                group.setExclusive(True)

    def _on_submit(self) -> None:
        # Validate identity
        if not self._nama.text().strip():
            QMessageBox.warning(self, "Validasi", "Nama tidak boleh kosong.")
            return
        if not self._usia.text().strip():
            QMessageBox.warning(self, "Validasi", "Usia tidak boleh kosong.")
            return

        # Validate all questions answered
        answers: dict[int, int] = {}
        for i, group in enumerate(self._groups, start=1):
            if group.checkedId() == -1:
                QMessageBox.warning(self, "Validasi", f"Pertanyaan nomor {i} belum dijawab.")
                return
            answers[i] = group.checkedId()

        # Calculate scores
        scores = {k: sum(answers[q] for q in items) for k, items in SUBSCALE_ITEMS.items()}
        levels = {k: _get_level(v, k) for k, v in scores.items()}
        all_normal = all(v == "Normal" for v in levels.values())

        result_text = (
            f"Hasil DASS-21:\n\n"
            f"  Depresi   : {scores['D']} → {levels['D']}\n"
            f"  Kecemasan : {scores['A']} → {levels['A']}\n"
            f"  Stres     : {scores['S']} → {levels['S']}\n"
        )

        if not all_normal:
            result_text += "\nSubjek tidak memenuhi kriteria inklusi.\nSemua dimensi harus berada di level Normal."
            QMessageBox.warning(self, "Hasil Kuesioner", result_text)
            return

        result_text += "\nSubjek memenuhi kriteria inklusi. Silakan lanjutkan sesi."
        QMessageBox.information(self, "Hasil Kuesioner", result_text)

        data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "nama": self._nama.text().strip(),
            "usia": self._usia.text().strip(),
            "jenis_kelamin": self._kelamin.currentText(),
            "level_noise": self._level_noise.text().strip(),
            "content_noise": self._content_noise.text().strip(),
            "answers": {str(k): v for k, v in answers.items()},
            "scores": scores,
            "levels": levels,
        }

        # Save alongside recordings
        Path("recordings").mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path("recordings") / f"questionnaire_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.completed.emit(data)
