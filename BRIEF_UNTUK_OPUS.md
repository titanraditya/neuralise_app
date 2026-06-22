# Brief Proyek "Neuralise" — untuk didiskusikan dengan Claude (Opus) web

> File ini dibuat otomatis dengan membaca seluruh kode di repo `neuralise1` per
> 2026-06-22. Tujuannya: jadi satu dokumen "siap tempel" ke Claude web (Opus)
> supaya bisa diajak diskusi merumuskan langkah selanjutnya — tanpa Opus perlu
> akses ke repo. Semua klaim di bawah diverifikasi langsung dari source code,
> bukan tebakan.

---

## 1. Apa proyek ini

**Neuralise** adalah aplikasi desktop (PySide6/Qt) untuk **riset deteksi
kantuk (drowsiness)** yang menggabungkan dua modalitas sensor secara real-time:

1. **Kamera** — deteksi kantuk dari mata (EAR / Eye Aspect Ratio → PERCLOS)
   menggunakan MediaPipe Face Landmarker.
2. **EEG** — deteksi kantuk dari sinyal otak menggunakan headband **Muse S
   Athena** (lewat BrainFlow), berbasis rasio band power (Theta+Alpha)/Beta
   yang dikalibrasi per-individu.

Konteksnya jelas riset eksperimental dengan manusia sebagai subjek:
- Ada field "Level Noise" dan "Content Noise" di kuesioner → sepertinya
  eksperimen memanipulasi **paparan kebisingan (noise)** sebagai variabel
  independen, lalu mengukur efeknya ke kantuk/kewaspadaan.
- Ada kuesioner **DASS-21** (Depression Anxiety Stress Scale) di awal sesi
  sebagai **kriteria inklusi** — subjek harus "Normal" di ketiga subskala
  (Depresi/Kecemasan/Stres) baru boleh lanjut, supaya hasil drowsiness tidak
  bias oleh kondisi psikologis subjek.
- Ada kuesioner **SART** (Situation Awareness Rating Technique, 9 item) di
  akhir sesi untuk mengukur situational awareness subjektif subjek saat
  mengerjakan tugas dengan paparan noise.

Jadi alurnya kira-kira: **screening (DASS-21) → sesi monitoring (kamera+EEG
real-time, dengan noise sebagai treatment) → SART (laporan subjektif) →
selesai**.

## 2. Tech stack

- Python 3.11.9 (`.python-version`), virtualenv di `venv/` (sudah di-ignore git)
- GUI: **PySide6** 6.11.1 (Qt for Python)
- Plot real-time: **pyqtgraph** 0.14.0
- Kamera/CV: **opencv-python** 4.12.0.88
- Face landmark: **mediapipe** 0.10.35 (model `face_landmarker.task`,
  auto-download ~3MB dari Google Storage kalau belum ada di `camera/`)
- EEG hardware: **brainflow** 5.22.2 (board id `MUSE_S_ATHENA_BOARD`)
- Signal processing: **scipy** 1.17.1 (butterworth bandpass + notch filter)
- numpy 2.2.6

Cara jalanin: `python main.py` dari root (load `styles/light_theme.qss`,
buka `MainWindow`).

Dua script standalone di root yang **bukan bagian dari app utama**, tampaknya
alat eksplorasi/kalibrasi manual saat development:
- `cek.py` — script CLI buat ngecek kualitas kontak elektroda Muse S Athena
  dan validasi alpha naik saat mata tertutup (sanity check headset).
- `muse_eeg_panel.py` — standalone PyQtGraph panel EEG real-time (mirip
  `ui/widgets/eeg_panel.py` tapi versi awal/terpisah, tidak diimpor oleh
  `main.py`). Kemungkinan prototype sebelum logic-nya dipindah ke
  `core/sources/muse.py` + `ui/widgets/eeg_panel.py`.

## 3. Struktur kode

```
main.py                          # entry point, load QSS, buka MainWindow
cek.py                           # CLI standalone: sanity check Muse headset
muse_eeg_panel.py                # standalone prototype panel EEG (tidak dipakai main.py)

core/
  eeg_drowsiness.py              # EEGDrowsinessDetector: kalibrasi baseline -> deteksi drowsy
  sources/
    base.py                      # ABC: CameraSource, EEGSource (interface)
    mock.py                      # MockCameraSource, MockEEGSource — TIDAK dipakai di mana pun
    muse.py                      # MuseEEGSource: implementasi nyata via BrainFlow

camera/
  camera_thread.py                # QThread: capture cv2, jalanin EyeDetector, emit sinyal
  detector.py                     # EyeDetector (MediaPipe FaceLandmarker) -> EAR kiri/kanan
  perclos.py                      # PerclosCalculator: sliding window 30s, threshold EAR<0.25
  recorder.py                     # SessionRecorder: tulis CSV per-frame (ear, perclos, status)
  face_landmarker.task            # model file (auto-downloaded)

ui/
  main_window.py                  # MainWindow: QStackedWidget 4 layar + wiring semua sinyal
  effects.py                      # apply_card_shadow() — drop shadow buat "card" look
  screens/
    welcome_screen.py              # layar awal: judul, tombol "Mulai Sesi" & "Unduh Laporan" (zip recordings/)
    questionnaire_screen.py        # DASS-21: 21 soal, skor 3 subskala, validasi inklusi
    sart_questionnaire_screen.py   # SART: 9 soal skala 1-7
  widgets/
    camera_panel.py                 # render frame kamera (QLabel + QPixmap)
    eeg_panel.py                    # plot multi-channel EEG + band power bar + status kalibrasi
    control_bar.py                  # tombol: Connect Camera/EEG, Start Recording, Start Monitoring, Selesai
    status_panel.py                 # badge EEG/Camera/Final (fusion OR-rule) + tile metrik

styles/
  light_theme.qss                  # satu-satunya stylesheet aktif sekarang

recordings/                        # output sesi (di-gitignore), berisi contoh data lama
requirements.txt
.python-version
.gitignore
```

## 4. Alur aplikasi (state machine `QStackedWidget` di `MainWindow`)

```
[0] WelcomeScreen
      └─ klik "Mulai Sesi" ──────────────► [1] QuestionnaireScreen (DASS-21)
      └─ klik "Unduh Laporan" → zip semua isi recordings/ ke file pilihan user

[1] QuestionnaireScreen (DASS-21)
      └─ submit (lolos kriteria / boleh skip) ─► simpan JSON ke recordings/
                                                  questionnaire_<timestamp>.json
                                                  → pindah ke [2]

[2] Monitoring (camera + EEG + status panel + control bar)
      - Connect Camera  -> start CameraThread (capture + EyeDetector + PERCLOS)
      - Connect EEG     -> start MuseEEGSource (BrainFlow, real hardware only)
      - Start Recording -> SessionRecorder nulis CSV (hanya data kamera: EAR/PERCLOS,
                            EEG TIDAK direkam ke file apa pun)
      - Start Monitoring -> cuma jalanin stopwatch sesi (QTimer di StatusPanel)
      - Selesai         -> pindah langsung ke [3] (TANPA stop camera/EEG thread!)

[3] SARTQuestionnaireScreen
      └─ Simpan -> JSON ke recordings/sart_<timestamp>.json
      └─ Mulai Sesi Baru -> reset SART form, balik ke [0]
```

## 5. Algoritma inti

### 5.1 Kamera — PERCLOS
- `EyeDetector` (MediaPipe FaceLandmarker, 1 wajah) ambil 6 landmark per mata
  → hitung **EAR** (Eye Aspect Ratio) standar (rasio jarak vertikal/horizontal).
- `PerclosCalculator`: sliding window 30 detik, tiap sample EAR < 0.25
  dihitung "mata tertutup". `perclos = closed / total` dalam window.
  Status "drowsy" kalau `perclos > 0.15` (15%).
- Frame + EAR + PERCLOS di-emit via Qt Signal dari `CameraThread` (QThread
  terpisah) ke UI tiap frame.

### 5.2 EEG — rasio band power terkalibrasi
- `MuseEEGSource` ambil 4 channel (TP9, AF7, AF8, TP10) @256Hz dari BrainFlow,
  filter tampilan: bandpass 1-30Hz + notch 50Hz (listrik Indonesia).
- Deteksi "no contact" per channel: sinyal mentok rail (`min<1.0`,
  `max>6500`, atau `ptp>6000`).
- Band power (delta/theta/alpha/beta/gamma) dihitung BrainFlow
  `get_avg_band_powers`, hanya dari channel yang kontaknya bagus, ~1x/detik.
- `EEGDrowsinessDetector`: kalibrasi 30 detik pertama (kumpulkan rasio
  `(theta+alpha)/beta`, rata-ratakan jadi baseline personal), setelah itu
  status "drowsy" jika rasio saat ini > `1.5 × baseline`. Eksplisit
  didokumentasikan di kode sebagai **bukan ambang klinis yang divalidasi**,
  cuma heuristik yang bisa di-tune (`DROWSY_RATIO_MULTIPLIER`).
- Kalibrasi reset setiap kali user klik "Connect EEG" lagi (tidak persisten
  antar sesi).

### 5.3 Fusion status akhir
- `status_panel.py`: status final = status paling "urgent" di antara EEG dan
  Camera, dengan urutan prioritas `drowsy > awake > calibrating > idle`
  (OR-rule — kalau salah satu bilang drowsy, hasil akhir drowsy).

## 6. Format data output (semua di `recordings/`, di-gitignore)

**`questionnaire_<ts>.json`** (DASS-21):
```json
{
  "timestamp": "...", "nama": "...", "usia": "...", "jenis_kelamin": "...",
  "level_noise": "", "content_noise": "",
  "answers": {"1": 0, ..., "21": 0},
  "scores": {"D": 0, "A": 0, "S": 0},
  "levels": {"D": "Normal", "A": "Normal", "S": "Normal"}
}
```

**`sart_<ts>.json`**:
```json
{"timestamp": "...", "nama": "...", "level_noise": "1",
 "answers": {"1": 1, ..., "9": 1}}
```

**`session_<ts>.csv`** (dari kamera saja, per-frame ~30fps):
```
timestamp,ear_left,ear_right,ear_avg,perclos,status
13:16:59.827,0.1821,0.1356,0.1589,1.0000,drowsy
```

⚠️ Catatan: ketiga jenis file ini **tidak punya ID sesi/subjek yang
menyambungkan mereka** — hanya nama file berbasis timestamp independen.
Tidak ada file yang merekam data EEG mentah/derived sama sekali.

## 7. Status Git saat ini (per 2026-06-22)

Branch `main`, working tree **sedang di tengah redesign besar yang belum
di-commit**:
- `styles/dark_theme.qss` dihapus (staged delete) → app pindah dari dark
  theme ke **light theme** (`styles/light_theme.qss`, baru/untracked).
- File baru (untracked): `core/eeg_drowsiness.py` (modul kalibrasi+deteksi
  drowsy EEG), `ui/effects.py` (drop shadow helper).
- Modified (belum staged): `main.py`, `ui/main_window.py`, dan hampir semua
  screen/widget di `ui/` — perubahan signifikan (lihat `git diff --stat`:
  total +227/-51 baris) seputar fusion status, card-shadow styling,
  kalibrasi EEG, refactor `CameraPanel`/`ControlBar`.
- Commit terakhir: `06b2605 Fix: add recordings to gitignore`, sebelumnya
  `601a625 kuesioner 2`, `3e6f76f kuesioner sblm` — riwayat menunjukkan
  kuesioner ditambahkan belakangan setelah fitur EEG+kamera inti (`74796f2
  Feat: add EEG detection`, `57428bc camera`).

→ **Belum ada commit untuk redesign light-theme + EEG calibration ini.**

## 8. Temuan / observasi (gap & potensi masalah, terverifikasi dari kode)

1. **`MockCameraSource` & `MockEEGSource`** (`core/sources/mock.py`) sudah
   diimplementasi lengkap sesuai interface `CameraSource`/`EEGSource`, tapi
   **tidak dipakai di mana pun** (`grep` konfirmasi tidak ada referensi di
   luar file itu sendiri). Tidak ada cara menjalankan/demo app tanpa hardware
   kamera+Muse asli.
2. **Tombol "Selesai" tidak menghentikan sesi.** `_wire_controls()` di
   `main_window.py` cuma `lambda: self._stack.setCurrentIndex(3)` — kalau
   user klik Selesai saat kamera/EEG masih connect, `CameraThread` tetap
   jalan di background (thread leak), state `ControlBar` ("Disconnect...")
   juga tidak direset.
3. **EEG sama sekali tidak direkam ke file.** `SessionRecorder` cuma nulis
   data kamera (EAR/PERCLOS). Tidak ada CSV/JSON untuk band power atau
   status drowsy EEG per waktu — padahal ini salah satu dari dua modalitas
   utama riset.
4. **Tile "Blink rate (bpm)" dan "Alerts triggered"** ada di UI
   (`status_panel.py`) tapi **tidak pernah di-update** — tidak ada kode yang
   memanggil `set_metric("blink_rate", ...)` atau `set_metric("alerts", ...)`
   di mana pun. UI placeholder yang belum diisi datanya.
5. **Tidak ada ID subjek/sesi yang konsisten** menyambungkan
   `questionnaire_*.json`, `session_*.csv`, dan `sart_*.json` — kalau mau
   analisis statistik nanti (gabungkan DASS-21 × noise level × PERCLOS × EEG
   × SART per subjek), harus join manual berbasis nama+waktu, rawan salah.
6. **Hardware EEG hardcoded** ke `MUSE_S_ATHENA_BOARD` tanpa serial number
   default (`MuseEEGSource(serial_number="")` di `main_window.py`, auto
   discover) — tidak ada UI untuk pilih device kalau ada >1 Muse di sekitar.
7. **Tidak ada automated test sama sekali** (tidak ada folder `tests/`).
   Logic yang paling "bernilai-riset" (PERCLOS, EAR, rasio EEG, scoring
   DASS-21/SART) semua bisa di-unit-test karena pure-function/kelas kecil,
   tapi belum ada.
8. **Tidak ada dokumentasi** (tidak ada README/CLAUDE.md) — onboarding
   kontributor baru atau "future-self" bergantung total ke baca kode.
9. **Kalibrasi EEG (`CALIBRATION_SECONDS=30`) tidak persisten** — device yang
   sama dikalibrasi ulang dari nol setiap kali user toggle "Connect EEG",
   termasuk kalau cuma reconnect karena drop koneksi BLE.
10. **`muse_eeg_panel.py` dan `cek.py`** sepertinya leftover script
    development/kalibrasi manual, terpisah dari arsitektur `core/sources/*`
    yang lebih bersih — kandidat untuk dihapus, dipindah ke folder `tools/`,
    atau didokumentasikan sebagai utilitas resmi.

## 9. Pertanyaan untuk didiskusikan / minta dirumuskan oleh Opus

Saya ingin bantuan merumuskan **langkah selanjutnya** untuk proyek ini.
Beberapa arah yang ingin dipikirkan bersama:

1. Prioritas mana dulu: beresin bug/gap di atas (terutama #2 thread leak dan
   #3 EEG tidak direkam), atau lanjut commit dulu redesign yang sudah di
   working tree (light theme + kalibrasi EEG)?
2. Bagaimana skema penamaan/ID sesi yang baik supaya data kuesioner + CSV
   kamera + (nanti) data EEG bisa di-join dengan rapi untuk analisis
   statistik skripsi/riset?
3. Apakah perlu menambahkan perekaman EEG (band power + status drowsy per
   waktu) ke file, sejajar dengan `SessionRecorder` punya kamera?
4. Apakah mock sources (`core/sources/mock.py`) sebaiknya diaktifkan sebagai
   mode "demo/dev tanpa hardware" (lewat flag/env var), atau dihapus saja
   kalau memang tidak akan dipakai?
5. Threshold yang dipakai sekarang (EAR<0.25, PERCLOS>15%, rasio EEG
   >1.5×baseline) semua disclaim sebagai "belum divalidasi secara klinis" —
   apakah perlu rencana validasi (misal bandingkan ke ground-truth manual
   atau literatur) sebelum dipakai untuk pengambilan data riset sungguhan?
6. Apakah arsitektur `CameraSource`/`EEGSource` (ABC) ini sudah cukup buat
   menambah sensor baru di masa depan (misal heart rate / GSR), atau perlu
   direvisi?
7. Strategi testing: bagian mana yang paling bernilai untuk di-unit-test
   duluan (PERCLOS, EAR, EEGDrowsinessDetector, scoring DASS-21/SART semua
   pure logic, gampang ditest tanpa hardware)?

---
*(Dihasilkan oleh Claude Code dengan membaca seluruh source code di repo
`neuralise1`, termasuk working-tree changes yang belum di-commit. Tidak ada
asumsi yang tidak diverifikasi dari kode aktual.)*
