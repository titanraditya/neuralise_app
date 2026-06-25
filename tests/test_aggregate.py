import csv
import json
import tempfile
import unittest
from pathlib import Path

from core.aggregate import summarize_session


def _write_meta(session_dir: Path, has_camera: bool = True, has_eeg: bool = True) -> None:
    meta = {
        "session_id": session_dir.name,
        "subject_code": "S01",
        "noise_condition": "quiet",
        "started_at": "2026-06-24T10:00:00",
        "ended_at": "2026-06-24T10:05:00",
        "has_camera": has_camera,
        "has_eeg": has_eeg,
        "has_dass21": False,
        "has_sart": False,
    }
    (session_dir / "meta.json").write_text(json.dumps(meta))


def _write_camera_csv(session_dir: Path, rows: list[tuple[float, float, bool]]) -> None:
    with (session_dir / "camera.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["timestamp", "ear_left", "ear_right", "ear_avg", "perclos", "status", "t_rel", "face_detected"]
        )
        for t_rel, perclos, face_detected in rows:
            status = "drowsy" if perclos > 0.15 else "normal"
            writer.writerow([
                "00:00:00.000", "0.2000", "0.2000", "0.2000", f"{perclos:.4f}", status,
                f"{t_rel:.3f}", "true" if face_detected else "false",
            ])


def _write_eeg_csv(session_dir: Path, rows: list[tuple[float, float, bool]]) -> None:
    with (session_dir / "eeg.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["timestamp", "delta", "theta", "alpha", "beta", "gamma", "ratio_theta_alpha_beta", "status",
             "t_rel", "contact_ok"]
        )
        for t_rel, ratio, contact_ok in rows:
            writer.writerow([
                "00:00:00.000", "1.0000", "1.0000", "1.0000", "1.0000", "0.2000", f"{ratio:.4f}", "idle",
                f"{t_rel:.3f}", "true" if contact_ok else "false",
            ])


class SummarizeSessionTests(unittest.TestCase):
    def _session_dir(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        session_dir = Path(tmp.name) / "SESS_TEST"
        session_dir.mkdir()
        return session_dir

    def test_narrow_spike_is_not_an_episode(self):
        """A 1s blip above threshold is shorter than the 3s on_seconds debounce, so it must
        not be confirmed as an episode."""
        session_dir = self._session_dir()
        _write_meta(session_dir)
        rows = [(30.0 + i, 0.30 if i == 5 else 0.05, True) for i in range(40)]
        _write_camera_csv(session_dir, rows)
        _write_eeg_csv(session_dir, [])

        summary = summarize_session(session_dir)
        self.assertEqual(summary["camera"]["episode_count"], 0)
        self.assertIsNone(summary["camera"]["onset_latency_s"])

    def test_sustained_signal_after_warmup_is_an_episode(self):
        session_dir = self._session_dir()
        _write_meta(session_dir)
        rows = [(30.0 + i, 0.30 if 5 <= i < 15 else 0.05, True) for i in range(40)]
        _write_camera_csv(session_dir, rows)
        _write_eeg_csv(session_dir, [])

        summary = summarize_session(session_dir)
        self.assertEqual(summary["camera"]["episode_count"], 1)
        self.assertAlmostEqual(summary["camera"]["onset_latency_s"], 35.0)
        self.assertAlmostEqual(summary["camera"]["longest_episode_s"], 10.0)

    def test_warmup_window_is_discarded(self):
        """A sustained high signal entirely inside the first 30s is long enough to qualify as
        an episode if warm-up weren't discarded first — it must produce nothing."""
        session_dir = self._session_dir()
        _write_meta(session_dir)
        rows = [(float(i), 0.30, True) for i in range(30)]
        rows += [(30.0 + i, 0.05, True) for i in range(30)]
        _write_camera_csv(session_dir, rows)
        _write_eeg_csv(session_dir, [])

        summary = summarize_session(session_dir)
        self.assertEqual(summary["camera"]["episode_count"], 0)

    def test_invalid_segment_is_discarded(self):
        """The only sustained high stretch has face_detected=False throughout, so it must be
        dropped before episode detection ever sees it."""
        session_dir = self._session_dir()
        _write_meta(session_dir)
        rows = [
            (30.0 + i, 0.30 if 5 <= i < 15 else 0.05, not (5 <= i < 15))
            for i in range(40)
        ]
        _write_camera_csv(session_dir, rows)
        _write_eeg_csv(session_dir, [])

        summary = summarize_session(session_dir)
        self.assertEqual(summary["camera"]["episode_count"], 0)

    def test_fusion_or_rule_picks_up_eeg_only_episode(self):
        session_dir = self._session_dir()
        _write_meta(session_dir)
        cam_rows = [(30.0 + i, 0.05, True) for i in range(40)]
        _write_camera_csv(session_dir, cam_rows)

        # 30s calibration window at ratio=1.0 (-> baseline=1.0), then a sustained spike to
        # ratio_norm=2.0 (above the 1.5x DROWSY_RATIO_MULTIPLIER threshold), then back down.
        eeg_rows = [(30.0 + i, 1.0, True) for i in range(30)]
        eeg_rows += [(60.0 + i, 2.0, True) for i in range(10)]
        eeg_rows += [(70.0 + i, 1.0, True) for i in range(10)]
        _write_eeg_csv(session_dir, eeg_rows)

        summary = summarize_session(session_dir)
        self.assertEqual(summary["eeg"]["episode_count"], 1)
        self.assertAlmostEqual(summary["eeg"]["onset_latency_s"], 60.0)
        self.assertEqual(summary["camera"]["episode_count"], 0)
        self.assertEqual(summary["fusion"]["episode_count"], 1)
        self.assertAlmostEqual(summary["fusion"]["onset_latency_s"], 60.0)
        # Camera never had an episode, so cam_onset - eeg_onset is not computable.
        self.assertIsNone(summary["eeg_lead_s"])


if __name__ == "__main__":
    unittest.main()
