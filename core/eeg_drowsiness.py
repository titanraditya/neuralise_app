import time

CALIBRATION_SECONDS = 30.0
# Flag drowsy once the (Theta+Alpha)/Beta ratio rises this many times above the
# subject's own calibrated baseline. Tunable — not a clinically validated cutoff.
DROWSY_RATIO_MULTIPLIER = 1.5


class EEGDrowsinessDetector:
    """Calibrates a per-subject (Theta+Alpha)/Beta baseline, then flags drowsiness via deviation from it.

    Band power alone varies too much between subjects (skull thickness, electrode
    impedance, individual baseline) for a fixed threshold to be reliable, so this
    requires an explicit calibration window — feed band powers while the subject
    rests with eyes open before treating update() results as meaningful.
    """

    def __init__(
        self,
        calibration_seconds: float = CALIBRATION_SECONDS,
        drowsy_multiplier: float = DROWSY_RATIO_MULTIPLIER,
    ) -> None:
        self._calibration_seconds = calibration_seconds
        self._drowsy_multiplier = drowsy_multiplier
        self._baseline: float | None = None
        self._calibration_samples: list[float] = []
        self._calibration_started_at: float | None = None

    def reset(self) -> None:
        self._baseline = None
        self._calibration_samples = []
        self._calibration_started_at = None

    @staticmethod
    def ratio(bands: list[float]) -> float:
        _delta, theta, alpha, beta, _gamma = bands
        return (theta + alpha) / beta if beta > 1e-6 else 0.0

    def calibration_seconds_left(self) -> float:
        if self._calibration_started_at is None:
            return self._calibration_seconds
        elapsed = time.time() - self._calibration_started_at
        return max(self._calibration_seconds - elapsed, 0.0)

    def update(self, bands: list[float]) -> str:
        """Feed fresh band powers (~1/s). Returns 'calibrating', 'awake', or 'drowsy'."""
        if self._calibration_started_at is None:
            self._calibration_started_at = time.time()

        r = self.ratio(bands)

        if self._baseline is None:
            self._calibration_samples.append(r)
            if self.calibration_seconds_left() > 0:
                return "calibrating"
            self._baseline = sum(self._calibration_samples) / len(self._calibration_samples)

        return "drowsy" if r > self._baseline * self._drowsy_multiplier else "awake"
