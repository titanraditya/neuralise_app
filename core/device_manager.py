import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal

from camera.camera_thread import CameraThread
from core.eeg_drowsiness import EEGDrowsinessDetector
from core.eeg_recorder import EEGRecorder
from core.sources.base import EEGSource
from core.sources.mock import MockEEGSource
from core.sources.muse import MuseEEGSource

EEG_POLL_MS = 33  # matches the old ui/widgets/eeg_panel.py REFRESH_MS
EEG_WINDOW_SECONDS = 5.0  # matches the old ui/widgets/eeg_panel.py WINDOW_SECONDS
BAND_UPDATE_EVERY_N_POLLS = round(1000 / EEG_POLL_MS)  # ~once per second


class _EEGConnectWorker(QThread):
    """Runs EEGSource.start() off the UI thread — for a real Muse headset this is a blocking
    BrainFlow prepare_session()/start_stream() call that can take several seconds of BLE
    scan/pairing, which would otherwise freeze the whole window."""

    succeeded = Signal(object)  # the now-started EEGSource
    failed = Signal(str)

    def __init__(self, source: EEGSource, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source = source

    def run(self) -> None:
        try:
            self._source.start()
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a connection error
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(self._source)


class DeviceManager(QObject):
    """Rig-level owner of the camera + EEG connections (CLAUDE.md target architecture).

    Connect once; streaming continues regardless of whether a recording Session is active —
    connect/disconnect is decoupled from start/stop recording, and from any particular Session.
    This is the only consumer of EEGSource.get_samples(): UI panels and recorders are fed via
    signals instead of polling the source themselves, so there's a single source of truth for
    the raw stream.
    """

    camera_frame_ready = Signal(object)  # np.ndarray RGB
    camera_analysis_ready = Signal(float, float, float, float, str)  # ear_l, ear_r, ear_avg, perclos, status
    camera_error = Signal(str)

    eeg_frame_ready = Signal(object, object)  # display_segments: list[np.ndarray], contact_ok: list[bool]
    eeg_bands_ready = Signal(object)  # bands: list[float] (delta..gamma)
    eeg_status_ready = Signal(str, str)  # status ('calibrating'|'awake'|'drowsy'), detail text

    eeg_connecting_changed = Signal(bool)  # True while a connect attempt is in flight
    eeg_connected_changed = Signal(bool)  # True after a successful connect, False on disconnect
    eeg_connect_failed = Signal(str)  # error message

    def __init__(self, use_mock: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._use_mock = use_mock

        self._camera_thread: CameraThread | None = None

        self._eeg_source: EEGSource | None = None
        self._eeg_connect_worker: _EEGConnectWorker | None = None
        self._eeg_calibration_active = False
        self._eeg_detector = EEGDrowsinessDetector()
        self._eeg_buffers: list[np.ndarray] = []
        self._eeg_samples_seen = 0
        self._eeg_poll_count = 0
        self._eeg_recorder: EEGRecorder | None = None
        self._eeg_recording = False

        self._eeg_timer = QTimer(self)
        self._eeg_timer.timeout.connect(self._poll_eeg)

    # ------------------------------------------------------------------
    # Camera — persistent connection, independent of any Session
    # ------------------------------------------------------------------

    @property
    def camera_connected(self) -> bool:
        return self._camera_thread is not None

    def connect_camera(self) -> None:
        if self._camera_thread is not None:
            return
        thread = CameraThread(use_mock=self._use_mock)
        thread.frame_ready.connect(self.camera_frame_ready)
        thread.analysis_ready.connect(self.camera_analysis_ready)
        thread.camera_error.connect(self.camera_error)
        thread.start_camera()
        self._camera_thread = thread

    def disconnect_camera(self) -> None:
        if self._camera_thread is None:
            return
        self._camera_thread.stop_camera()  # blocks until the worker thread has actually exited
        self._camera_thread = None

    def start_camera_recording(self, path: str | Path) -> None:
        if self._camera_thread is not None:
            self._camera_thread.start_recording(path)

    def stop_camera_recording(self) -> None:
        if self._camera_thread is not None:
            self._camera_thread.stop_recording()

    # ------------------------------------------------------------------
    # EEG — persistent connection; calibration is manual-only (start_eeg_calibration()),
    # never an automatic side effect of connect_eeg() or creating a Session.
    # ------------------------------------------------------------------

    @property
    def eeg_connected(self) -> bool:
        return self._eeg_source is not None

    @property
    def eeg_calibration_active(self) -> bool:
        return self._eeg_calibration_active

    @property
    def eeg_channel_names(self) -> list[str]:
        return list(self._eeg_source.channel_names) if self._eeg_source is not None else []

    def connect_eeg(self, serial_number: str = "") -> None:
        """Connects asynchronously: EEGSource.start() runs on a worker thread so a slow BLE
        pairing can't freeze the UI. Result arrives via eeg_connected_changed/eeg_connect_failed,
        bracketed by eeg_connecting_changed(True)/(False)."""
        if self._eeg_source is not None or self._eeg_connect_worker is not None:
            return
        source = MockEEGSource() if self._use_mock else MuseEEGSource(serial_number)
        worker = _EEGConnectWorker(source, self)
        worker.succeeded.connect(self._on_eeg_connect_succeeded)
        worker.failed.connect(self._on_eeg_connect_failed)
        worker.finished.connect(worker.deleteLater)
        self._eeg_connect_worker = worker
        self.eeg_connecting_changed.emit(True)
        worker.start()

    def _on_eeg_connect_succeeded(self, source: EEGSource) -> None:
        self._eeg_connect_worker = None
        self._eeg_source = source
        window_points = int(EEG_WINDOW_SECONDS * source.sample_rate)
        self._eeg_buffers = [np.zeros(window_points, dtype=np.float32) for _ in source.channel_names]
        self._eeg_samples_seen = 0
        self._eeg_poll_count = 0
        self._eeg_timer.start(EEG_POLL_MS)
        self.eeg_connecting_changed.emit(False)
        self.eeg_connected_changed.emit(True)

    def _on_eeg_connect_failed(self, message: str) -> None:
        self._eeg_connect_worker = None
        self.eeg_connecting_changed.emit(False)
        self.eeg_connect_failed.emit(message)

    def disconnect_eeg(self) -> None:
        self._eeg_timer.stop()
        if self._eeg_source is not None:
            self._eeg_source.stop()
        self._eeg_source = None
        self.eeg_connected_changed.emit(False)

    def start_eeg_calibration(self) -> None:
        """(Re-)run the 30s baseline, triggered only by an explicit user action (a dedicated
        "Kalibrasi EEG" button) — never automatically on connect_eeg() or when a Session is
        created, so the subject can get settled first. Also doubles as recalibrate: calling
        this again later resets the baseline without reconnecting the EEG source (fix finding
        #9 — previously the only way to recalibrate was a full disconnect/reconnect, which
        re-pairs BLE). Once active, calibration stays active across a BLE drop/reconnect.
        """
        self._eeg_detector.reset()
        self._eeg_calibration_active = True

    def start_eeg_recording(self, path: str | Path) -> None:
        if self._eeg_source is None:
            return
        recorder = EEGRecorder()
        recorder.start(path)
        self._eeg_recorder = recorder
        self._eeg_recording = True

    def stop_eeg_recording(self) -> None:
        self._eeg_recording = False
        if self._eeg_recorder is not None:
            self._eeg_recorder.stop()
            self._eeg_recorder = None

    def shutdown(self) -> None:
        """Stop all acquisition threads/connections cleanly (fix finding #2: call this from the
        main window's closeEvent so a window close can never leak a running CameraThread)."""
        self.disconnect_camera()
        if self._eeg_connect_worker is not None:
            self._eeg_connect_worker.wait()  # let an in-flight connect attempt resolve first
        self.disconnect_eeg()

    def _poll_eeg(self) -> None:
        source = self._eeg_source
        if source is None:
            return

        samples = source.get_samples()
        if samples is not None and samples.shape[1] > 0:
            self._eeg_samples_seen += samples.shape[1]
            for i in range(len(self._eeg_buffers)):
                self._eeg_buffers[i] = np.concatenate(
                    [self._eeg_buffers[i], samples[i]]
                )[-len(self._eeg_buffers[i]):]

        # Same warm-up guard as the old EEGPanel: don't trust check_contact/filter_for_display
        # on a still mostly-zero buffer right after connecting (avoids a false "no contact" read).
        warmed_up = self._eeg_samples_seen >= source.sample_rate

        contact_ok = [True] * len(self._eeg_buffers)
        display_segments = list(self._eeg_buffers)
        if warmed_up:
            contact_ok = [source.check_contact(seg) for seg in self._eeg_buffers]
            display_segments = [
                source.filter_for_display(seg) if ok else seg
                for seg, ok in zip(self._eeg_buffers, contact_ok)
            ]
        self.eeg_frame_ready.emit(display_segments, contact_ok)

        self._eeg_poll_count += 1
        if not warmed_up or self._eeg_poll_count % BAND_UPDATE_EVERY_N_POLLS != 0:
            return

        good_idx = [i for i, ok in enumerate(contact_ok) if ok]
        if not good_idx:
            return

        bands = source.band_powers(np.vstack(self._eeg_buffers), good_idx)
        if bands is None:
            return

        self.eeg_bands_ready.emit(bands)
        ratio = EEGDrowsinessDetector.ratio(bands)

        # Drowsy/awake classification only runs once the user has explicitly started
        # calibration — band powers above still update the live bar chart either way.
        if self._eeg_calibration_active:
            status = self._eeg_detector.update(bands)
            detail = f"{int(self._eeg_detector.calibration_seconds_left())}s" if status == "calibrating" else ""
            self.eeg_status_ready.emit(status, detail)
        else:
            status = "idle"

        if self._eeg_recording and self._eeg_recorder is not None:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._eeg_recorder.write_row(ts, bands, ratio, status)
