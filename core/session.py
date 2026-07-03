import datetime
import json
import shutil
from pathlib import Path

RECORDINGS_DIR = Path("recordings")


class Session:
    """One research run for one subject — owns recordings/<session_id>/ and its meta.json.

    Deliberately has no dependency on DeviceManager or the recorders: callers write into
    camera_csv_path / eeg_csv_path and flip the has_* flags themselves, then call write_meta().
    """

    def __init__(
        self,
        subject_code: str = "",
        noise_condition: str = "",
        base_dir: str | Path = RECORDINGS_DIR,
    ) -> None:
        self.session_id = f"SESS_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.subject_code = subject_code
        self.noise_condition = noise_condition
        self.started_at = datetime.datetime.now().isoformat(timespec="seconds")
        self.ended_at: str | None = None

        self.has_camera = False
        self.has_eeg = False
        self.has_eog = False
        self.has_museeog = False
        self.has_dass21 = False
        self.has_sart = False

        self.dir = Path(base_dir) / self.session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.write_meta()

    @property
    def camera_csv_path(self) -> Path:
        return self.dir / "camera.csv"

    @property
    def eeg_csv_path(self) -> Path:
        return self.dir / "eeg.csv"

    @property
    def eog_csv_path(self) -> Path:
        return self.dir / "eog.csv"

    @property
    def museeog_csv_path(self) -> Path:
        """EOG derived from the Muse frontal electrode — a separate file from the OpenSignals/
        BITalino eog.csv so the two EOG modalities stay independent."""
        return self.dir / "eog_muse.csv"

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    @property
    def dass21_path(self) -> Path:
        return self.dir / "dass21.json"

    @property
    def sart_path(self) -> Path:
        return self.dir / "sart.json"

    @classmethod
    def load(cls, session_dir: str | Path) -> "Session":
        """Reconstruct a Session from an existing recordings/<session_id>/meta.json.

        Unlike __init__, this never mints a new session_id or touches the folder — it just
        re-hydrates an existing one (for the history drawer, or for re-opening a questionnaire
        against a past session).
        """
        session_dir = Path(session_dir)
        meta = json.loads((session_dir / "meta.json").read_text())
        session = cls.__new__(cls)
        session.session_id = meta.get("session_id", session_dir.name)
        session.subject_code = meta.get("subject_code", "")
        session.noise_condition = meta.get("noise_condition", "")
        session.started_at = meta.get("started_at", "")
        session.ended_at = meta.get("ended_at")
        session.has_camera = meta.get("has_camera", False)
        session.has_eeg = meta.get("has_eeg", False)
        session.has_eog = meta.get("has_eog", False)
        session.has_museeog = meta.get("has_museeog", False)
        session.has_dass21 = meta.get("has_dass21", False)
        session.has_sart = meta.get("has_sart", False)
        session.dir = session_dir
        return session

    @staticmethod
    def list_all(base_dir: str | Path = RECORDINGS_DIR) -> list[Path]:
        """Session folders under recordings/, newest first. Skips legacy loose files that
        predate the Session/meta.json layout (questionnaire_*.json, session_*.csv, sart_*.json).
        """
        base = Path(base_dir)
        if not base.exists():
            return []
        return sorted(
            (p for p in base.iterdir() if p.is_dir() and (p / "meta.json").exists()),
            key=lambda p: p.name,
            reverse=True,
        )

    def write_meta(self) -> Path:
        meta = {
            "session_id": self.session_id,
            "subject_code": self.subject_code,
            "noise_condition": self.noise_condition,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "has_camera": self.has_camera,
            "has_eeg": self.has_eeg,
            "has_eog": self.has_eog,
            "has_museeog": self.has_museeog,
            "has_dass21": self.has_dass21,
            "has_sart": self.has_sart,
        }
        self.meta_path.write_text(json.dumps(meta, indent=2))
        return self.meta_path

    def end(self) -> None:
        self.ended_at = datetime.datetime.now().isoformat(timespec="seconds")
        self.write_meta()

    def duration_str(self) -> str | None:
        """HH:MM:SS between started_at and ended_at — None while the session is still active
        (ended_at not set yet)."""
        if not self.ended_at:
            return None
        start = datetime.datetime.fromisoformat(self.started_at)
        end = datetime.datetime.fromisoformat(self.ended_at)
        total_seconds = max(int((end - start).total_seconds()), 0)
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def delete(self) -> None:
        """Permanently remove recordings/<session_id>/ and everything in it. Irreversible —
        callers are responsible for confirming with the user first."""
        shutil.rmtree(self.dir)
