import csv
from pathlib import Path


class EEGRecorder:
    """Writes one row per band-power update (~1/s): timestamp, band powers, ratio, drowsy status.

    Mirrors camera/recorder.py's SessionRecorder shape (start/write_row/stop) for the EEG modality.
    """

    def __init__(self) -> None:
        self._file = None
        self._writer = None
        self._path: Path | None = None

    def start(self, path: str | Path) -> Path:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(
            ["timestamp", "delta", "theta", "alpha", "beta", "gamma", "ratio_theta_alpha_beta", "status"]
        )
        return self._path

    def write_row(
        self,
        timestamp: str,
        bands: list[float],
        ratio: float,
        status: str,
    ) -> None:
        if self._writer is None:
            return
        delta, theta, alpha, beta, gamma = bands
        self._writer.writerow([
            timestamp,
            f"{delta:.4f}",
            f"{theta:.4f}",
            f"{alpha:.4f}",
            f"{beta:.4f}",
            f"{gamma:.4f}",
            f"{ratio:.4f}",
            status,
        ])

    def stop(self) -> Path | None:
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
        return self._path
