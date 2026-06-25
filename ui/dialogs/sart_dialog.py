import datetime
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.session import Session
from ui.effects import apply_card_shadow

QUESTIONS: list[tuple[int, str, str]] = [
    (1, "Bagaimana perubahan situasi saat Anda mengerjakan test dengan paparan kebisingan? "
        "Apakah situasi sangat tidak stabil dan sering berubah (tinggi) atau situasi stabil "
        "dan tidak banyak perubahan (rendah)?", "Instability of situation"),
    (2, "Bagaimana kerumitan situasi saat Anda mengerjakan test dengan paparan kebisingan? "
        "Apakah situasi kompleks dan sangat rumit (tinggi) atau sederhana dan tidak banyak "
        "komponen terkait (rendah)?", "Complexity of situation"),
    (3, "Seberapa banyak perubahan yang terjadi saat Anda mengerjakan test dengan paparan "
        "kebisingan? Apakah terdapat banyak faktor yang berubah (tinggi) atau sedikit faktor "
        "yang berubah (rendah)?", "Variability of Situation"),
    (4, "Seberapa sadar Anda saat mengerjakan test dengan paparan kebisingan? Apakah tingkat "
        "kesadaran Anda tinggi atau rendah?", "Arousal"),
    (5, "Seberapa konsentrasi Anda pada saat mengerjakan test dengan paparan kebisingan? "
        "Apakah Anda dapat berkonsentrasi pada banyak hal (tinggi) atau hanya berfokus pada "
        "satu hal (rendah)?", "Concentration of Attention"),
    (6, "Seberapa tinggi atensi Anda terbagi pada saat mengerjakan test dengan paparan "
        "kebisingan? Apakah Anda banyak membagi atensi (tinggi) atau sedikit membagi atensi "
        "(rendah)?", "Division of Attention"),
    (7, "Seberapa besar kapasitas mental yang harus diluangkan untuk mengerjakan test dengan "
        "paparan kebisingan? Apakah Anda memiliki kapasitas mental yang cukup untuk semua "
        "variabel (tinggi) atau tidak ada kapasitas yang tersisa sama sekali (rendah)?",
        "Spare Mental Capacity"),
    (8, "Seberapa banyak informasi yang Anda dapatkan saat mengerjakan test dengan paparan "
        "kebisingan? Apakah Anda bisa menerima banyak informasi saat mengerjakan test "
        "(instruksi pengawas) atau hanya sedikit informasi yang bisa Anda terima?",
        "Information Quantity"),
    (9, "Seberapa terbiasa anda dengan situasi mengerjakan test dengan paparan kebisingan? "
        "Apakah Anda sering memiliki pengalaman yang sama terhadap situasi tersebut (tinggi) "
        "atau merupakan pengalaman yang baru untuk Anda (rendah)?", "Familiarity with Situation"),
]


class SARTDialog(QDialog):
    """Modal, fully optional SART questionnaire attached to one Session.

    Writes recordings/<session_id>/sart.json and flips Session.has_sart.
    """

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self.setWindowTitle(f"Kuesioner SART — {session.session_id}")
        self._groups: list[QButtonGroup] = []
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        self.setMinimumSize(720, 560)

        header = QLabel("Kuesioner SART")
        header.setObjectName("appTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Situation Awareness Rating Technique — opsional, terikat ke sesi ini")
        sub.setObjectName("appSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setSpacing(16)

        id_box = QGroupBox("Data Responden")
        id_form = QFormLayout(id_box)
        # Nama is one-per-Session (satu sesi = satu responden) — edit it via the Nama field on
        # the session control strip, not here.
        self._nama_label = QLabel(
            self._session.subject_code or "(kosong — isi di Nama pada sesi)"
        )
        id_form.addRow("Nama:", self._nama_label)
        apply_card_shadow(id_box)
        cl.addWidget(id_box)

        instr = QLabel(
            "Petunjuk: Pilih angka yang paling sesuai dengan persepsi Anda.\n"
            "Skala 1 = Sangat Rendah  |  Skala 7 = Sangat Tinggi"
        )
        instr.setWordWrap(True)
        cl.addWidget(instr)

        q_box = QGroupBox("Pertanyaan")
        q_grid = QGridLayout(q_box)
        q_grid.setColumnStretch(1, 1)

        for col, lbl in enumerate(["No.", "Pertanyaan", "1", "2", "3", "4", "5", "6", "7"]):
            h = QLabel(f"<b>{lbl}</b>")
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            q_grid.addWidget(h, 0, col)

        for row, (num, text, dimension) in enumerate(QUESTIONS, start=1):
            group = QButtonGroup(self)
            self._groups.append(group)

            q_grid.addWidget(QLabel(str(num)), row, 0, Qt.AlignmentFlag.AlignCenter)

            q_lbl = QLabel(f"{text}<br><i>({dimension})</i>")
            q_lbl.setWordWrap(True)
            q_grid.addWidget(q_lbl, row, 1)

            for val in range(1, 8):
                rb = QRadioButton()
                group.addButton(rb, val)
                q_grid.addWidget(rb, row, 1 + val, Qt.AlignmentFlag.AlignCenter)

        apply_card_shadow(q_box)
        cl.addWidget(q_box)

        self._close_btn = QPushButton("Tutup")
        self._close_btn.setObjectName("ghostButton")
        self._close_btn.setFixedWidth(160)
        self._close_btn.clicked.connect(self.reject)

        self._submit_btn = QPushButton("Simpan")
        self._submit_btn.setObjectName("primaryButton")
        self._submit_btn.setFixedWidth(160)
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
        path = self._session.sart_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        answers = data.get("answers", {})
        for i, group in enumerate(self._groups, start=1):
            val = answers.get(str(i))
            if val is not None:
                button = group.button(int(val))
                if button is not None:
                    button.setChecked(True)

    def _on_submit(self) -> None:
        answers: dict[int, int] = {}
        for i, group in enumerate(self._groups, start=1):
            if group.checkedId() == -1:
                QMessageBox.warning(self, "Validasi", f"Pertanyaan nomor {i} belum dijawab.")
                return
            answers[i] = group.checkedId()

        data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "session_id": self._session.session_id,
            "nama": self._session.subject_code,
            "answers": {str(k): v for k, v in answers.items()},
        }

        self._session.sart_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        self._session.has_sart = True
        self._session.write_meta()

        QMessageBox.information(self, "Tersimpan", f"Hasil SART disimpan ke:\n{self._session.sart_path}")
        self.accept()
