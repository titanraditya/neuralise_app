"""
Muse S Athena - Panel EEG Realtime (BrainFlow + pyqtgraph)
==========================================================
Fokus: deteksi/monitoring EEG.
  - 4 channel time-series live (TP9, AF7, AF8, TP10)
  - Deteksi kontak otomatis per channel (railing -> "NO CONTACT")
  - Notch 50 Hz (listrik Indonesia) + bandpass 1-40 Hz untuk tampilan
  - Bar band power live: Delta / Theta / Alpha / Beta / Gamma

Dependencies:
  pip install pyqtgraph pyqt5 scipy
  (brainflow sudah terpasang)

Jalankan:
  python muse_eeg_panel.py
"""

import numpy as np
from scipy.signal import butter, sosfiltfilt, iirnotch, filtfilt
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowPresets
from brainflow.data_filter import DataFilter

pg.setConfigOptions(antialias=True)   # garis lebih halus

# ---------------- Config ----------------
SERIAL      = "MuseS-DA8F"     # nama device kamu; kosongkan ("") untuk auto-discover
SRATE       = 256
WINDOW_SEC  = 5
WINDOW      = WINDOW_SEC * SRATE
NOTCH_HZ    = 50.0             # listrik Indonesia = 50 Hz (ganti 60.0 kalau perlu)
CH_NAMES    = ["TP9", "AF7", "AF8", "TP10"]
CH_COLORS   = ['#00d1b2', '#3273dc', '#ffdd57', '#ff3860']
BANDS       = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']

# ---------------- Filter tampilan (display only) ----------------
_sos_bp   = butter(4, [1, 30], btype='band', fs=SRATE, output='sos')   # 1-30 Hz: buang fuzz EMG/high-freq
_b_n, _a_n = iirnotch(NOTCH_HZ, 30, fs=SRATE)

def display_filter(x):
    y = sosfiltfilt(_sos_bp, x)
    y = filtfilt(_b_n, _a_n, y)
    return y

def is_railing(x):
    # elektroda mengambang -> nilai mentok 0 / rail, atau ptp ekstrem
    return x.min() < 1.0 or x.max() > 6500 or np.ptp(x) > 6000

# ---------------- BrainFlow ----------------
params = BrainFlowInputParams()
params.serial_number = SERIAL
params.other_info = "preset=p1041;low_latency=true"
params.timeout = 15

BoardShim.disable_board_logger()
board = BoardShim(BoardIds.MUSE_S_ATHENA_BOARD, params)
EEG = BoardShim.get_eeg_channels(BoardIds.MUSE_S_ATHENA_BOARD, BrainFlowPresets.DEFAULT_PRESET)

print(">> Menyambung ke Muse... (pastikan HP off & stream lain mati)")
board.prepare_session()
board.start_stream()
print(">> Streaming. Pakai headband, panel akan terbuka.")

buffers = [np.zeros(WINDOW) for _ in EEG]
t_axis  = np.linspace(-WINDOW_SEC, 0, WINDOW)
total   = {'n': 0}
frame   = {'n': 0}

# ---------------- GUI ----------------
app = QtWidgets.QApplication([])
win = pg.GraphicsLayoutWidget()
win.setWindowTitle("Muse S Athena - EEG Realtime")
win.resize(1000, 760)

curves, plots = [], []
yscale = [None] * len(CH_NAMES)        # skala-Y per channel, di-smooth biar nggak loncat
for i, name in enumerate(CH_NAMES):
    p = win.addPlot(row=i, col=0)
    p.setMouseEnabled(x=False, y=False)
    p.disableAutoRange('y')            # atur skala sendiri (autorange per-frame yang bikin terlihat "kasar")
    p.setYRange(-100, 100)
    p.showAxis('bottom', i == len(CH_NAMES) - 1)
    p.setLabel('left', name)
    if i > 0:
        p.setXLink(plots[0])
    c = p.plot(t_axis, buffers[i], pen=pg.mkPen(CH_COLORS[i], width=1.2))
    curves.append(c)
    plots.append(p)

# panel band power
pb = win.addPlot(row=len(CH_NAMES), col=0)
pb.setLabel('left', 'Band power (rel)')
pb.setMouseEnabled(x=False, y=False)
xb = np.arange(len(BANDS))
bar = pg.BarGraphItem(x=xb, height=[0] * len(BANDS), width=0.6, brush='#3273dc')
pb.addItem(bar)
pb.getAxis('bottom').setTicks([list(zip(xb, BANDS))])
pb.enableAutoRange('y', True)


def update():
    frame['n'] += 1
    slow = (frame['n'] % 20 == 0)      # update skala-Y & band power tiap ~1 dtk

    data = board.get_board_data(preset=BrainFlowPresets.DEFAULT_PRESET)
    m = data.shape[1]
    if m > 0:
        total['n'] += m
        for i, ch in enumerate(EEG):
            buffers[i] = np.concatenate([buffers[i], data[ch]])[-WINDOW:]

    valid = min(total['n'], WINDOW)
    if valid < SRATE:        # < 1 detik data, masih warmup
        return
    sl = slice(WINDOW - valid, WINDOW)

    good_idx = []
    for i in range(len(EEG)):
        seg = buffers[i][sl]
        if is_railing(seg):
            plots[i].setLabel('left', f"{CH_NAMES[i]}  -  NO CONTACT")
            curves[i].setPen(pg.mkPen('#888888', width=1.2))
            curves[i].setData(t_axis[sl], np.zeros(valid))
        else:
            good_idx.append(i)
            plots[i].setLabel('left', CH_NAMES[i])
            curves[i].setPen(pg.mkPen(CH_COLORS[i], width=1.2))
            yf = display_filter(seg)
            curves[i].setData(t_axis[sl], yf)
            if slow:           # skala-Y robust, di-smooth (EMA) -> stabil, nggak terlihat kasar
                amp = max(np.percentile(np.abs(yf), 95) * 1.4, 1e-6)
                yscale[i] = amp if yscale[i] is None else 0.8 * yscale[i] + 0.2 * amp
                plots[i].setYRange(-yscale[i], yscale[i])

    # band power dari channel yang kontaknya bagus
    if slow and good_idx:
        arr = np.vstack([buffers[i][sl].copy() for i in range(len(EEG))])
        try:
            bands, _ = DataFilter.get_avg_band_powers(arr, good_idx, SRATE, True)
            bar.setOpts(height=list(bands))
        except Exception:
            pass


timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(50)   # ~20 fps

win.show()
try:
    app.exec()
finally:
    timer.stop()
    if board.is_prepared():
        board.stop_stream()
        board.release_session()
    print(">> Panel ditutup, sesi dilepas.")