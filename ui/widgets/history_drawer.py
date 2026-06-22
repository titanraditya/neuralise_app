import zipfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.session import Session

BADGE_ON = (
    "background-color: #1f9d55; color: #ffffff; border-radius: 6px;"
    "padding: 2px 6px; font-size: 10px; font-weight: 700;"
)
BADGE_OFF = (
    "background-color: #d7dde7; color: #6b7585; border-radius: 6px;"
    "padding: 2px 6px; font-size: 10px; font-weight: 700;"
)


def _badge(label: str, ok: bool) -> QLabel:
    badge = QLabel(label)
    badge.setStyleSheet(BADGE_ON if ok else BADGE_OFF)
    return badge


class _SessionRow(QWidget):
    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel(session.session_id)
        title.setStyleSheet("font-weight: 700;")
        layout.addWidget(title)

        sub_bits = [b for b in (session.subject_code, session.noise_condition) if b]
        if sub_bits:
            sub = QLabel(" · ".join(sub_bits))
            sub.setStyleSheet("color: #6b7585; font-size: 11px;")
            layout.addWidget(sub)

        badges = QHBoxLayout()
        badges.setSpacing(4)
        badges.addWidget(_badge("KAMERA", session.has_camera))
        badges.addWidget(_badge("EEG", session.has_eeg))
        badges.addWidget(_badge("DASS-21", session.has_dass21))
        badges.addWidget(_badge("SART", session.has_sart))
        badges.addStretch(1)
        layout.addLayout(badges)


class HistoryDrawer(QWidget):
    """Side panel (open/close, not a screen) listing recordings/<session_id>/ folders.

    Click a session for a summary, fill in a missing questionnaire, or export that one
    session's folder as a zip. Read-only over the filesystem otherwise — no DeviceManager
    or live Session dependency baked in; MainWindow resolves dass21_requested/sart_requested
    to the right Session (live vs. reloaded from disk) before opening a dialog.
    """

    close_clicked = Signal()
    dass21_requested = Signal(object)  # Path to the session's folder
    sart_requested = Signal(object)  # Path to the session's folder

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlBar")
        self.setFixedWidth(320)
        self._sessions: dict[str, Session] = {}

        title = QLabel("Riwayat Sesi")
        title.setObjectName("appTitle")
        close_btn = QPushButton("×")
        close_btn.setFixedWidth(32)
        close_btn.clicked.connect(self.close_clicked)

        header = QHBoxLayout()
        header.addWidget(title, stretch=1)
        header.addWidget(close_btn)

        self._list = QListWidget()
        self._list.setSpacing(4)
        self._list.currentItemChanged.connect(self._on_selection_changed)

        self._summary_frame = QFrame()
        self._summary_frame.setObjectName("metricTile")
        summary_layout = QVBoxLayout(self._summary_frame)
        self._summary_label = QLabel("Pilih sesi untuk lihat ringkasan.")
        self._summary_label.setWordWrap(True)
        summary_layout.addWidget(self._summary_label)

        btn_row = QHBoxLayout()
        self._dass21_btn = QPushButton("Isi DASS-21")
        self._dass21_btn.clicked.connect(self._on_dass21_clicked)
        self._sart_btn = QPushButton("Isi SART")
        self._sart_btn.clicked.connect(self._on_sart_clicked)
        btn_row.addWidget(self._dass21_btn)
        btn_row.addWidget(self._sart_btn)
        summary_layout.addLayout(btn_row)

        self._export_btn = QPushButton("Export (.zip)")
        self._export_btn.clicked.connect(self._on_export_clicked)
        summary_layout.addWidget(self._export_btn)
        self._set_summary_enabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._list, stretch=1)
        layout.addWidget(self._summary_frame)

        self.refresh()

    def refresh(self) -> None:
        current_id = self._current_session_id()
        self._sessions = {}
        self._list.clear()
        for session_dir in Session.list_all():
            try:
                session = Session.load(session_dir)
            except (OSError, ValueError):
                continue
            self._sessions[session.session_id] = session

            item = QListWidgetItem(self._list)
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)
            row_widget = _SessionRow(session)
            item.setSizeHint(row_widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row_widget)
            if session.session_id == current_id:
                self._list.setCurrentItem(item)

        if self._list.currentItem() is None:
            self._set_summary_enabled(False)
            self._summary_label.setText("Pilih sesi untuk lihat ringkasan.")

    def _current_session_id(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected_session(self) -> Session | None:
        session_id = self._current_session_id()
        return self._sessions.get(session_id) if session_id else None

    def _on_selection_changed(self, current: QListWidgetItem, _previous: QListWidgetItem) -> None:
        if current is None:
            self._set_summary_enabled(False)
            return
        session = self._sessions.get(current.data(Qt.ItemDataRole.UserRole))
        if session is None:
            self._set_summary_enabled(False)
            return
        self._set_summary_enabled(True)
        self._summary_label.setText(
            f"<b>{session.session_id}</b><br>"
            f"Subject: {session.subject_code or '-'}<br>"
            f"Noise: {session.noise_condition or '-'}<br>"
            f"Mulai: {session.started_at}<br>"
            f"Selesai: {session.ended_at or '(masih aktif)'}"
        )

    def _set_summary_enabled(self, enabled: bool) -> None:
        self._dass21_btn.setEnabled(enabled)
        self._sart_btn.setEnabled(enabled)
        self._export_btn.setEnabled(enabled)

    def _on_dass21_clicked(self) -> None:
        session = self._selected_session()
        if session is not None:
            self.dass21_requested.emit(session.dir)

    def _on_sart_clicked(self) -> None:
        session = self._selected_session()
        if session is not None:
            self.sart_requested.emit(session.dir)

    def _on_export_clicked(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Sesi", f"{session.session_id}.zip", "ZIP Archive (*.zip)"
        )
        if not path:
            return
        files = [f for f in session.dir.iterdir() if f.is_file()]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.name)
        QMessageBox.information(self, "Export Selesai", f"{len(files)} file diekspor ke:\n{path}")
