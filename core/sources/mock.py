import time

import numpy as np

from core.sources.base import CameraSource, EEGSource, EOGSource


# Drowsy stretch repeats every CYCLE_SECONDS, lasting DROWSY_SECONDS — long enough to push
# the 30s PERCLOS window above its 15% threshold so the "drowsy" status is exercised too.
CYCLE_SECONDS = 45.0
DROWSY_SECONDS = 5.0
NORMAL_EAR = 0.32
DROWSY_EAR = 0.15

# Blink timing shared by MockEEGSource (frontal-channel EOG derived from the mock Muse stream)
# and MockEOGSource (standalone A1 stream): blinks come faster and last longer during the same
# drowsy stretch, so the blink-rate/EOG-PERCLOS analysis built on either has something to catch.
BLINK_INTERVAL_NORMAL = 4.0
BLINK_INTERVAL_DROWSY = 1.2
BLINK_DURATION_NORMAL = 0.15
BLINK_DURATION_DROWSY = 0.45


def _blink_pulse(t: np.ndarray, center: float, sigma: float) -> np.ndarray:
    return np.exp(-0.5 * ((t - center) / sigma) ** 2)


class MockCameraSource(CameraSource):
    """Generates a synthetic animated frame so the camera panel has something to render."""

    def __init__(self, width: int = 480, height: int = 360) -> None:
        self._width = width
        self._height = height
        self._running = False
        self._t0 = 0.0
        self._rng = np.random.default_rng()

    def start(self) -> None:
        self._running = True
        self._t0 = time.time()

    def stop(self) -> None:
        self._running = False

    def get_frame(self) -> np.ndarray | None:
        if not self._running:
            return None

        t = time.time() - self._t0
        yy, xx = np.mgrid[0:self._height, 0:self._width]
        cx = self._width / 2 + np.cos(t) * self._width * 0.25
        cy = self._height / 2 + np.sin(t * 0.8) * self._height * 0.25
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        pulse = (np.sin(dist / 12 - t * 4) + 1) / 2

        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[..., 0] = (pulse * 60).astype(np.uint8)
        frame[..., 1] = (pulse * 160).astype(np.uint8)
        frame[..., 2] = (pulse * 220).astype(np.uint8)
        return frame

    def get_ear(self) -> tuple[float, float, float] | None:
        """Synthetic eye-aspect-ratio reading standing in for EyeDetector's MediaPipe output."""
        if not self._running:
            return None

        t = time.time() - self._t0
        in_drowsy_stretch = (t % CYCLE_SECONDS) > (CYCLE_SECONDS - DROWSY_SECONDS)
        base = DROWSY_EAR if in_drowsy_stretch else NORMAL_EAR

        ear_left = max(0.02, base + self._rng.normal(0, 0.015))
        ear_right = max(0.02, base + self._rng.normal(0, 0.015))
        ear_avg = (ear_left + ear_right) / 2.0
        return ear_left, ear_right, ear_avg


# Frontal-channel blink deflection amplitude — large vs the ~unit-scale sine/noise so the derived
# mock Muse-EOG clears EOGDrowsinessDetector's mean±3·std closure threshold.
EOG_BLINK_AMPLITUDE = 5.0


class MockEEGSource(EEGSource):
    """Generates a synthetic multi-channel signal (sine mix + noise) standing in for a real headset.

    The frontal channel (_EOG_INDEX, standing in for the Muse AF7 electrode) also carries periodic
    blink deflections so the Muse-EOG derived from it in DeviceManager has real blinks to detect.
    """

    _CHANNELS = ["Fp1", "Fp2", "O1", "O2"]
    _EOG_INDEX = 1  # Fp2 stands in for Muse's AF7 — the frontal channel Muse-EOG is derived from
    _SAMPLE_RATE = 256.0

    def __init__(self) -> None:
        self._running = False
        self._t0 = 0.0
        self._last_t = 0.0
        self._rng = np.random.default_rng()
        self._next_blink_at = 0.0
        self._active_blinks: list[tuple[float, float]] = []

    def start(self) -> None:
        self._running = True
        self._t0 = time.time()
        self._last_t = 0.0
        self._next_blink_at = BLINK_INTERVAL_NORMAL
        self._active_blinks = []

    def stop(self) -> None:
        self._running = False

    @property
    def channel_names(self) -> list[str]:
        return list(self._CHANNELS)

    @property
    def sample_rate(self) -> float:
        return self._SAMPLE_RATE

    def get_samples(self) -> np.ndarray | None:
        if not self._running:
            return None

        now = time.time() - self._t0
        n_new = int((now - self._last_t) * self._SAMPLE_RATE)
        if n_new <= 0:
            return None

        t = self._last_t + np.arange(1, n_new + 1) / self._SAMPLE_RATE
        self._last_t = now

        n_channels = len(self._CHANNELS)
        samples = np.zeros((n_channels, n_new), dtype=np.float32)
        for ch in range(n_channels):
            alpha = np.sin(2 * np.pi * 10 * t + ch)
            theta = 0.5 * np.sin(2 * np.pi * 5 * t + ch * 0.5)
            noise = self._rng.normal(0, 0.2, n_new)
            samples[ch] = alpha + theta + noise

        samples[self._EOG_INDEX] += self._blink_train(t)
        return samples

    def _blink_train(self, t: np.ndarray) -> np.ndarray:
        """Gaussian blink deflections on the frontal channel, faster/longer during the drowsy
        stretch (same cycle as MockCameraSource.get_ear), scheduled the same way as MockEOGSource."""
        now = t[-1]
        in_drowsy_stretch = (now % CYCLE_SECONDS) > (CYCLE_SECONDS - DROWSY_SECONDS)
        blink_duration = BLINK_DURATION_DROWSY if in_drowsy_stretch else BLINK_DURATION_NORMAL
        blink_interval = BLINK_INTERVAL_DROWSY if in_drowsy_stretch else BLINK_INTERVAL_NORMAL
        sigma = blink_duration / 2.5

        while self._next_blink_at < t[-1] + 4 * sigma:
            self._active_blinks.append((self._next_blink_at, sigma))
            self._next_blink_at += blink_interval

        pulse = np.zeros_like(t)
        for center, b_sigma in self._active_blinks:
            pulse += EOG_BLINK_AMPLITUDE * _blink_pulse(t, center, b_sigma)

        cutoff = t[0] - 4 * sigma
        self._active_blinks = [(c, s) for c, s in self._active_blinks if c + 4 * s >= cutoff]
        return pulse.astype(np.float32)

    @property
    def supports_eog(self) -> bool:
        return True

    @property
    def eog_channel_name(self) -> str:
        return self._CHANNELS[self._EOG_INDEX]

    @property
    def eog_channel_indices(self) -> tuple[int, ...]:
        return (self._EOG_INDEX,)

    def derive_eog(self, samples: np.ndarray) -> np.ndarray | None:
        if samples.shape[0] <= self._EOG_INDEX:
            return None
        return samples[self._EOG_INDEX]

    def band_powers(self, segments: np.ndarray, good_channels: list[int]) -> list[float] | None:
        """Synthetic [delta, theta, alpha, beta, gamma], with theta+alpha spiking on the same
        drowsy-stretch cycle as MockCameraSource so the EEG ratio detector has something to catch."""
        if not good_channels:
            return None

        t = time.time() - self._t0
        in_drowsy_stretch = (t % CYCLE_SECONDS) > (CYCLE_SECONDS - DROWSY_SECONDS)

        delta = float(self._rng.uniform(0.5, 1.5))
        beta = float(self._rng.uniform(0.8, 1.5))
        gamma = float(self._rng.uniform(0.1, 0.4))
        if in_drowsy_stretch:
            theta = float(self._rng.uniform(1.5, 2.5))
            alpha = float(self._rng.uniform(1.5, 2.5))
        else:
            theta = float(self._rng.uniform(0.3, 0.8))
            alpha = float(self._rng.uniform(0.3, 0.8))

        return [delta, theta, alpha, beta, gamma]


EOG_SAMPLE_RATE = 200.0


class MockEOGSource(EOGSource):
    """Generates a synthetic single-channel ("A1") EOG signal: baseline noise plus periodic
    blink-like deflections, standing in for an LSL/OpenSignals stream."""

    def __init__(self) -> None:
        self._running = False
        self._t0 = 0.0
        self._last_t = 0.0
        self._next_blink_at = 0.0
        self._active_blinks: list[tuple[float, float]] = []  # (center, sigma) still in range
        self._rng = np.random.default_rng()

    def start(self) -> None:
        self._running = True
        self._t0 = time.time()
        self._last_t = 0.0
        self._next_blink_at = BLINK_INTERVAL_NORMAL
        self._active_blinks = []

    def stop(self) -> None:
        self._running = False

    @property
    def channel_names(self) -> list[str]:
        return ["A1"]

    @property
    def sample_rate(self) -> float:
        return EOG_SAMPLE_RATE

    def get_samples(self) -> np.ndarray | None:
        if not self._running:
            return None

        now = time.time() - self._t0
        n_new = int((now - self._last_t) * EOG_SAMPLE_RATE)
        if n_new <= 0:
            return None

        t = self._last_t + np.arange(1, n_new + 1) / EOG_SAMPLE_RATE
        self._last_t = now

        in_drowsy_stretch = (now % CYCLE_SECONDS) > (CYCLE_SECONDS - DROWSY_SECONDS)
        blink_duration = BLINK_DURATION_DROWSY if in_drowsy_stretch else BLINK_DURATION_NORMAL
        blink_interval = BLINK_INTERVAL_DROWSY if in_drowsy_stretch else BLINK_INTERVAL_NORMAL
        sigma = blink_duration / 2.5

        # Schedule blink centers as soon as this chunk reaches their leading edge (~4 sigma
        # before the peak), then keep evaluating each one across every later chunk its Gaussian
        # tail still reaches — a single blink's pulse spans many chunks, not just the one
        # nearest its center.
        while self._next_blink_at < t[-1] + 4 * sigma:
            self._active_blinks.append((self._next_blink_at, sigma))
            self._next_blink_at += blink_interval

        signal = self._rng.normal(0, 0.02, n_new)
        for center, b_sigma in self._active_blinks:
            signal += _blink_pulse(t, center, b_sigma)

        cutoff = t[0] - 4 * sigma
        self._active_blinks = [(c, s) for c, s in self._active_blinks if c + 4 * s >= cutoff]

        return signal.reshape(1, -1).astype(np.float32)
