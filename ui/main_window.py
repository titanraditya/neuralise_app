import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import QMainWindow, QMessageBox

from core.device_manager import DeviceManager
from core.session import Session
from core.settings import get_warn_missing_dass21, set_warn_missing_dass21
from ui.dialogs.dass21_dialog import DASS21Dialog
from ui.dialogs.sart_dialog import SARTDialog
from ui.screens.main_screen import MainScreen

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MainWindow(QMainWindow):
    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Neuralise — Drowsiness Detection")
        self.resize(1200, 720)

        self._device_manager = DeviceManager(use_mock=mock)
        self._session: Session | None = None
        self._report_processes: dict[str, QProcess] = {}

        self._screen = MainScreen()
        self.setCentralWidget(self._screen)

        self._build_menu()
        self._wire_device_row()
        self._wire_device_manager()
        self._wire_control_strip()
        self._wire_history_drawer()

    # ------------------------------------------------------------------
    # Menu — settings
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Pengaturan")
        self._warn_dass21_action = QAction("Peringatan DASS-21 sebelum Rekam", self)
        self._warn_dass21_action.setCheckable(True)
        self._warn_dass21_action.setChecked(get_warn_missing_dass21())
        self._warn_dass21_action.toggled.connect(set_warn_missing_dass21)
        settings_menu.addAction(self._warn_dass21_action)

    # ------------------------------------------------------------------
    # Device row <-> DeviceManager (rig-level, persistent — independent of any Session)
    # ------------------------------------------------------------------

    def _wire_device_row(self) -> None:
        self._screen.device_row.camera_toggled.connect(self._on_camera_toggled)
        self._screen.device_row.eeg_toggled.connect(self._on_eeg_toggled)
        self._screen.device_row.calibrate_eeg_clicked.connect(self._on_calibrate_eeg)
        self._screen.device_row.eog_toggled.connect(self._on_eog_toggled)
        self._screen.device_row.calibrate_eog_clicked.connect(self._on_calibrate_eog)

    def _wire_device_manager(self) -> None:
        dm = self._device_manager
        dm.camera_frame_ready.connect(self._screen.camera_panel.update_frame)
        dm.camera_analysis_ready.connect(self._on_camera_analysis)
        dm.camera_error.connect(self._on_camera_error)
        dm.eeg_frame_ready.connect(self._screen.eeg_panel.update_frame)
        dm.eeg_frame_ready.connect(self._on_eeg_frame)
        dm.eeg_bands_ready.connect(self._screen.eeg_panel.update_bands)
        dm.eeg_status_ready.connect(self._screen.status_panel.set_eeg_status)
        dm.eeg_connecting_changed.connect(self._screen.device_row.set_eeg_connecting)
        dm.eeg_connected_changed.connect(self._on_eeg_connected_changed)
        dm.eeg_connect_failed.connect(self._on_eeg_connect_failed)
        dm.museeog_frame_ready.connect(self._screen.museeog_panel.update_frame)
        dm.museeog_metrics_ready.connect(self._screen.museeog_panel.update_metrics)
        dm.museeog_status_ready.connect(self._screen.museeog_panel.set_status)
        dm.eog_frame_ready.connect(self._screen.eog_panel.update_frame)
        dm.eog_metrics_ready.connect(self._screen.eog_panel.update_metrics)
        dm.eog_status_ready.connect(self._screen.eog_panel.set_status)
        dm.eog_status_ready.connect(self._screen.status_panel.set_eog_status)
        dm.eog_connecting_changed.connect(self._screen.device_row.set_eog_connecting)
        dm.eog_connected_changed.connect(self._on_eog_connected_changed)
        dm.eog_connect_failed.connect(self._on_eog_connect_failed)

    def _on_camera_toggled(self, connected: bool) -> None:
        if connected:
            self._screen.camera_panel.set_active(True)
            self._device_manager.connect_camera()
        else:
            self._device_manager.disconnect_camera()
            self._screen.camera_panel.clear()
            self._screen.status_panel.set_cam_status("idle")

    def _on_camera_analysis(
        self, _ear_l: float, _ear_r: float, _ear_avg: float, perclos: float, status: str
    ) -> None:
        if not self._device_manager.camera_connected:
            return  # straggler analysis_ready queued just before the worker thread stopped
        self._screen.camera_panel.set_perclos(perclos)
        self._screen.status_panel.set_cam_status("drowsy" if status == "drowsy" else "awake")

    def _on_camera_error(self, message: str) -> None:
        self._device_manager.disconnect_camera()
        self._screen.device_row.set_camera_connected(False)
        self._screen.camera_panel.clear()
        QMessageBox.critical(self, "Camera Error", message)

    def _on_eeg_toggled(self, connected: bool) -> None:
        if connected:
            self._device_manager.connect_eeg()
        else:
            self._device_manager.disconnect_eeg()

    def _on_eeg_connected_changed(self, connected: bool) -> None:
        self._screen.device_row.set_eeg_connected(connected)
        dm = self._device_manager
        if connected:
            self._screen.eeg_panel.set_channels(dm.eeg_channel_names)
            # Muse-EOG rides the EEG connection — activate its panel too if this headset can
            # derive an EOG channel from a frontal electrode.
            if dm.museeog_available:
                self._screen.museeog_panel.set_channels(
                    [dm.museeog_channel_name], dm.museeog_sample_rate
                )
        else:
            self._screen.eeg_panel.set_channels([])
            self._screen.status_panel.set_eeg_status("idle")
            self._screen.museeog_panel.set_channels([])

    def _on_eeg_connect_failed(self, message: str) -> None:
        self._screen.device_row.set_eeg_connected(False)
        QMessageBox.critical(self, "EEG Connection Error", message)

    def _on_calibrate_eeg(self) -> None:
        # One headset, one button: calibrate both the EEG-drowsiness and the Muse-EOG baselines.
        self._device_manager.start_eeg_calibration()
        self._device_manager.start_museeog_calibration()

    def _on_eeg_frame(self, _segments, contact_ok) -> None:
        if not contact_ok:
            self._screen.device_row.set_eeg_contact_text("Kontak EEG: –")
            return
        ok_count = sum(1 for ok in contact_ok if ok)
        self._screen.device_row.set_eeg_contact_text(f"Kontak EEG: {ok_count}/{len(contact_ok)} OK")

    def _on_eog_toggled(self, connected: bool) -> None:
        if connected:
            self._device_manager.connect_eog()
        else:
            self._device_manager.disconnect_eog()

    def _on_eog_connected_changed(self, connected: bool) -> None:
        self._screen.device_row.set_eog_connected(connected)
        if connected:
            self._screen.eog_panel.set_channels(
                self._device_manager.eog_channel_names, self._device_manager.eog_sample_rate
            )
        else:
            self._screen.eog_panel.set_channels([])
            self._screen.status_panel.set_eog_status("idle")

    def _on_eog_connect_failed(self, message: str) -> None:
        self._screen.device_row.set_eog_connected(False)
        QMessageBox.critical(self, "EOG Connection Error", message)

    def _on_calibrate_eog(self) -> None:
        self._device_manager.start_eog_calibration()

    # ------------------------------------------------------------------
    # Control strip <-> Session (recording layer — decoupled from device connect/disconnect)
    # ------------------------------------------------------------------

    def _wire_control_strip(self) -> None:
        strip = self._screen.control_strip
        strip.new_session_clicked.connect(self._on_new_session)
        strip.record_toggled.connect(self._on_record_toggled)
        strip.selesai_clicked.connect(self._on_selesai)
        strip.subject_code_changed.connect(self._on_subject_code_changed)
        strip.dass21_clicked.connect(self._on_dass21_from_strip)
        strip.sart_clicked.connect(self._on_sart_from_strip)

    def _on_new_session(self) -> None:
        self._session = Session()
        strip = self._screen.control_strip
        strip.set_session_id(self._session.session_id)
        strip.set_subject_code("")
        strip.set_mode("aktif")
        self._refresh_history()

    def _on_record_toggled(self, recording: bool) -> None:
        if self._session is None:
            return
        dm = self._device_manager
        if recording:
            if not self._session.has_dass21 and get_warn_missing_dass21():
                reply = QMessageBox.question(
                    self,
                    "DASS-21 belum diisi",
                    "DASS-21 belum diisi untuk sesi ini, lanjut tanpa screening?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self._screen.control_strip.set_recording(False)
                    return
            if dm.camera_connected:
                dm.start_camera_recording(self._session.camera_csv_path)
                self._session.has_camera = True
            if dm.eeg_connected:
                dm.start_eeg_recording(self._session.eeg_csv_path)
                self._session.has_eeg = True
                # Muse-EOG rides the Muse board — record it as its own file when available.
                if dm.museeog_available:
                    dm.start_museeog_recording(self._session.museeog_csv_path)
                    self._session.has_museeog = True
            if dm.eog_connected:
                dm.start_eog_recording(self._session.eog_csv_path)
                self._session.has_eog = True
            self._session.write_meta()
            self._screen.status_panel.start_record_timer()
        else:
            dm.stop_camera_recording()
            dm.stop_eeg_recording()
            dm.stop_museeog_recording()
            dm.stop_eog_recording()
            self._screen.status_panel.stop_record_timer()
        self._refresh_history()

    def _on_selesai(self) -> None:
        if self._session is None:
            return
        self._device_manager.stop_camera_recording()
        self._device_manager.stop_eeg_recording()
        self._device_manager.stop_museeog_recording()
        self._device_manager.stop_eog_recording()
        self._screen.status_panel.stop_record_timer()
        self._session.end()  # writer flushed+closed by stop_*_recording() above before this point
        session_dir = self._session.dir
        self._session = None
        self._screen.control_strip.set_mode("siap")
        self._refresh_history()
        self._start_report_generation(session_dir)

    def _on_subject_code_changed(self, text: str) -> None:
        if self._session is not None:
            self._session.subject_code = text
            self._session.write_meta()

    # ------------------------------------------------------------------
    # DASS-21 / SART — modal, optional, attached to a Session by session_id
    # ------------------------------------------------------------------

    def _on_dass21_from_strip(self) -> None:
        if self._session is not None:
            self._open_dass21(self._session)

    def _on_sart_from_strip(self) -> None:
        if self._session is not None:
            self._open_sart(self._session)

    def _wire_history_drawer(self) -> None:
        drawer = self._screen.history_drawer
        drawer.dass21_requested.connect(self._on_dass21_from_history)
        drawer.sart_requested.connect(self._on_sart_from_history)
        drawer.delete_requested.connect(self._on_session_delete_requested)
        drawer.open_pdf_requested.connect(self._on_open_pdf_requested)
        drawer.regenerate_report_requested.connect(self._on_regenerate_report_requested)

    def _on_dass21_from_history(self, session_dir) -> None:
        self._open_dass21(self._resolve_session(Path(session_dir)))

    def _on_sart_from_history(self, session_dir) -> None:
        self._open_sart(self._resolve_session(Path(session_dir)))

    def _on_session_delete_requested(self, session_dir) -> None:
        session_dir = Path(session_dir)
        if self._session is not None and self._session.dir == session_dir:
            QMessageBox.warning(
                self,
                "Sesi masih aktif",
                "Sesi ini masih aktif — klik \"Selesai\" dulu sebelum menghapusnya.",
            )
            return
        try:
            Session.load(session_dir).delete()
        except OSError as exc:
            QMessageBox.critical(self, "Gagal Menghapus", f"Tidak bisa menghapus sesi:\n{exc}")
            return
        self._refresh_history()

    def _resolve_session(self, session_dir: Path) -> Session:
        """Reuse the live, in-memory Session if it's the one being requested — otherwise a
        write from a freshly-loaded copy would go to disk fine, but the live object's
        in-memory has_* flags would go stale and a later write_meta() from the control strip
        would clobber it back."""
        if self._session is not None and self._session.dir == session_dir:
            return self._session
        return Session.load(session_dir)

    def _open_dass21(self, session: Session) -> None:
        DASS21Dialog(session, parent=self).exec()
        self._refresh_history()

    def _open_sart(self, session: Session) -> None:
        SARTDialog(session, parent=self).exec()
        self._refresh_history()

    def _refresh_history(self) -> None:
        self._screen.history_drawer.refresh()

    # ------------------------------------------------------------------
    # PDF report — always generated by spawning `python -m tools.report <session_dir>` as a
    # separate OS process, never called in-process: rendering the plot + PDF is too heavy to
    # run on the GUI thread without freezing the UI (tools/report.py is plain batch code with
    # no Qt import, specifically so it can run standalone like this).
    # ------------------------------------------------------------------

    def _start_report_generation(self, session_dir: Path) -> None:
        session_id = session_dir.name
        if session_id in self._report_processes:
            return  # already (re)generating this one — don't spawn a second process for it
        process = QProcess(self)
        process.setProgram(sys.executable)
        # session_dir may be relative (Session() defaults to a relative "recordings/" base) —
        # resolve it against the GUI's cwd before handing it to a subprocess that runs with a
        # different working directory (PROJECT_ROOT), so the two can't disagree about the path.
        process.setArguments(["-m", "tools.report", str(Path(session_dir).resolve())])
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.finished.connect(lambda code, status: self._on_report_finished(session_id, code, status))
        self._report_processes[session_id] = process
        self._screen.history_drawer.set_report_generating(session_id, True)
        self.statusBar().showMessage(f"Membuat laporan untuk {session_id}…")
        process.start()

    def _on_report_finished(self, session_id: str, exit_code: int, _exit_status) -> None:
        process = self._report_processes.pop(session_id, None)
        if exit_code != 0:
            stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace") if process else ""
            print(f"[report] gagal membuat laporan untuk {session_id} (exit {exit_code}):\n{stderr}", file=sys.stderr)
            self.statusBar().showMessage(f"Gagal membuat laporan untuk {session_id} — lihat log.", 8000)
        else:
            self.statusBar().showMessage(f"Laporan untuk {session_id} siap.", 6000)
        self._screen.history_drawer.set_report_generating(session_id, False)
        self._refresh_history()

    def _on_open_pdf_requested(self, session_dir) -> None:
        # session_dir may be relative (Session() defaults to a relative "recordings/" base) —
        # QUrl.fromLocalFile() on a relative path builds a malformed file: URI with no leading
        # slash, which gio/xdg-open then rejects as "Operation not supported".
        pdf_path = Path(session_dir).resolve() / "report.pdf"
        if pdf_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))

    def _on_regenerate_report_requested(self, session_dir) -> None:
        self._start_report_generation(Path(session_dir))

    # ------------------------------------------------------------------
    # Shutdown — fix finding #2: never leave an acquisition thread running.
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._device_manager.shutdown()
        super().closeEvent(event)
