import time
from collections import deque

WINDOW_SECONDS = 30
EAR_THRESHOLD = 0.25
DROWSY_THRESHOLD = 0.15  # 15 %


class PerclosCalculator:
    def __init__(
        self,
        window_seconds: int = WINDOW_SECONDS,
        ear_threshold: float = EAR_THRESHOLD,
        drowsy_threshold: float = DROWSY_THRESHOLD,
    ) -> None:
        self._window = window_seconds
        self._ear_threshold = ear_threshold
        self._drowsy_threshold = drowsy_threshold
        self._buffer: deque[tuple[float, bool]] = deque()

    def update(self, ear_avg: float | None) -> float:
        now = time.time()
        cutoff = now - self._window
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

        if ear_avg is not None:
            self._buffer.append((now, ear_avg < self._ear_threshold))

        if not self._buffer:
            return 0.0

        return sum(1 for _, closed in self._buffer if closed) / len(self._buffer)

    def is_drowsy(self, perclos: float) -> bool:
        return perclos > self._drowsy_threshold

    def reset(self) -> None:
        self._buffer.clear()
