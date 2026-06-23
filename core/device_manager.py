import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from camera.camera_thread import CameraThread
from core.eeg_drowsiness import EEGDrowsinessDetector
from core.eeg_recorder import EEGRecorder
from core.sources.base import EEGSource
from core.sources.mock import MockEEGSource
from core.sources.muse import MuseEEGSource

EEG_POLL_MS = 33  # raw sample acquisition cadence — matches the old ui/widgets/eeg_panel.py REFRESH_MS
EEG_WINDOW_SECONDS = 5.0  # matches the old ui/widgets/eeg_panel.py WINDOW_SECONDS
BAND_UPDATE_EVERY_N_POLLS = round(1000 / EEG_POLL_MS)  # ~once per second
DISPLAY_UPDATE_EVERY_N_POLLS = 3  # ~10Hz filtered-segment redraw; filtering+plotting at the
# full 30Hz poll rate was the main cause of GUI lag on EEG connect (sosfiltfilt/filtfilt over
# a 5s window, 4 channels, 30x/s). Must divide BAND_UPDATE_EVERY_N_POLLS so contact_ok is
# always fresh on a band-update tick — see the assert below.
assert BAND_UPDATE_EVERY_N_POLLS % DISPLAY_UPDATE_EVERY_N_POLLS == 0


class _EEGWorker(QThread):
    """Owns one EEG connection end-to-end — connect, acquisition loop, filtering, band power,
    and recording — entirely off the GUI thread (mirrors camera/camera_thread.py's CameraThread
    pattern: a plain run() loop controlled by self._running, with start_recording()/
    stop_recording() called directly from the GUI thread to flip flags the loop reads).

    This replaces a QTimer that used to drive the same work in the GUI thread: every poll did
    blocking BrainFlow reads + zero-phase filtering, which made the whole window feel heavy
    while EEG was connected.
    """

    connected = Signal(list)  # channel_names
    connect_failed = Signal(str)
    frame_ready = Signal(object, object)  # display_segments: list[np.ndarray], contact_ok: list[bool]
    bands_ready = Signal(object)  # bands: list[float] (delta..gamma)
    status_ready = Signal(str, str)  # status ('calibrating'|'awake'|'drowsy'), detail text

    def __init__(self, source: EEGSource, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source = source
        self._running = False
        self._detector = EEGDrowsinessDetector()
        self._calibration_active = False
        self._recorder: EEGRecorder | None = None
        self._recording = False

    # -- called directly from the GUI thread; same plain-flag pattern as CameraThread --

    def start_calibration(self) -> None:
        self._detector.reset()
        self._calibration_active = True

    def start_recording(self, path: str | Path) -> None:
        recorder = EEGRecorder()
        recorder.start(path)
        self._recorder = recorder
        self._recording = True

    def stop_recording(self) -> None:
        self._recording = False
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None

    def stop(self) -> None:
        self._running = False
        self.wait()  # blocks until run()'s finally (source.stop()) has actually completed

    def run(self) -> None:
        try:
            self._source.start()
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a connection error
            self.connect_failed.emit(str(exc))
            return

        self._running = True
        self.connected.emit(list(self._source.channel_names))

        window_points = int(EEG_WINDOW_SECONDS * self._source.sample_rate)
        buffers = [np.zeros(window_points, dtype=np.float32) for _ in self._source.channel_names]
        samples_seen = 0
        poll_count = 0
        contact_ok = [True] * len(buffers)

        try:
            while self._running:
                samples = self._source.get_samples()
                if samples is not None and samples.shape[1] > 0:
                    samples_seen += samples.shape[1]
                    for i in range(len(buffers)):
                        buffers[i] = np.concatenate([buffers[i], samples[i]])[-len(buffers[i]):]

                # Same warm-up guard as before: don't trust check_contact/filter_for_display on
                # a still mostly-zero buffer right after connecting.
                warmed_up = samples_seen >= self._source.sample_rate
                poll_count += 1
                display_tick = (not warmed_up) or (poll_count % DISPLAY_UPDATE_EVERY_N_POLLS == 0)

                if display_tick:
                    if warmed_up:
                        contact_ok = [self._source.check_contact(seg) for seg in buffers]
                        # Filter every channel, even a bad-contact one — an unfiltered raw
                        # segment can sit far outside the other channels' range (pinned rail,
                        # motion artifact) and blow up the shared y-axis autorange. contact_ok
                        # still excludes it from band power below and still drives the
                        # "NO CONTACT" label/tint in the UI.
                        display_segments = [self._source.filter_for_display(seg) for seg in buffers]
                    else:
                        contact_ok = [True] * len(buffers)
                        display_segments = list(buffers)
                    self.frame_ready.emit(display_segments, contact_ok)

                if warmed_up and poll_count % BAND_UPDATE_EVERY_N_POLLS == 0:
                    self._emit_bands(buffers, contact_ok)

                self.msleep(EEG_POLL_MS)
        finally:
            self._source.stop()

    def _emit_bands(self, buffers: list[np.ndarray], contact_ok: list[bool]) -> None:
        good_idx = [i for i, ok in enumerate(contact_ok) if ok]
        if not good_idx:
            return

        bands = self._source.band_powers(np.vstack(buffers), good_idx)
        if bands is None:
            return

        self.bands_ready.emit(bands)
        ratio = EEGDrowsinessDetector.ratio(bands)

        # Drowsy/awake classification only runs once the user has explicitly started
        # calibration — band powers above still update the live bar chart either way.
        if self._calibration_active:
            status = self._detector.update(bands)
            detail = f"{int(self._detector.calibration_seconds_left())}s" if status == "calibrating" else ""
            self.status_ready.emit(status, detail)
        else:
            status = "idle"

        if self._recording and self._recorder is not None:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._recorder.write_row(ts, bands, ratio, status)


class DeviceManager(QObject):
    """Rig-level owner of the camera + EEG connections (CLAUDE.md target architecture).

    Connect once; streaming continues regardless of whether a recording Session is active —
    connect/disconnect is decoupled from start/stop recording, and from any particular Session.
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

        self._eeg_worker: _EEGWorker | None = None
        self._eeg_channel_names: list[str] = []

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
    # never an automatic side effect of connect_eeg() or creating a Session. All polling,
    # filtering, and band power work happens inside _EEGWorker's thread, not here.
    # ------------------------------------------------------------------

    @property
    def eeg_connected(self) -> bool:
        return self._eeg_worker is not None

    @property
    def eeg_channel_names(self) -> list[str]:
        return list(self._eeg_channel_names)

    def connect_eeg(self, serial_number: str = "") -> None:
        """Connects asynchronously: everything in _EEGWorker.run() (including the blocking BLE
        pairing) happens on a worker thread so it can't freeze the UI. Result arrives via
        eeg_connected_changed/eeg_connect_failed, bracketed by eeg_connecting_changed(True)/(False)."""
        if self._eeg_worker is not None:
            return
        source = MockEEGSource() if self._use_mock else MuseEEGSource(serial_number)
        worker = _EEGWorker(source, self)
        worker.connected.connect(self._on_eeg_connected)
        worker.connect_failed.connect(self._on_eeg_connect_failed)
        worker.frame_ready.connect(self.eeg_frame_ready)
        worker.bands_ready.connect(self.eeg_bands_ready)
        worker.status_ready.connect(self.eeg_status_ready)
        worker.finished.connect(worker.deleteLater)
        self._eeg_worker = worker
        self.eeg_connecting_changed.emit(True)
        worker.start()

    def _on_eeg_connected(self, channel_names: list[str]) -> None:
        self._eeg_channel_names = channel_names
        self.eeg_connecting_changed.emit(False)
        self.eeg_connected_changed.emit(True)

    def _on_eeg_connect_failed(self, message: str) -> None:
        self._eeg_worker = None
        self.eeg_connecting_changed.emit(False)
        self.eeg_connect_failed.emit(message)

    def disconnect_eeg(self) -> None:
        if self._eeg_worker is None:
            return
        self._eeg_worker.stop()  # blocks until the acquisition loop + source.stop() finish
        self._eeg_worker = None
        self._eeg_channel_names = []
        self.eeg_connected_changed.emit(False)

    def start_eeg_calibration(self) -> None:
        """(Re-)run the 30s baseline, triggered only by an explicit user action (a dedicated
        "Kalibrasi EEG" button) — never automatically on connect_eeg() or when a Session is
        created, so the subject can get settled first. Also doubles as recalibrate: calling
        this again later resets the baseline without reconnecting the EEG source. Once active,
        calibration stays active across a BLE drop/reconnect.
        """
        if self._eeg_worker is not None:
            self._eeg_worker.start_calibration()

    def start_eeg_recording(self, path: str | Path) -> None:
        if self._eeg_worker is not None:
            self._eeg_worker.start_recording(path)

    def stop_eeg_recording(self) -> None:
        if self._eeg_worker is not None:
            self._eeg_worker.stop_recording()

    def shutdown(self) -> None:
        """Stop all acquisition threads/connections cleanly (fix finding #2: call this from the
        main window's closeEvent so a window close can never leak a running CameraThread)."""
        self.disconnect_camera()
        self.disconnect_eeg()
