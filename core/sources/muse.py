import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams, BrainFlowPresets
from brainflow.data_filter import DataFilter
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt

from core.sources.base import EEGSource

CHANNEL_NAMES = ["TP9", "AF7", "AF8", "TP10"]
SAMPLE_RATE = 256.0
NOTCH_HZ = 50.0  # Indonesian mains frequency; use 60.0 elsewhere


class MuseEEGSource(EEGSource):
    """Streams real EEG data from a Muse S Athena headband via BrainFlow."""

    def __init__(self, serial_number: str = "") -> None:
        self._serial_number = serial_number
        self._board: BoardShim | None = None
        self._eeg_channels: list[int] = []
        self._sos_bp = butter(4, [1, 30], btype="band", fs=SAMPLE_RATE, output="sos")
        self._notch_b, self._notch_a = iirnotch(NOTCH_HZ, 30, fs=SAMPLE_RATE)

    def start(self) -> None:
        params = BrainFlowInputParams()
        params.serial_number = self._serial_number
        params.other_info = "preset=p1041;low_latency=true"
        params.timeout = 15

        BoardShim.disable_board_logger()
        board = BoardShim(BoardIds.MUSE_S_ATHENA_BOARD, params)
        board.prepare_session()
        board.start_stream()
        self._board = board
        self._eeg_channels = BoardShim.get_eeg_channels(
            BoardIds.MUSE_S_ATHENA_BOARD, BrainFlowPresets.DEFAULT_PRESET
        )

    def stop(self) -> None:
        if self._board is not None and self._board.is_prepared():
            self._board.stop_stream()
            self._board.release_session()
        self._board = None

    @property
    def channel_names(self) -> list[str]:
        return list(CHANNEL_NAMES)

    @property
    def sample_rate(self) -> float:
        return SAMPLE_RATE

    def get_samples(self) -> np.ndarray | None:
        if self._board is None:
            return None
        data = self._board.get_board_data(preset=BrainFlowPresets.DEFAULT_PRESET)
        if data.shape[1] == 0:
            return None
        return data[self._eeg_channels]

    def filter_for_display(self, segment: np.ndarray) -> np.ndarray:
        y = sosfiltfilt(self._sos_bp, segment)
        y = filtfilt(self._notch_b, self._notch_a, y)
        return y

    def check_contact(self, segment: np.ndarray) -> bool:
        # Floating/disconnected electrode -> signal pinned near rail or wildly out of range.
        return not (segment.min() < 1.0 or segment.max() > 6500 or np.ptp(segment) > 6000)

    def band_powers(self, segments: np.ndarray, good_channels: list[int]) -> list[float] | None:
        if not good_channels:
            return None
        try:
            bands, _ = DataFilter.get_avg_band_powers(segments, good_channels, int(SAMPLE_RATE), True)
            return list(bands)
        except Exception:
            return None
