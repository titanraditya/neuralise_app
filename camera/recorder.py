import csv
import datetime
import time
from pathlib import Path


class SessionRecorder:
    def __init__(self) -> None:
        self._file = None
        self._writer = None
        self._path: Path | None = None
        self._start_time: float | None = None

    def start(self, path: str | Path | None = None, output_dir: str = "recordings") -> Path:
        if path is not None:
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
        else:
            Path(output_dir).mkdir(exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._path = Path(output_dir) / f"session_{ts}.csv"
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        # New columns appended at the end, after the original 6 — keeps old session_*.csv
        # readers (fixed 6-column schema) working unchanged, per CLAUDE.md rule #5.
        self._writer.writerow(
            ["timestamp", "ear_left", "ear_right", "ear_avg", "perclos", "status", "t_rel", "face_detected"]
        )
        self._start_time = time.monotonic()
        return self._path

    def write_row(
        self,
        timestamp: str,
        ear_left: float | None,
        ear_right: float | None,
        ear_avg: float | None,
        perclos: float,
        status: str,
        face_detected: bool = True,
    ) -> None:
        if self._writer is None:
            return
        t_rel = time.monotonic() - self._start_time if self._start_time is not None else 0.0
        self._writer.writerow([
            timestamp,
            f"{ear_left:.4f}" if ear_left is not None else "",
            f"{ear_right:.4f}" if ear_right is not None else "",
            f"{ear_avg:.4f}" if ear_avg is not None else "",
            f"{perclos:.4f}",
            status,
            f"{t_rel:.3f}",
            "true" if face_detected else "false",
        ])

    def stop(self) -> Path | None:
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
        return self._path
