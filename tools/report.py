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

MODALITY_COLORS = {"camera": "#2563eb", "eeg": "#d97706", "fusion": "#dc2626"}
MODALITY_LABELS = {"camera": "Kamera", "eeg": "EEG", "fusion": "Gabungan"}
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
    cam_series = summary["series"]["camera"]
    eeg_series = summary["series"]["eeg"]
    params = summary["params"]

    fig, ax_cam = plt.subplots(figsize=PLOT_FIGSIZE)
    ax_eeg = ax_cam.twinx()

    if cam_series:
        t, v = zip(*cam_series)
        ax_cam.plot(t, v, color=MODALITY_COLORS["camera"], linewidth=1.2, label="PERCLOS (Kamera)")
    if eeg_series:
        t, v = zip(*eeg_series)
        ax_eeg.plot(t, v, color=MODALITY_COLORS["eeg"], linewidth=1.2, label="Rasio EEG")

    if not cam_series and not eeg_series:
        ax_cam.text(0.5, 0.5, "Tidak ada data valid untuk ditampilkan", ha="center", va="center",
                    transform=ax_cam.transAxes, color="#888888")

    ax_cam.axhline(params["perclos_threshold"], color=MODALITY_COLORS["camera"], linestyle="--",
                   linewidth=0.8, alpha=0.6)
    ax_eeg.axhline(params["eeg_ratio_threshold"], color=MODALITY_COLORS["eeg"], linestyle="--",
                   linewidth=0.8, alpha=0.6)

    for ep in summary["episodes"]:
        ax_cam.axvspan(ep["start_s"], ep["start_s"] + ep["duration_s"],
                       color=MODALITY_COLORS[ep["modality"]], alpha=0.12, linewidth=0)

    ax_cam.set_xlabel("Waktu sejak sesi dimulai (detik)")
    ax_cam.set_ylabel("PERCLOS (% mata tertutup)", color=MODALITY_COLORS["camera"])
    ax_eeg.set_ylabel("Rasio EEG (vs awal sesi)", color=MODALITY_COLORS["eeg"])
    ax_cam.tick_params(axis="y", labelcolor=MODALITY_COLORS["camera"])
    ax_eeg.tick_params(axis="y", labelcolor=MODALITY_COLORS["eeg"])
    ax_cam.set_ylim(bottom=0)
    ax_eeg.set_ylim(bottom=0)

    handles_cam, labels_cam = ax_cam.get_legend_handles_labels()
    handles_eeg, labels_eeg = ax_eeg.get_legend_handles_labels()
    if handles_cam or handles_eeg:
        ax_cam.legend(handles_cam + handles_eeg, labels_cam + labels_eeg, loc="upper right", fontsize=8)

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
        Paragraph(_quality_line(summary["quality"]), body_style),
        Spacer(1, 10),
        Paragraph(
            "<b>Ringkasan deteksi kantuk</b> — gabungan kamera &amp; EEG "
            "(kantuk tercatat begitu salah satu dari keduanya mendeteksi kantuk):",
            body_style,
        ),
        Spacer(1, 4),
        _tiles_table(summary, content_width, tile_label_style, tile_value_style),
        Spacer(1, 10),
        Image(str(png_path), width=content_width, height=content_width * (PLOT_FIGSIZE[1] / PLOT_FIGSIZE[0])),
        Spacer(1, 8),
        _episode_and_severity_row(summary, content_width, body_style, caption_style),
        Spacer(1, 10),
        Paragraph(_params_line(summary["params"]), caption_style),
        Spacer(1, 3),
        Paragraph(
            "<i>Catatan: \"Gabungan\" berarti hasil kombinasi kamera + EEG, bukan alat ukur "
            "tersendiri. \"Selisih EEG vs Kamera\" bernilai positif jika EEG mendeteksi kantuk "
            "lebih dulu daripada kamera, dan negatif jika kamera lebih dulu. Nilai puncak pada "
            "tabel episode memakai satuan PERCLOS untuk episode dari Kamera dan rasio EEG untuk "
            "episode dari EEG. Ambang deteksi di atas belum tervalidasi secara klinis; \"waktu "
            "kantuk pertama\" adalah saat sistem ini pertama kali mendeteksi tanda kantuk, bukan "
            "diagnosis onset tidur secara medis. Semua angka dihitung hanya dari segmen data yang "
            "valid (wajah terdeteksi / kontak EEG baik), di luar masa pemanasan awal sistem.</i>",
            caption_style,
        ),
    ]

    doc.build(elements)


def _header_line(summary: dict) -> str:
    duration = _format_duration(summary["started_at"], summary["ended_at"])
    date_str = (summary["started_at"] or "")[:10] or "-"
    return (
        f"Nama: <b>{summary['subject_code'] or '-'}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Kebisingan: <b>{summary['noise_condition'] or '-'}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Durasi: <b>{duration}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Tanggal: <b>{date_str}</b>"
    )


def _quality_line(quality: dict) -> str:
    return (
        f"Kualitas data — wajah terdeteksi: <b>{_fmt_pct(quality['pct_face_valid'])}</b> &nbsp;|&nbsp; "
        f"kontak EEG baik: <b>{_fmt_pct(quality['pct_contact_ok'])}</b> &nbsp;|&nbsp; "
        f"sesi valid: <b>{'Ya' if quality['valid_session'] else 'Tidak'}</b>"
    )


def _tiles_table(summary: dict, content_width: float, label_style, value_style) -> Table:
    fusion = summary["fusion"]
    tiles = [
        ("Waktu Kantuk Pertama", _fmt_seconds(fusion["onset_latency_s"])),
        ("% Waktu Kantuk", _fmt_pct(fusion["pct_drowsy"])),
        ("Jumlah Episode Kantuk", str(fusion["episode_count"])),
        ("Episode Kantuk Terlama", _fmt_seconds(fusion["longest_episode_s"])),
        ("Selisih EEG vs Kamera", _fmt_seconds(summary["eeg_lead_s"])),
    ]
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
    episodes = summary["episodes"]
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
    fusion = summary["fusion"]
    label, hex_color = _severity_label(fusion["pct_drowsy"])
    cam_trend = _fmt_trend(summary["camera"]["trend"], "{:.3f}")
    eeg_trend = _fmt_trend(summary["eeg"]["trend"], "{:.2f}")

    return [
        Paragraph(
            f"<b>Tingkat Keparahan Kantuk (gabungan):</b> "
            f"<font color='{hex_color}'><b>{label}</b></font>",
            body_style,
        ),
        Spacer(1, 4),
        Paragraph(f"Tren PERCLOS — persentase mata tertutup (awal → tengah → akhir): {cam_trend}", body_style),
        Paragraph(
            f"Tren Rasio EEG — kenaikan band power vs awal sesi (awal → tengah → akhir): {eeg_trend}",
            body_style,
        ),
        Spacer(1, 4),
        Paragraph(
            "Tingkat keparahan ini hanya label deskriptif berdasarkan % waktu kantuk (gabungan "
            "kamera + EEG) untuk penilaian cepat, bukan skor diagnosis klinis.",
            caption_style,
        ),
    ]


def _params_line(params: dict) -> str:
    return (
        f"Parameter: ambang PERCLOS={params['perclos_threshold']:.2f}, "
        f"ambang rasio EEG={params['eeg_ratio_threshold']:.2f}×baseline, "
        f"histeresis aktif/nonaktif={params['hysteresis_on_seconds']:.0f}s/{params['hysteresis_off_seconds']:.0f}s, "
        f"pemanasan awal={params['warmup_seconds']:.0f}s, kalibrasi EEG={params['eeg_calibration_seconds']:.0f}s."
    )


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
