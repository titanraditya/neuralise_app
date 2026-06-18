import csv
import datetime
from pathlib import Path


class SessionRecorder:
    def __init__(self) -> None:
        self._file = None
        self._writer = None
        self._path: Path | None = None

    def start(self, output_dir: str = "recordings") -> Path:
        Path(output_dir).mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = Path(output_dir) / f"session_{ts}.csv"
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["timestamp", "ear_left", "ear_right", "ear_avg", "perclos", "status"])
        return self._path

    def write_row(
        self,
        timestamp: str,
        ear_left: float | None,
        ear_right: float | None,
        ear_avg: float | None,
        perclos: float,
        status: str,
    ) -> None:
        if self._writer is None:
            return
        self._writer.writerow([
            timestamp,
            f"{ear_left:.4f}" if ear_left is not None else "",
            f"{ear_right:.4f}" if ear_right is not None else "",
            f"{ear_avg:.4f}" if ear_avg is not None else "",
            f"{perclos:.4f}",
            status,
        ])

    def stop(self) -> Path | None:
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
        return self._path
