import time

import numpy as np

from core.sources.base import CameraSource, EEGSource


class MockCameraSource(CameraSource):
    """Generates a synthetic animated frame so the camera panel has something to render."""

    def __init__(self, width: int = 480, height: int = 360) -> None:
        self._width = width
        self._height = height
        self._running = False
        self._t0 = 0.0

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
