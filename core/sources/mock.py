import time

import numpy as np

from core.sources.base import CameraSource, EEGSource


# Drowsy stretch repeats every CYCLE_SECONDS, lasting DROWSY_SECONDS — long enough to push
# the 30s PERCLOS window above its 15% threshold so the "drowsy" status is exercised too.
CYCLE_SECONDS = 45.0
DROWSY_SECONDS = 5.0
NORMAL_EAR = 0.32
DROWSY_EAR = 0.15


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


class MockEEGSource(EEGSource):
    """Generates a synthetic multi-channel signal (sine mix + noise) standing in for a real headset."""

    _CHANNELS = ["Fp1", "Fp2", "O1", "O2"]
    _SAMPLE_RATE = 256.0

    def __init__(self) -> None:
        self._running = False
        self._t0 = 0.0
        self._last_t = 0.0
        self._rng = np.random.default_rng()

    def start(self) -> None:
        self._running = True
        self._t0 = time.time()
        self._last_t = 0.0

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

        return samples

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
