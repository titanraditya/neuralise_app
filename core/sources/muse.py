import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams, BrainFlowPresets
from brainflow.data_filter import DataFilter
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt

from core.sources.base import EEGSource

CHANNEL_NAMES = ["TP9", "AF7", "AF8", "TP10"]
SAMPLE_RATE = 256.0
NOTCH_HZ = 50.0  # Indonesian mains frequency; use 60.0 elsewhere

# EOG-from-EEG: AF7 sits on the left forehead just above the eye, so it picks up eye-blink /
# eyelid-closure potentials (vertical EOG) as a strong low-frequency deflection — exactly what
# EOGDrowsinessDetector's blink-rate/PERCLOS math needs. A single frontal channel is used (not a
# bipolar AF7-AF8 pair, which would largely cancel the symmetric vertical blink signal).
EOG_CHANNEL_INDEX = CHANNEL_NAMES.index("AF7")
EOG_CHANNEL_NAME = "AF7"
EOG_DISPLAY_LOWPASS_HZ = 10.0  # matches the LSL/OpenSignals EOG display filter (core/sources/eog_lsl.py)


class MuseEEGSource(EEGSource):
    """Streams real EEG data from a Muse S Athena headband via BrainFlow."""

    def __init__(self, serial_number: str = "") -> None:
        self._serial_number = serial_number
        self._board: BoardShim | None = None
        self._eeg_channels: list[int] = []
        self._sos_bp = butter(4, [1, 30], btype="band", fs=SAMPLE_RATE, output="sos")
        self._notch_b, self._notch_a = iirnotch(NOTCH_HZ, 30, fs=SAMPLE_RATE)
        self._sos_eog = butter(4, EOG_DISPLAY_LOWPASS_HZ, btype="low", fs=SAMPLE_RATE, output="sos")

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

    # -- EOG derived from the AF7 frontal electrode (see EOG_CHANNEL_INDEX comment above) --

    @property
    def supports_eog(self) -> bool:
        return True

    @property
    def eog_channel_name(self) -> str:
        return EOG_CHANNEL_NAME

    @property
    def eog_channel_indices(self) -> tuple[int, ...]:
        return (EOG_CHANNEL_INDEX,)

    def derive_eog(self, samples: np.ndarray) -> np.ndarray | None:
        # samples is (n_channels, n_samples) in CHANNEL_NAMES order (see get_samples).
        if samples.shape[0] <= EOG_CHANNEL_INDEX:
            return None
        return samples[EOG_CHANNEL_INDEX]

    def filter_eog_for_display(self, segment: np.ndarray) -> np.ndarray:
        try:
            y = sosfiltfilt(self._sos_eog, segment)
        except ValueError:
            y = segment  # segment shorter than the filter padding — fall back to raw
        return y - y.mean()  # center on 0 without a high-pass's window-long edge transient
