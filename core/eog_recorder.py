import csv
import time
from pathlib import Path


class EOGRecorder:
    """Writes one row per classified chunk: timestamp, blink rate, EOG-PERCLOS, status.

    Mirrors core/eeg_recorder.py's shape (start/write_row/stop) for the EOG modality.
    """

    def __init__(self) -> None:
        self._file = None
        self._writer = None
        self._path: Path | None = None
        self._start_time: float | None = None

    def start(self, path: str | Path) -> Path:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(
            ["timestamp", "blink_rate", "eog_perclos", "status", "t_rel", "contact_ok"]
        )
        self._start_time = time.monotonic()
        return self._path

    def write_row(
        self,
        timestamp: str,
        blink_rate: float,
        eog_perclos: float,
        status: str,
        contact_ok: bool = True,
    ) -> None:
        if self._writer is None:
            return
        t_rel = time.monotonic() - self._start_time if self._start_time is not None else 0.0
        self._writer.writerow([
            timestamp,
            f"{blink_rate:.4f}",
            f"{eog_perclos:.4f}",
            status,
            f"{t_rel:.3f}",
            "true" if contact_ok else "false",
        ])

    def stop(self) -> Path | None:
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
        return self._path
