import time
from collections import deque

import numpy as np

CALIBRATION_SECONDS = 30.0
# Closure flagged when |sample - baseline_mean| exceeds this many baseline std devs — abs()
# so it works regardless of the EOG deflection's polarity (montage/electrode-dependent).
THRESHOLD_MULTIPLIER = 3.0
MIN_BLINK_SECONDS = 0.05  # shorter runs are noise, not a real eyelid closure
BLINK_RATE_WINDOW_SECONDS = 60.0
PERCLOS_WINDOW_SECONDS = 30.0
# Same 15% cutoff as the camera's PERCLOS (camera/perclos.py) for a same-length window, picked
# by analogy — not a clinically validated number, same caveat as EEGDrowsinessDetector's ratio.
PERCLOS_DROWSY_THRESHOLD = 0.15


class EOGDrowsinessDetector:
    """Calibrates a per-subject closure threshold from 30s of baseline EOG (channel A1), then
    derives two metrics from a continuous "is eyelid closed" stream: blink rate (blinks/min,
    60s window) and EOG-PERCLOS (fraction of the last 30s spent above threshold).

    Reported as a standalone metric/status only — deliberately not wired into the camera+EEG
    OR-rule fusion in ui/widgets/status_panel.py.
    """

    def __init__(
        self,
        sample_rate: float,
        calibration_seconds: float = CALIBRATION_SECONDS,
        threshold_multiplier: float = THRESHOLD_MULTIPLIER,
    ) -> None:
        self._sample_rate = sample_rate
        self._calibration_seconds = calibration_seconds
        self._threshold_multiplier = threshold_multiplier

        self._baseline_mean: float | None = None
        self._baseline_std: float | None = None
        self._calibration_samples: list[float] = []
        self._calibration_started_at: float | None = None

        self._was_closed = False
        self._closure_started_at: float | None = None
        self._blink_times: deque[float] = deque()
        self._closure_window: deque[tuple[float, bool]] = deque()

    def reset(self) -> None:
        self._baseline_mean = None
        self._baseline_std = None
        self._calibration_samples = []
        self._calibration_started_at = None
        self._was_closed = False
        self._closure_started_at = None
        self._blink_times.clear()
        self._closure_window.clear()

    def calibration_seconds_left(self) -> float:
        if self._calibration_started_at is None:
            return self._calibration_seconds
        elapsed = time.time() - self._calibration_started_at
        return max(self._calibration_seconds - elapsed, 0.0)

    def update(self, segment: np.ndarray) -> str:
        """Feed the latest raw EOG chunk (new samples since the last call, channel A1 only).
        Returns 'calibrating', 'awake', or 'drowsy'."""
        if self._calibration_started_at is None:
            self._calibration_started_at = time.time()

        if self._baseline_std is None:
            self._calibration_samples.extend(float(v) for v in segment)
            if self.calibration_seconds_left() > 0:
                return "calibrating"
            self._baseline_mean = float(np.mean(self._calibration_samples))
            self._baseline_std = max(float(np.std(self._calibration_samples)), 1e-9)
            self._calibration_samples = []

        self._classify_chunk(segment)
        return "drowsy" if self.perclos() > PERCLOS_DROWSY_THRESHOLD else "awake"

    def _classify_chunk(self, segment: np.ndarray) -> None:
        if len(segment) == 0:
            return
        now = time.time()
        dt = 1.0 / self._sample_rate
        above = np.abs(segment - self._baseline_mean) > self._threshold_multiplier * self._baseline_std

        for i, is_above in enumerate(above):
            sample_time = now - dt * (len(above) - 1 - i)
            is_above = bool(is_above)
            self._closure_window.append((sample_time, is_above))

            if is_above and not self._was_closed:
                self._closure_started_at = sample_time
            elif not is_above and self._was_closed:
                duration = sample_time - (self._closure_started_at or sample_time)
                if duration >= MIN_BLINK_SECONDS:
                    self._blink_times.append(sample_time)
            self._was_closed = is_above

        self._trim(now)

    def _trim(self, now: float) -> None:
        blink_cutoff = now - BLINK_RATE_WINDOW_SECONDS
        while self._blink_times and self._blink_times[0] < blink_cutoff:
            self._blink_times.popleft()
        perclos_cutoff = now - PERCLOS_WINDOW_SECONDS
        while self._closure_window and self._closure_window[0][0] < perclos_cutoff:
            self._closure_window.popleft()

    def blink_rate(self) -> float:
        """Blinks per minute, derived from the last BLINK_RATE_WINDOW_SECONDS."""
        return len(self._blink_times) * (60.0 / BLINK_RATE_WINDOW_SECONDS)

    def perclos(self) -> float:
        """Fraction of the last PERCLOS_WINDOW_SECONDS spent above the closure threshold."""
        if not self._closure_window:
            return 0.0
        return sum(1 for _, closed in self._closure_window if closed) / len(self._closure_window)
