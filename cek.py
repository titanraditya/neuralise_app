import time, numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowPresets
from brainflow.data_filter import DataFilter

BoardShim.disable_board_logger()        # matikan spam log 0x53 biar output bersih

params = BrainFlowInputParams()
params.serial_number = "MuseS-DA8F"
params.other_info = "preset=p1041;low_latency=true"
params.timeout = 15

board = BoardShim(BoardIds.MUSE_S_ATHENA_BOARD, params)
srate = 256                              # sudah dikonfirmasi dari run sebelumnya
eeg = BoardShim.get_eeg_channels(BoardIds.MUSE_S_ATHENA_BOARD, BrainFlowPresets.DEFAULT_PRESET)
TP9, AF7, AF8, TP10 = eeg
labels = {TP9:"TP9", AF7:"AF7", AF8:"AF8", TP10:"TP10"}

def capture(sec):
    board.get_board_data(preset=BrainFlowPresets.DEFAULT_PRESET)   # buang buffer lama
    time.sleep(sec)
    return board.get_board_data(preset=BrainFlowPresets.DEFAULT_PRESET)

def alpha(data, channels):
    bands, _ = DataFilter.get_avg_band_powers(data, channels, srate, True)
    return bands[2]                      # 0=delta 1=theta 2=alpha 3=beta 4=gamma

try:
    board.prepare_session()
    board.start_stream()
    print(">> Pakai headband, duduk tenang. Settling 12 detik...")
    time.sleep(12)

    d = capture(8)
    print(f"\nKualitas kontak ({d.shape[1]} sampel):")
    for ch in eeg:
        r = d[ch]
        print(f"  {labels[ch]:4s}: mean={r.mean():8.1f}  ptp={np.ptp(r):8.1f}  min={r.min():7.1f}  max={r.max():7.1f}")

    input("\n>> ENTER, lalu MATA TERBUKA pandang lurus 10 detik...")
    a_open = alpha(capture(10), [TP9, TP10])
    input(">> ENTER, lalu langsung TUTUP MATA 10 detik...")
    a_closed = alpha(capture(10), [TP9, TP10])

    print(f"\nAlpha mata-buka : {a_open:.4f}")
    print(f"Alpha mata-tutup: {a_closed:.4f}")
    r = a_closed / a_open if a_open else 0
    print(f"Rasio tutup/buka: {r:.2f}x ->",
          "EEG VALID (alpha naik saat mata tutup)" if r > 1.3 else "alpha tidak naik jelas - cek kontak/posisi elektroda")
finally:
    if board.is_prepared():
        board.release_session()