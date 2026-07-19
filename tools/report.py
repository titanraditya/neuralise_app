"""CLI: render recordings/<session_id>/report.pdf from a session folder.

Usage:
    python -m tools.report <session_dir>

Pure batch process — no Qt import anywhere in this module. It must be runnable as a plain
subprocess so the GUI can spawn it without blocking the UI thread (PDF/plot rendering is too
heavy to run inline — see ui/main_window.py's `_on_selesai`).

All drowsiness analysis (warm-up/invalid-segment filtering, ratio_norm baseline, hysteresis
episode detection) lives in core/aggregate.py — this module only reads summarize_session()'s
result and renders it; it never recomputes any of that math.
"""

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — no display, no Qt backend
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.aggregate import summarize_session

MODALITY_COLORS = {
    "camera": "#2563eb",
    "eeg": "#d97706",
    "fusion": "#dc2626",
    "eog": "#7c3aed",
    "museeog": "#0f766e",
}
MODALITY_LABELS = {
    "camera": "Kamera",
    "eeg": "EEG",
    "fusion": "Gabungan",
    "eog": "EOG (BITalino)",
    "museeog": "EOG (Muse)",
}
# PERCLOS-family modalities share the left plot axis: all three are a 0–1 "fraction of time
# eyes closed" with the same 0.15 drowsy threshold. EEG (ratio vs baseline) gets its own axis.
PERCLOS_FAMILY = ("camera", "eog", "museeog")
MAX_EPISODE_ROWS = 8
SEVERITY_BUCKETS = [(10.0, "Rendah", "#1f9d55"), (30.0, "Sedang", "#d97706"), (None, "Tinggi", "#dc2626")]

PAGE_SIZE = A4
MARGIN = 14 * mm
PLOT_FIGSIZE = (9.6, 3.4)  # inches
PLOT_DPI = 300


def render_session_report(session_dir: str | Path) -> Path:
    """Build recordings/<session_id>/report.pdf from scratch. Returns the PDF's path."""
    session_dir = Path(session_dir)
    summary = summarize_session(session_dir)
    out_path = session_dir / "report.pdf"

    with tempfile.TemporaryDirectory() as tmp_dir:
        png_path = Path(tmp_dir) / "timeline.png"
        _render_timeline_png(summary, png_path)
        _build_pdf(summary, png_path, out_path)

    return out_path


# ----------------------------------------------------------------------
# Plot (matplotlib)
# ----------------------------------------------------------------------

def _render_timeline_png(summary: dict, out_path: Path) -> None:
    """Only the session's own modalities are drawn (summary['modalities']): PERCLOS-family
    series share the left axis; the EEG-ratio axis only exists when EEG was part of the
    session (as the sole axis when nothing PERCLOS-shaped was recorded)."""
    modalities = summary["modalities"]
    params = summary["params"]
    perclos_keys = [m for m in PERCLOS_FAMILY if modalities.get(m)]
    has_eeg = bool(modalities.get("eeg"))

    plot_labels = {
        "camera": "PERCLOS (Kamera)",
        "eog": "PERCLOS EOG (BITalino)",
        "museeog": "PERCLOS EOG (Muse)",
        "eeg": "Rasio EEG",
    }

    fig, ax_left = plt.subplots(figsize=PLOT_FIGSIZE)
    if perclos_keys and has_eeg:
        ax_perclos, ax_eeg = ax_left, ax_left.twinx()
    elif has_eeg:
        ax_perclos, ax_eeg = None, ax_left
    else:
        ax_perclos, ax_eeg = ax_left, None

    plotted_any = False
    if ax_perclos is not None:
        for key in perclos_keys:
            series = summary["series"][key]
            if series:
                t, v = zip(*series)
                ax_perclos.plot(t, v, color=MODALITY_COLORS[key], linewidth=1.2,
                                label=plot_labels[key])
                plotted_any = True
        ax_perclos.axhline(params["perclos_threshold"], color="#6b7585", linestyle="--",
                           linewidth=0.8, alpha=0.6)
        ax_perclos.set_ylabel("PERCLOS (proporsi mata tertutup)", color="#333333")
        ax_perclos.set_ylim(bottom=0)
    if ax_eeg is not None:
        eeg_series = summary["series"]["eeg"]
        if eeg_series:
            t, v = zip(*eeg_series)
            ax_eeg.plot(t, v, color=MODALITY_COLORS["eeg"], linewidth=1.2, label=plot_labels["eeg"])
            plotted_any = True
        ax_eeg.axhline(params["eeg_ratio_threshold"], color=MODALITY_COLORS["eeg"], linestyle="--",
                       linewidth=0.8, alpha=0.6)
        ax_eeg.set_ylabel("Rasio EEG (vs awal sesi)", color=MODALITY_COLORS["eeg"])
        ax_eeg.tick_params(axis="y", labelcolor=MODALITY_COLORS["eeg"])
        ax_eeg.set_ylim(bottom=0)

    if not plotted_any:
        ax_left.text(0.5, 0.5, "Tidak ada data valid untuk ditampilkan", ha="center", va="center",
                     transform=ax_left.transAxes, color="#888888")

    for ep in _display_episodes(summary):
        ax_left.axvspan(ep["start_s"], ep["start_s"] + ep["duration_s"],
                        color=MODALITY_COLORS[ep["modality"]], alpha=0.12, linewidth=0)

    ax_left.set_xlabel("Waktu sejak sesi dimulai (detik)")

    handles, labels = ax_left.get_legend_handles_labels()
    if ax_eeg is not None and ax_eeg is not ax_left:
        h, l = ax_eeg.get_legend_handles_labels()
        handles, labels = handles + h, labels + l
    if handles:
        ax_left.legend(handles, labels, loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=PLOT_DPI)
    plt.close(fig)


# ----------------------------------------------------------------------
# PDF (reportlab)
# ----------------------------------------------------------------------

def _build_pdf(summary: dict, png_path: Path, out_path: Path) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=16, leading=19, spaceAfter=2)
    subhead_style = ParagraphStyle("subhead", parent=styles["Normal"], fontSize=9,
                                    textColor=colors.HexColor("#555555"))
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=8.5, leading=12)
    caption_style = ParagraphStyle("caption", parent=styles["Normal"], fontSize=7.5, leading=9.5,
                                    textColor=colors.HexColor("#6b7585"))
    tile_label_style = ParagraphStyle("tile_label", parent=styles["Normal"], fontSize=8,
                                       textColor=colors.HexColor("#6b7585"), alignment=1)
    tile_value_style = ParagraphStyle("tile_value", parent=styles["Normal"], fontSize=16, leading=19,
                                       alignment=1, fontName="Helvetica-Bold")

    content_width = PAGE_SIZE[0] - 2 * MARGIN
    doc = SimpleDocTemplate(
        str(out_path), pagesize=PAGE_SIZE,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Laporan Sesi {summary['session_id']}",
    )

    elements = [
        Paragraph(f"Laporan Sesi Drowsiness — {summary['session_id']}", title_style),
        Paragraph(_header_line(summary), subhead_style),
        Spacer(1, 5),
        Paragraph(_quality_line(summary), body_style),
        Spacer(1, 10),
        Paragraph(_summary_heading(summary), body_style),
        Spacer(1, 4),
        _tiles_table(summary, content_width, tile_label_style, tile_value_style),
        Spacer(1, 10),
        Image(str(png_path), width=content_width, height=content_width * (PLOT_FIGSIZE[1] / PLOT_FIGSIZE[0])),
        Spacer(1, 8),
        _episode_and_severity_row(summary, content_width, body_style, caption_style),
        Spacer(1, 10),
        Paragraph(_params_line(summary), caption_style),
        Spacer(1, 3),
        Paragraph(f"<i>{_notes_line(summary)}</i>", caption_style),
    ]

    doc.build(elements)


# ----------------------------------------------------------------------
# Modality selection — the report only shows the modalities this session recorded
# (summary["modalities"], from meta.json's has_* flags / recorded data).
# ----------------------------------------------------------------------

def _active_modalities(summary: dict) -> list[str]:
    return [m for m in ("camera", "eeg", "eog", "museeog") if summary["modalities"].get(m)]


def _has_fusion(summary: dict) -> bool:
    """The OR-rule fusion only means something when both of its inputs were recorded — EOG is
    never part of it (mirrors the live status panel)."""
    modalities = summary["modalities"]
    return bool(modalities.get("camera")) and bool(modalities.get("eeg"))


def _display_episodes(summary: dict) -> list[dict]:
    """Without fusion, its episodes would just duplicate the single source modality's rows."""
    episodes = summary["episodes"]
    if _has_fusion(summary):
        return episodes
    return [ep for ep in episodes if ep["modality"] != "fusion"]


def _primary_stats(summary: dict) -> tuple[str, dict]:
    """(modality_key, stats) the headline tiles + severity label are computed from: the
    camera+EEG fusion when both were recorded, otherwise the session's single main modality."""
    if _has_fusion(summary):
        return "fusion", summary["fusion"]
    for key in ("camera", "eeg", "eog", "museeog"):
        if summary["modalities"].get(key):
            return key, summary[key]
    return "fusion", summary["fusion"]  # no modality at all — all-NA tiles


def _summary_heading(summary: dict) -> str:
    if _has_fusion(summary):
        return (
            "<b>Ringkasan deteksi kantuk</b> — gabungan kamera &amp; EEG "
            "(kantuk tercatat begitu salah satu dari keduanya mendeteksi kantuk):"
        )
    key, _ = _primary_stats(summary)
    return f"<b>Ringkasan deteksi kantuk</b> — berdasarkan {MODALITY_LABELS[key]}:"


def _header_line(summary: dict) -> str:
    duration = _format_duration(summary["started_at"], summary["ended_at"])
    date_str = (summary["started_at"] or "")[:10] or "-"
    modality_names = ", ".join(MODALITY_LABELS[m] for m in _active_modalities(summary)) or "-"
    return (
        f"Nama: <b>{summary['subject_code'] or '-'}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Kebisingan: <b>{summary['noise_condition'] or '-'}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Durasi: <b>{duration}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Tanggal: <b>{date_str}</b>"
        f"<br/>Modalitas sesi: <b>{modality_names}</b>"
    )


def _quality_line(summary: dict) -> str:
    quality = summary["quality"]
    modalities = summary["modalities"]
    parts = []
    if modalities.get("camera"):
        parts.append(f"wajah terdeteksi: <b>{_fmt_pct(quality['pct_face_valid'])}</b>")
    if modalities.get("eeg"):
        parts.append(f"kontak EEG baik: <b>{_fmt_pct(quality['pct_contact_ok'])}</b>")
    if modalities.get("eog"):
        parts.append(f"kontak EOG (BITalino) baik: <b>{_fmt_pct(quality['pct_eog_contact_ok'])}</b>")
    if modalities.get("museeog"):
        parts.append(f"kontak EOG (Muse) baik: <b>{_fmt_pct(quality['pct_museeog_contact_ok'])}</b>")
    parts.append(f"sesi valid: <b>{'Ya' if quality['valid_session'] else 'Tidak'}</b>")
    return "Kualitas data — " + " &nbsp;|&nbsp; ".join(parts)


def _tiles_table(summary: dict, content_width: float, label_style, value_style) -> Table:
    key, stats = _primary_stats(summary)
    tiles = [
        ("Waktu Kantuk Pertama", _fmt_seconds(stats["onset_latency_s"])),
        ("% Waktu Kantuk", _fmt_pct(stats["pct_drowsy"])),
        ("Jumlah Episode Kantuk", str(stats["episode_count"])),
        ("Episode Kantuk Terlama", _fmt_seconds(stats["longest_episode_s"])),
    ]
    if key == "fusion":
        tiles.append(("Selisih EEG vs Kamera", _fmt_seconds(summary["eeg_lead_s"])))
    else:
        peak = stats.get("peak")
        tiles.append(("Nilai Puncak", f"{peak:.2f}" if peak is not None else "NA"))
    data = [
        [Paragraph(value, value_style) for _, value in tiles],
        [Paragraph(label, label_style) for label, _ in tiles],
    ]
    table = Table(data, colWidths=[content_width / len(tiles)] * len(tiles))
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _episode_and_severity_row(summary: dict, content_width: float, body_style, caption_style) -> Table:
    episodes = _display_episodes(summary)
    shown = episodes[:MAX_EPISODE_ROWS]
    remaining = len(episodes) - len(shown)

    rows = [["No", "Mulai (detik)", "Durasi (detik)", "Sumber", "Nilai Puncak"]]
    for i, ep in enumerate(shown, start=1):
        rows.append([
            str(i),
            f"{ep['start_s']:.1f}",
            f"{ep['duration_s']:.1f}",
            MODALITY_LABELS.get(ep["modality"], ep["modality"]),
            f"{ep['peak']:.2f}" if ep["peak"] is not None else "-",
        ])
    if not shown:
        rows.append(["-", "-", "-", "Tidak ada episode", "-"])

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f6")),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]
    if remaining > 0:
        rows.append([f"+{remaining} episode lainnya tidak ditampilkan", "", "", "", ""])
        last = len(rows) - 1
        style.append(("SPAN", (0, last), (-1, last)))
        style.append(("FONTSIZE", (0, last), (-1, last), 7))
        style.append(("TEXTCOLOR", (0, last), (-1, last), colors.HexColor("#6b7585")))

    ep_width = content_width * 0.56
    ep_table = Table(rows, colWidths=[ep_width * w for w in (0.12, 0.22, 0.22, 0.28, 0.16)])
    ep_table.setStyle(TableStyle(style))

    severity_panel = _severity_trend_panel(summary, body_style, caption_style)

    row = Table([[ep_table, severity_panel]], colWidths=[ep_width, content_width - ep_width])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, 0), 10)]))
    return row


def _severity_trend_panel(summary: dict, body_style, caption_style) -> list:
    """A plain list of flowables — Table cells stack these directly (see _listCellGeom in
    reportlab's tables.py). KeepTogether would look like a drop-in alternative here but its
    wrap() deliberately returns a giant sentinel height to force a page split when used as a
    top-level flowable, which blows up Table's real cell-height calculation."""
    modalities = summary["modalities"]
    primary_key, primary = _primary_stats(summary)
    severity_source = "gabungan" if primary_key == "fusion" else MODALITY_LABELS[primary_key]
    label, hex_color = _severity_label(primary["pct_drowsy"])

    flowables = [
        Paragraph(
            f"<b>Tingkat Keparahan Kantuk ({severity_source}):</b> "
            f"<font color='{hex_color}'><b>{label}</b></font>",
            body_style,
        ),
        Spacer(1, 4),
    ]
    if modalities.get("camera"):
        cam_trend = _fmt_trend(summary["camera"]["trend"], "{:.3f}")
        flowables.append(Paragraph(
            f"Tren PERCLOS Kamera — persentase mata tertutup (awal → tengah → akhir): {cam_trend}",
            body_style,
        ))
    if modalities.get("eeg"):
        eeg_trend = _fmt_trend(summary["eeg"]["trend"], "{:.2f}")
        flowables.append(Paragraph(
            f"Tren Rasio EEG — kenaikan band power vs awal sesi (awal → tengah → akhir): {eeg_trend}",
            body_style,
        ))
    for key in ("eog", "museeog"):
        if not modalities.get(key):
            continue
        stats = summary[key]
        trend = _fmt_trend(stats["trend"], "{:.3f}")
        blink = stats.get("mean_blink_rate")
        blink_str = f"{blink:.1f}/menit" if blink is not None else "NA"
        flowables.append(Paragraph(
            f"Tren PERCLOS {MODALITY_LABELS[key]} (awal → tengah → akhir): {trend} "
            f"— rata-rata blink rate: {blink_str}",
            body_style,
        ))
    flowables += [
        Spacer(1, 4),
        Paragraph(
            f"Tingkat keparahan ini hanya label deskriptif berdasarkan % waktu kantuk "
            f"({severity_source}) untuk penilaian cepat, bukan skor diagnosis klinis.",
            caption_style,
        ),
    ]
    return flowables


def _params_line(summary: dict) -> str:
    params = summary["params"]
    modalities = summary["modalities"]
    parts = []
    if modalities.get("camera"):
        parts.append(f"ambang PERCLOS kamera={params['perclos_threshold']:.2f}")
    if modalities.get("eeg"):
        parts.append(f"ambang rasio EEG={params['eeg_ratio_threshold']:.2f}×baseline")
    if modalities.get("eog") or modalities.get("museeog"):
        parts.append(f"ambang PERCLOS EOG={params['eog_perclos_threshold']:.2f}")
    parts.append(
        f"histeresis aktif/nonaktif={params['hysteresis_on_seconds']:.0f}s/{params['hysteresis_off_seconds']:.0f}s"
    )
    parts.append(f"pemanasan awal={params['warmup_seconds']:.0f}s")
    if modalities.get("eeg"):
        parts.append(f"kalibrasi EEG={params['eeg_calibration_seconds']:.0f}s")
    return "Parameter: " + ", ".join(parts) + "."


def _notes_line(summary: dict) -> str:
    modalities = summary["modalities"]
    sentences = []
    if _has_fusion(summary):
        sentences.append(
            "Catatan: \"Gabungan\" berarti hasil kombinasi kamera + EEG, bukan alat ukur "
            "tersendiri. \"Selisih EEG vs Kamera\" bernilai positif jika EEG mendeteksi kantuk "
            "lebih dulu daripada kamera, dan negatif jika kamera lebih dulu."
        )
    else:
        sentences.append("Catatan:")
    if modalities.get("eog") or modalities.get("museeog"):
        sentences.append(
            "EOG dianalisis sebagai modalitas mandiri — tidak ikut digabung ke deteksi "
            "gabungan kamera + EEG."
        )
    sentences.append(
        "Nilai puncak pada tabel episode memakai satuan PERCLOS untuk episode dari "
        "Kamera/EOG dan rasio EEG untuk episode dari EEG. Ambang deteksi di atas belum "
        "tervalidasi secara klinis; \"waktu kantuk pertama\" adalah saat sistem ini pertama "
        "kali mendeteksi tanda kantuk, bukan diagnosis onset tidur secara medis. Semua angka "
        "dihitung hanya dari segmen data yang valid (wajah terdeteksi / kontak sensor baik), "
        "di luar masa pemanasan awal sistem."
    )
    return " ".join(sentences)


def _severity_label(pct_drowsy: float | None) -> tuple[str, str]:
    if pct_drowsy is None:
        return "NA", "#6b7585"
    for cutoff, label, hex_color in SEVERITY_BUCKETS:
        if cutoff is None or pct_drowsy < cutoff:
            return label, hex_color
    return "Tinggi", "#dc2626"


def _fmt_trend(trend: list[float | None], fmt: str) -> str:
    return " → ".join(fmt.format(v) if v is not None else "NA" for v in trend)


def _fmt_pct(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1f}%"


def _fmt_seconds(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1f} s"


def _format_duration(started_at: str | None, ended_at: str | None) -> str:
    if not started_at or not ended_at:
        return "NA"
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except ValueError:
        return "NA"
    total_seconds = max(int((end - start).total_seconds()), 0)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir")
    args = parser.parse_args()

    out_path = render_session_report(args.session_dir)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
