"""CLI: summarize every recordings/<session_id>/ folder into one row of recordings/_summary.csv.

Usage:
    python -m tools.build_report_csv [recordings_dir]

All the actual math lives in core/aggregate.py — this just loops, flattens, and writes CSV.
"""

import argparse
import csv
import sys
from pathlib import Path

from core.aggregate import summarize_session
from core.session import RECORDINGS_DIR, Session

FIELDNAMES = [
    "session_id", "subject_code", "noise_condition", "started_at", "ended_at",
    "cam_onset_latency_s", "cam_episode_count", "cam_total_drowsy_s", "cam_pct_drowsy",
    "cam_longest_episode_s", "cam_mean_episode_duration_s", "cam_perclos_peak",
    "cam_trend_first", "cam_trend_mid", "cam_trend_last",
    "eeg_onset_latency_s", "eeg_episode_count", "eeg_total_drowsy_s", "eeg_pct_drowsy",
    "eeg_longest_episode_s", "eeg_mean_episode_duration_s", "eeg_ratio_norm_peak", "eeg_baseline",
    "eeg_trend_first", "eeg_trend_mid", "eeg_trend_last",
    "fusion_onset_latency_s", "fusion_episode_count", "fusion_total_drowsy_s", "fusion_pct_drowsy",
    "fusion_longest_episode_s", "fusion_mean_episode_duration_s",
    "eeg_lead_s",
    "pct_face_valid", "pct_contact_ok", "valid_session",
    "warmup_seconds", "hysteresis_on_seconds", "hysteresis_off_seconds",
    "perclos_threshold", "eeg_ratio_threshold", "eeg_calibration_seconds",
]


def _row_from_summary(summary: dict) -> dict:
    cam, eeg, fusion = summary["camera"], summary["eeg"], summary["fusion"]
    quality, params = summary["quality"], summary["params"]
    cam_trend = cam["trend"]
    eeg_trend = eeg["trend"]
    return {
        "session_id": summary["session_id"],
        "subject_code": summary["subject_code"],
        "noise_condition": summary["noise_condition"],
        "started_at": summary["started_at"],
        "ended_at": summary["ended_at"],
        "cam_onset_latency_s": cam["onset_latency_s"],
        "cam_episode_count": cam["episode_count"],
        "cam_total_drowsy_s": cam["total_drowsy_s"],
        "cam_pct_drowsy": cam["pct_drowsy"],
        "cam_longest_episode_s": cam["longest_episode_s"],
        "cam_mean_episode_duration_s": cam["mean_episode_duration_s"],
        "cam_perclos_peak": cam["peak"],
        "cam_trend_first": cam_trend[0],
        "cam_trend_mid": cam_trend[1],
        "cam_trend_last": cam_trend[2],
        "eeg_onset_latency_s": eeg["onset_latency_s"],
        "eeg_episode_count": eeg["episode_count"],
        "eeg_total_drowsy_s": eeg["total_drowsy_s"],
        "eeg_pct_drowsy": eeg["pct_drowsy"],
        "eeg_longest_episode_s": eeg["longest_episode_s"],
        "eeg_mean_episode_duration_s": eeg["mean_episode_duration_s"],
        "eeg_ratio_norm_peak": eeg["peak"],
        "eeg_baseline": eeg["baseline"],
        "eeg_trend_first": eeg_trend[0],
        "eeg_trend_mid": eeg_trend[1],
        "eeg_trend_last": eeg_trend[2],
        "fusion_onset_latency_s": fusion["onset_latency_s"],
        "fusion_episode_count": fusion["episode_count"],
        "fusion_total_drowsy_s": fusion["total_drowsy_s"],
        "fusion_pct_drowsy": fusion["pct_drowsy"],
        "fusion_longest_episode_s": fusion["longest_episode_s"],
        "fusion_mean_episode_duration_s": fusion["mean_episode_duration_s"],
        "eeg_lead_s": summary["eeg_lead_s"],
        "pct_face_valid": quality["pct_face_valid"],
        "pct_contact_ok": quality["pct_contact_ok"],
        "valid_session": quality["valid_session"],
        "warmup_seconds": params["warmup_seconds"],
        "hysteresis_on_seconds": params["hysteresis_on_seconds"],
        "hysteresis_off_seconds": params["hysteresis_off_seconds"],
        "perclos_threshold": params["perclos_threshold"],
        "eeg_ratio_threshold": params["eeg_ratio_threshold"],
        "eeg_calibration_seconds": params["eeg_calibration_seconds"],
    }


def build_report_csv(recordings_dir: str | Path = RECORDINGS_DIR) -> Path:
    recordings_dir = Path(recordings_dir)
    out_path = recordings_dir / "_summary.csv"
    rows = []
    for session_dir in Session.list_all(recordings_dir):
        try:
            summary = summarize_session(session_dir)
        except Exception as exc:  # noqa: BLE001 - one bad session shouldn't abort the whole report
            print(f"skipping {session_dir.name}: {exc}", file=sys.stderr)
            continue
        rows.append(_row_from_summary(summary))

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings_dir", nargs="?", default=str(RECORDINGS_DIR))
    args = parser.parse_args()

    out_path = build_report_csv(args.recordings_dir)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
