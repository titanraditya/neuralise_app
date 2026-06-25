"""Pure post-hoc statistics over one recordings/<session_id>/ folder.

No live state, no Qt, no hardware — just camera.csv + eeg.csv + meta.json in, a dict out.
Per the task spec: invalid rows (face_detected=False / contact_ok=False) and the first
`warmup_seconds` of session time are discarded before anything else is computed, then drowsy
episodes are detected with a hysteresis debounce (onset needs >= N seconds above threshold to
confirm, offset needs >= M seconds back below to confirm) — separately for camera (signal =
PERCLOS) and EEG (signal = ratio_norm), plus an OR-rule fusion of the two.

Thresholds are reused from the already-tuned live detectors (camera/perclos.py,
core/eeg_drowsiness.py), not retuned here.
"""

import bisect
import csv
import json
from pathlib import Path

from camera.perclos import DROWSY_THRESHOLD as PERCLOS_DROWSY_THRESHOLD
from core.eeg_drowsiness import CALIBRATION_SECONDS as EEG_CALIBRATION_SECONDS
from core.eeg_drowsiness import DROWSY_RATIO_MULTIPLIER as EEG_DROWSY_RATIO_THRESHOLD

WARMUP_SECONDS = 30.0
HYSTERESIS_ON_SECONDS = 3.0
HYSTERESIS_OFF_SECONDS = 5.0

Sample = tuple[float, float]  # (t_rel, value)


def summarize_session(
    session_dir: str | Path,
    *,
    warmup_seconds: float = WARMUP_SECONDS,
    hysteresis_on_seconds: float = HYSTERESIS_ON_SECONDS,
    hysteresis_off_seconds: float = HYSTERESIS_OFF_SECONDS,
    perclos_threshold: float = PERCLOS_DROWSY_THRESHOLD,
    eeg_ratio_threshold: float = EEG_DROWSY_RATIO_THRESHOLD,
    eeg_calibration_seconds: float = EEG_CALIBRATION_SECONDS,
) -> dict:
    session_dir = Path(session_dir)
    meta = json.loads((session_dir / "meta.json").read_text())

    cam_rows = _read_csv(session_dir / "camera.csv")
    eeg_rows = _read_csv(session_dir / "eeg.csv")

    cam_raw = _camera_samples(cam_rows)
    eeg_raw = _eeg_samples(eeg_rows)

    cam_series = _filter_valid(cam_raw, warmup_seconds)
    eeg_series, eeg_baseline = _eeg_ratio_norm(eeg_raw, warmup_seconds, eeg_calibration_seconds)

    cam_stats, cam_episodes = _series_stats(
        cam_series, perclos_threshold, hysteresis_on_seconds, hysteresis_off_seconds, "camera"
    )
    eeg_stats, eeg_episodes = _series_stats(
        eeg_series, eeg_ratio_threshold, hysteresis_on_seconds, hysteresis_off_seconds, "eeg"
    )
    eeg_stats["baseline"] = eeg_baseline

    # Fusion OR-rule: forward-fill each modality's own above/below-threshold state onto the
    # union of both timelines, then run the same hysteresis detector over the boolean result.
    # A boolean signal has no meaningful peak/trend, so those two fields don't apply here.
    cam_above = [(t, 1.0 if v > perclos_threshold else 0.0) for t, v in cam_series]
    eeg_above = [(t, 1.0 if v > eeg_ratio_threshold else 0.0) for t, v in eeg_series]
    fused_series = _forward_fill_or(cam_above, eeg_above)
    fusion_stats, fusion_episodes = _series_stats(
        fused_series, 0.5, hysteresis_on_seconds, hysteresis_off_seconds, "fusion"
    )
    fusion_stats.pop("peak", None)
    fusion_stats.pop("trend", None)

    cam_onset = cam_stats["onset_latency_s"]
    eeg_onset = eeg_stats["onset_latency_s"]
    eeg_lead_s = (cam_onset - eeg_onset) if (cam_onset is not None and eeg_onset is not None) else None

    pct_face_valid = _pct_true([_to_bool(r.get("face_detected", "true")) for r in cam_rows])
    pct_contact_ok = _pct_true([_to_bool(r.get("contact_ok", "true")) for r in eeg_rows])

    has_camera = bool(meta.get("has_camera"))
    has_eeg = bool(meta.get("has_eeg"))
    valid_session = (has_camera or has_eeg) and not (has_camera and not cam_series) and not (
        has_eeg and not eeg_series
    )

    all_episodes = sorted(cam_episodes + eeg_episodes + fusion_episodes, key=lambda e: e["start_s"])

    return {
        "session_id": meta.get("session_id", session_dir.name),
        "subject_code": meta.get("subject_code", ""),
        "noise_condition": meta.get("noise_condition", ""),
        "started_at": meta.get("started_at"),
        "ended_at": meta.get("ended_at"),
        "camera": cam_stats,
        "eeg": eeg_stats,
        "fusion": fusion_stats,
        "eeg_lead_s": eeg_lead_s,
        "episodes": all_episodes,
        # The exact (valid, post-warmup) series already computed above — exposed as-is for
        # plotting (e.g. tools/report.py) so callers never need to recompute filtering or the
        # EEG ratio_norm baseline themselves.
        "series": {"camera": cam_series, "eeg": eeg_series},
        "quality": {
            "pct_face_valid": pct_face_valid,
            "pct_contact_ok": pct_contact_ok,
            "valid_session": valid_session,
        },
        "params": {
            "warmup_seconds": warmup_seconds,
            "hysteresis_on_seconds": hysteresis_on_seconds,
            "hysteresis_off_seconds": hysteresis_off_seconds,
            "perclos_threshold": perclos_threshold,
            "eeg_ratio_threshold": eeg_ratio_threshold,
            "eeg_calibration_seconds": eeg_calibration_seconds,
        },
    }


# ----------------------------------------------------------------------
# CSV reading
# ----------------------------------------------------------------------

def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def _camera_samples(rows: list[dict]) -> list[tuple[float, float, bool]]:
    """(t_rel, perclos, face_detected) for every row that has both numeric columns."""
    out = []
    for row in rows:
        try:
            t_rel = float(row["t_rel"])
            perclos = float(row["perclos"])
        except (KeyError, ValueError):
            continue
        out.append((t_rel, perclos, _to_bool(row.get("face_detected", "true"))))
    return out


def _eeg_samples(rows: list[dict]) -> list[tuple[float, float, bool]]:
    """(t_rel, ratio, contact_ok) for every row that has both numeric columns."""
    out = []
    for row in rows:
        try:
            t_rel = float(row["t_rel"])
            ratio = float(row["ratio_theta_alpha_beta"])
        except (KeyError, ValueError):
            continue
        out.append((t_rel, ratio, _to_bool(row.get("contact_ok", "true"))))
    return out


# ----------------------------------------------------------------------
# Pre-processing: discard invalid rows + warm-up, before any other computation
# ----------------------------------------------------------------------

def _filter_valid(samples: list[tuple[float, float, bool]], warmup_seconds: float) -> list[Sample]:
    return [(t, v) for t, v, ok in samples if ok and t >= warmup_seconds]


def _eeg_ratio_norm(
    eeg_raw: list[tuple[float, float, bool]], warmup_seconds: float, calibration_seconds: float
) -> tuple[list[Sample], float | None]:
    """ratio_norm = ratio / baseline, baseline = mean ratio over the first `calibration_seconds`
    of valid, post-warmup data.

    Mirrors core.eeg_drowsiness.EEGDrowsinessDetector's calibration formula and window length,
    but anchored to recorded t_rel rather than wall-clock time — this recomputes the baseline
    offline from an already-captured session, not live, so it can't reuse that class directly.
    """
    series = _filter_valid(eeg_raw, warmup_seconds)
    if not series:
        return [], None

    t0 = series[0][0]
    calib_values = [v for t, v in series if t - t0 < calibration_seconds]
    if not calib_values:
        return [], None

    baseline = sum(calib_values) / len(calib_values)
    if baseline <= 1e-9:
        return [], None

    return [(t, v / baseline) for t, v in series], baseline


# ----------------------------------------------------------------------
# Episode detection (hysteresis debounce) + per-modality stats
# ----------------------------------------------------------------------

def _detect_episodes(
    series: list[Sample], threshold: float, on_seconds: float, off_seconds: float
) -> list[dict]:
    """A candidate onset must hold above `threshold` for >= on_seconds before it's confirmed
    (back-dated to when the streak actually started); a confirmed episode only ends once the
    signal has been back below threshold for >= off_seconds (also back-dated). Brief dips
    shorter than off_seconds don't split an episode in two."""
    episodes: list[dict] = []
    drowsy = False
    onset_t: float | None = None
    peak: float | None = None
    candidate_on: float | None = None
    candidate_on_peak: float | None = None
    candidate_off: float | None = None

    for t, v in series:
        above = v > threshold
        if not drowsy:
            if above:
                if candidate_on is None:
                    candidate_on = t
                    candidate_on_peak = v
                else:
                    candidate_on_peak = max(candidate_on_peak, v)
                if t - candidate_on >= on_seconds:
                    drowsy = True
                    onset_t = candidate_on
                    peak = candidate_on_peak
                    candidate_off = None
            else:
                candidate_on = None
                candidate_on_peak = None
        else:
            peak = v if peak is None else max(peak, v)
            if above:
                candidate_off = None
            else:
                if candidate_off is None:
                    candidate_off = t
                if t - candidate_off >= off_seconds:
                    episodes.append({"start_s": onset_t, "duration_s": candidate_off - onset_t, "peak": peak})
                    drowsy = False
                    onset_t = None
                    peak = None
                    candidate_on = None
                    candidate_on_peak = None
                    candidate_off = None

    if drowsy and onset_t is not None:
        last_t = series[-1][0]
        episodes.append({"start_s": onset_t, "duration_s": last_t - onset_t, "peak": peak})

    return episodes


def _trend_thirds(series: list[Sample]) -> list[float | None]:
    """Average signal value in each third (by time span, not sample count) of the series."""
    if not series:
        return [None, None, None]

    t0, t1 = series[0][0], series[-1][0]
    span = t1 - t0
    if span <= 0:
        avg = sum(v for _, v in series) / len(series)
        return [avg, avg, avg]

    edges = [t0, t0 + span / 3, t0 + 2 * span / 3, t1 + 1e-9]
    buckets: list[list[float]] = [[], [], []]
    for t, v in series:
        for i in range(3):
            if edges[i] <= t < edges[i + 1]:
                buckets[i].append(v)
                break
    return [sum(b) / len(b) if b else None for b in buckets]


def _series_stats(
    series: list[Sample], threshold: float, on_seconds: float, off_seconds: float, modality: str
) -> tuple[dict, list[dict]]:
    episodes = _detect_episodes(series, threshold, on_seconds, off_seconds)
    durations = [e["duration_s"] for e in episodes]
    # Approximation: treats the filtered (valid, post-warmup) series as one continuous span —
    # good enough for a research summary, doesn't subtract small excluded-invalid gaps inside it.
    valid_duration = (series[-1][0] - series[0][0]) if len(series) >= 2 else 0.0
    total_drowsy = sum(durations)

    stats = {
        "onset_latency_s": episodes[0]["start_s"] if episodes else None,
        "episode_count": len(episodes),
        "total_drowsy_s": total_drowsy,
        "pct_drowsy": (100.0 * total_drowsy / valid_duration) if valid_duration > 0 else None,
        "longest_episode_s": max(durations) if durations else None,
        "mean_episode_duration_s": (sum(durations) / len(durations)) if durations else None,
        "peak": max((v for _, v in series), default=None),
        "trend": _trend_thirds(series),
    }
    episode_list = [
        {"start_s": e["start_s"], "duration_s": e["duration_s"], "modality": modality, "peak": e["peak"]}
        for e in episodes
    ]
    return stats, episode_list


def _forward_fill_or(series_a: list[Sample], series_b: list[Sample]) -> list[Sample]:
    """Union both timelines; at each timestamp, OR the most recently known state (forward-
    filled) of each modality. A modality that hasn't reported yet at a given time contributes
    False, not an unknown state — the OR-rule only needs one side to say 'drowsy'."""
    times_a = [t for t, _ in series_a]
    times_b = [t for t, _ in series_b]
    times = sorted({*times_a, *times_b})

    out = []
    for t in times:
        ia = bisect.bisect_right(times_a, t) - 1
        ib = bisect.bisect_right(times_b, t) - 1
        val_a = series_a[ia][1] if ia >= 0 else 0.0
        val_b = series_b[ib][1] if ib >= 0 else 0.0
        out.append((t, 1.0 if (val_a > 0.5 or val_b > 0.5) else 0.0))
    return out


def _pct_true(flags: list[bool]) -> float | None:
    if not flags:
        return None
    return 100.0 * sum(flags) / len(flags)
