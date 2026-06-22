from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox

from core.device_manager import DeviceManager
from core.session import Session
from core.settings import get_warn_missing_dass21, set_warn_missing_dass21
from ui.dialogs.dass21_dialog import DASS21Dialog
from ui.dialogs.sart_dialog import SARTDialog
from ui.screens.main_screen import MainScreen


class MainWindow(QMainWindow):
    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Neuralise — Drowsiness Detection")
        self.resize(1200, 720)

        self._device_manager = DeviceManager(use_mock=mock)
        self._session: Session | None = None

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

    def _on_camera_toggled(self, connected: bool) -> None:
        if connected:
            self._screen.camera_panel.set_active(True)
            self._device_manager.connect_camera()
        else:
            self._device_manager.disconnect_camera()
            self._screen.camera_panel.clear()
            self._screen.status_panel.set_cam_status("idle")
            self._screen.status_panel.set_metric("perclos", "--")

    def _on_camera_analysis(
        self, _ear_l: float, _ear_r: float, _ear_avg: float, perclos: float, status: str
    ) -> None:
        self._screen.status_panel.set_metric("perclos", f"{perclos * 100:.1f}%")
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
        if connected:
            self._screen.eeg_panel.set_channels(self._device_manager.eeg_channel_names)
        else:
            self._screen.eeg_panel.set_channels([])
            self._screen.status_panel.set_eeg_status("idle")

    def _on_eeg_connect_failed(self, message: str) -> None:
        self._screen.device_row.set_eeg_connected(False)
        QMessageBox.critical(self, "EEG Connection Error", message)

    def _on_calibrate_eeg(self) -> None:
        self._device_manager.start_eeg_calibration()

    def _on_eeg_frame(self, _segments, contact_ok) -> None:
        if not contact_ok:
            self._screen.device_row.set_eeg_contact_text("Kontak EEG: –")
            return
        ok_count = sum(1 for ok in contact_ok if ok)
        self._screen.device_row.set_eeg_contact_text(f"Kontak EEG: {ok_count}/{len(contact_ok)} OK")

    # ------------------------------------------------------------------
    # Control strip <-> Session (recording layer — decoupled from device connect/disconnect)
    # ------------------------------------------------------------------

    def _wire_control_strip(self) -> None:
        strip = self._screen.control_strip
        strip.new_session_clicked.connect(self._on_new_session)
        strip.record_toggled.connect(self._on_record_toggled)
        strip.selesai_clicked.connect(self._on_selesai)
        strip.subject_code_changed.connect(self._on_subject_code_changed)
        strip.noise_condition_changed.connect(self._on_noise_condition_changed)
        strip.dass21_clicked.connect(self._on_dass21_from_strip)
        strip.sart_clicked.connect(self._on_sart_from_strip)

    def _on_new_session(self) -> None:
        self._session = Session()
        strip = self._screen.control_strip
        strip.set_session_id(self._session.session_id)
        strip.set_subject_code("")
        strip.set_noise_condition("")
        strip.set_mode("aktif")
        self._refresh_history_if_visible()

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
            self._session.write_meta()
        else:
            dm.stop_camera_recording()
            dm.stop_eeg_recording()
        self._refresh_history_if_visible()

    def _on_selesai(self) -> None:
        if self._session is None:
            return
        self._device_manager.stop_camera_recording()
        self._device_manager.stop_eeg_recording()
        self._session.end()
        self._session = None
        self._screen.control_strip.set_mode("siap")
        self._refresh_history_if_visible()

    def _on_subject_code_changed(self, text: str) -> None:
        if self._session is not None:
            self._session.subject_code = text
            self._session.write_meta()

    def _on_noise_condition_changed(self, text: str) -> None:
        if self._session is not None:
            self._session.noise_condition = text
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
        self._screen.history_toggle_requested.connect(self._on_history_toggle)
        drawer = self._screen.history_drawer
        drawer.close_clicked.connect(lambda: drawer.setVisible(False))
        drawer.dass21_requested.connect(self._on_dass21_from_history)
        drawer.sart_requested.connect(self._on_sart_from_history)

    def _on_history_toggle(self) -> None:
        drawer = self._screen.history_drawer
        visible = not drawer.isVisible()
        drawer.setVisible(visible)
        if visible:
            drawer.refresh()

    def _on_dass21_from_history(self, session_dir) -> None:
        self._open_dass21(self._resolve_session(Path(session_dir)))

    def _on_sart_from_history(self, session_dir) -> None:
        self._open_sart(self._resolve_session(Path(session_dir)))

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
        self._refresh_history_if_visible()

    def _open_sart(self, session: Session) -> None:
        SARTDialog(session, parent=self).exec()
        self._refresh_history_if_visible()

    def _refresh_history_if_visible(self) -> None:
        drawer = self._screen.history_drawer
        if drawer.isVisible():
            drawer.refresh()

    # ------------------------------------------------------------------
    # Shutdown — fix finding #2: never leave an acquisition thread running.
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._device_manager.shutdown()
        super().closeEvent(event)
