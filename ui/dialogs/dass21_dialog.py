import datetime
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.session import Session
from ui.effects import apply_card_shadow

# (nomor, teks pertanyaan, subscale: D/A/S) — scoring preserved verbatim from the old wizard step.
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


class DASS21Dialog(QDialog):
    """Modal, fully optional DASS-21 questionnaire attached to one Session.

    Writes recordings/<session_id>/dass21.json and flips Session.has_dass21 — it no longer
    gates progress through a wizard, so an out-of-range result is informational only.
    """

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self.setWindowTitle(f"Kuesioner DASS-21 — {session.session_id}")
        self._groups: list[QButtonGroup] = []
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        self.setMinimumSize(720, 600)

        header = QLabel("Kuesioner DASS-21")
        header.setObjectName("appTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Depression Anxiety Stress Scale — opsional, terikat ke sesi ini")
        sub.setObjectName("appSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setSpacing(16)

        id_box = QGroupBox("Data Responden")
        id_form = QFormLayout(id_box)

        # Nama is one-per-Session (satu sesi = satu responden), not re-entered per questionnaire —
        # the only place to set/edit it is the Subject Code field on the session control strip.
        self._nama_label = QLabel(
            self._session.subject_code or "(kosong — isi di Subject Code pada sesi)"
        )
        self._usia = QLineEdit()
        self._kelamin = QComboBox()
        self._kelamin.addItems(["Laki-laki", "Perempuan"])
        self._content_noise = QLineEdit()

        id_form.addRow("Nama:", self._nama_label)
        id_form.addRow("Usia:", self._usia)
        id_form.addRow("Jenis Kelamin:", self._kelamin)
        id_form.addRow("Content Noise:", self._content_noise)
        apply_card_shadow(id_box)
        cl.addWidget(id_box)

        instr = QLabel(
            "Petunjuk: Pilih angka yang paling sesuai dengan pengalaman Anda selama satu minggu belakangan ini.\n"
            "0 = Tidak sesuai sama sekali  |  1 = Kadang-kadang  |  2 = Lumayan sering  |  3 = Sering sekali"
        )
        instr.setWordWrap(True)
        cl.addWidget(instr)

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

        apply_card_shadow(q_box)
        cl.addWidget(q_box)

        self._close_btn = QPushButton("Tutup")
        self._close_btn.setObjectName("ghostButton")
        self._close_btn.setFixedWidth(160)
        self._close_btn.clicked.connect(self.reject)

        self._submit_btn = QPushButton("Simpan")
        self._submit_btn.setObjectName("primaryButton")
        self._submit_btn.setFixedWidth(200)
        self._submit_btn.clicked.connect(self._on_submit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self._close_btn)
        btn_layout.addWidget(self._submit_btn)
        btn_layout.addStretch()
        cl.addLayout(btn_layout)
        cl.addSpacing(16)

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.addWidget(header)
        outer.addWidget(sub)
        outer.addSpacing(8)
        outer.addWidget(scroll, stretch=1)

    def _load_existing(self) -> None:
        path = self._session.dass21_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        self._usia.setText(data.get("usia", ""))
        idx = self._kelamin.findText(data.get("jenis_kelamin", ""))
        if idx >= 0:
            self._kelamin.setCurrentIndex(idx)
        self._content_noise.setText(data.get("content_noise", ""))

        answers = data.get("answers", {})
        for i, group in enumerate(self._groups, start=1):
            val = answers.get(str(i))
            if val is not None:
                button = group.button(int(val))
                if button is not None:
                    button.setChecked(True)

    def _on_submit(self) -> None:
        if not self._usia.text().strip():
            QMessageBox.warning(self, "Validasi", "Usia tidak boleh kosong.")
            return

        answers: dict[int, int] = {}
        for i, group in enumerate(self._groups, start=1):
            if group.checkedId() == -1:
                QMessageBox.warning(self, "Validasi", f"Pertanyaan nomor {i} belum dijawab.")
                return
            answers[i] = group.checkedId()

        scores = {k: sum(answers[q] for q in items) for k, items in SUBSCALE_ITEMS.items()}
        levels = {k: _get_level(v, k) for k, v in scores.items()}
        all_normal = all(v == "Normal" for v in levels.values())

        result_text = (
            f"Hasil DASS-21:\n\n"
            f"  Depresi   : {scores['D']} → {levels['D']}\n"
            f"  Kecemasan : {scores['A']} → {levels['A']}\n"
            f"  Stres     : {scores['S']} → {levels['S']}\n\n"
        )
        result_text += (
            "Subjek memenuhi kriteria inklusi (semua Normal)."
            if all_normal
            else "Subjek TIDAK memenuhi kriteria inklusi screening — tetap disimpan sebagai data opsional."
        )
        QMessageBox.information(self, "Hasil Kuesioner", result_text)

        data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "session_id": self._session.session_id,
            "nama": self._session.subject_code,
            "usia": self._usia.text().strip(),
            "jenis_kelamin": self._kelamin.currentText(),
            "content_noise": self._content_noise.text().strip(),
            "answers": {str(k): v for k, v in answers.items()},
            "scores": scores,
            "levels": levels,
        }

        self._session.dass21_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        self._session.has_dass21 = True
        self._session.write_meta()

        self.accept()
