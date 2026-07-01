import numpy as np
import pylsl
from scipy.signal import butter, sosfiltfilt

from core.sources.base import EOGSource

PREFERRED_CHANNEL_LABEL = "A1"
RESOLVE_WAIT_SECONDS = 5.0
# Display-only cleanup: low-pass strips mains/HF noise (the real cause of the raw "solid block"
# look), and the DC offset is removed separately by subtracting the mean in filter_for_display.
# A high-pass low enough to strip DC would need a settling time longer than the 5s display
# window, producing a large, frozen-looking edge transient on every frame — so we avoid it.
# The drowsiness detector still runs on the raw chunk, so none of this touches blink/PERCLOS.
DISPLAY_LOWPASS_HZ = 10.0


class LSLEOGSource(EOGSource):
    """Streams a single EOG channel from whichever LSL outlet is active (e.g. PLUX OpenSignals).

    Stream discovery is generic — connects to any active LSL stream rather than a hardcoded
    name/type, since OpenSignals' stream identifiers vary by device/config. Within that stream,
    only the channel labelled "A1" is used (falls back to channel 0 if the stream's metadata
    doesn't label any channel "A1").
    """

    def __init__(self) -> None:
        self._inlet: pylsl.StreamInlet | None = None
        self._channel_index = 0
        self._sample_rate = 0.0
        self._sos_display = None  # built in start() once the stream's sample rate is known

    def start(self) -> None:
        streams = pylsl.resolve_streams(wait_time=RESOLVE_WAIT_SECONDS)
        if not streams:
            raise RuntimeError(
                "Tidak ada LSL stream yang terdeteksi — pastikan OpenSignals sedang streaming."
            )
        info = streams[0]
        self._channel_index = self._find_channel_index(info)
        self._sample_rate = info.nominal_srate() or 1.0
        self._sos_display = butter(
            4, DISPLAY_LOWPASS_HZ, btype="low", fs=self._sample_rate, output="sos"
        )
        self._inlet = pylsl.StreamInlet(info)

    @staticmethod
    def _find_channel_index(info: pylsl.StreamInfo) -> int:
        ch = info.desc().child("channels").child("channel")
        index = 0
        while ch.name() == "channel":
            if ch.child_value("label") == PREFERRED_CHANNEL_LABEL:
                return index
            ch = ch.next_sibling()
            index += 1
        return 0  # no "A1" label in the stream's metadata — default to the first channel

    def stop(self) -> None:
        self._inlet = None

    @property
    def channel_names(self) -> list[str]:
        return [PREFERRED_CHANNEL_LABEL]

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    def get_samples(self) -> np.ndarray | None:
        if self._inlet is None:
            return None
        chunk, _timestamps = self._inlet.pull_chunk()
        if not chunk:
            return None
        data = np.asarray(chunk, dtype=np.float32).T  # (n_channels, n_samples)
        return data[self._channel_index : self._channel_index + 1]

    def filter_for_display(self, segment: np.ndarray) -> np.ndarray:
        """Low-pass (DISPLAY_LOWPASS_HZ) + DC removal for a clean, centered live trace.
        Display-only — the drowsiness detector still runs on the raw chunk."""
        if self._sos_display is None:
            return segment
        try:
            y = sosfiltfilt(self._sos_display, segment)
        except ValueError:
            # Segment shorter than the filter's padding (e.g. a very low sample-rate stream) —
            # fall back to the raw trace rather than crash the acquisition loop.
            y = segment
        return y - y.mean()  # center on 0 without a high-pass's window-long edge transient
