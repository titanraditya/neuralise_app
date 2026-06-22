# Neuralise — panduan kerja untuk Claude Code

Neuralise adalah aplikasi desktop PySide6 untuk riset drowsiness: kamera
(EAR/PERCLOS via MediaPipe) + EEG (rasio band power via Muse S Athena/BrainFlow),
dengan DASS-21 sebagai kriteria inklusi di awal sesi dan SART sebagai laporan
subjektif di akhir. Untuk breakdown file-per-file dan daftar gap yang sudah
diverifikasi dari kode, baca `BRIEF_UNTUK_OPUS.md` di root repo — dokumen itu
snapshot per tanggal pembuatannya, jangan anggap selalu akurat untuk kondisi
kode terbaru.

## Arsitektur saat ini (ringkas)

UI adalah wizard 4 layar (`QStackedWidget` di `ui/main_window.py`): Welcome →
QuestionnaireScreen (DASS-21) → Monitoring (camera+EEG+status+control bar) →
SARTQuestionnaireScreen. Kamera dan EEG dikoneksi/dikoneksikan manual lewat
tombol di `ControlBar`, hidup-matinya terikat ke layar Monitoring saja —
tidak ada live preview di luar layar itu, dan koneksi tidak persisten across
sesi (tombol "Connect EEG" mereset kalibrasi `EEGDrowsinessDetector` setiap
kali). Tiga jenis output (`questionnaire_*.json`, `session_*.csv`,
`sart_*.json`) ditulis ke `recordings/` dengan nama file berbasis timestamp,
**tidak ada session_id yang menyambungkan ketiganya**.

## Arsitektur target (belum diimplementasikan — arah refactor ke depan)

Perubahan struktural yang ingin dituju, bertahap di task-task berikutnya:

- **DeviceManager** (level rig) — pemilik koneksi kamera + EEG yang
  **persisten**: connect sekali, streaming terus jalan untuk live preview,
  tidak bergantung pada ada/tidaknya sesi perekaman yang aktif. ini
  menggantikan pola sekarang (connect/disconnect manual per layar, kalibrasi
  EEG reset tiap reconnect).
- **Session** (level perekaman) — satu run riset untuk satu subjek,
  diidentifikasi `session_id`. Semua output satu sesi (CSV kamera, CSV EEG
  yang belum ada sekarang, JSON DASS-21, JSON SART) ditulis ke **satu folder**
  `recordings/<session_id>/`, bukan tersebar dengan nama file timestamp lepas
  seperti sekarang. Ini yang menyelesaikan gap "tidak ada ID yang
  menyambungkan ketiga jenis file" di BRIEF_UNTUK_OPUS.md.
- **UI satu layar, dua mode** — bukan wizard 4 layar. Satu layar utama dengan
  mode **SIAP** (rig terhubung, live preview tampil, belum ada session_id
  aktif) dan **SESI AKTIF** (sedang merekam ke `recordings/<session_id>/`).
  DeviceManager tetap streaming di kedua mode.
- **Kuesioner DASS-21/SART jadi modal opsional** yang bisa dibuka kapan saja
  (bukan langkah wajib berurutan di wizard) dan saat disimpan di-attach ke
  `session_id` yang sedang aktif.

Jangan implementasikan ini sekaligus dalam satu task besar kecuali user minta
eksplisit — pecah jadi langkah-langkah kecil, dan konfirmasi urutan/scope ke
user sebelum mulai setiap langkah.

## Aturan tetap (berlaku di SEMUA task, bukan cuma task ini)

1. **Ini refactor struktur, bukan tuning.** Jangan ubah algoritma atau angka
   threshold yang sudah ada: EAR (`camera/detector.py`), PERCLOS
   (`camera/perclos.py`: window 30s, EAR<0.25, drowsy>15%), band power
   (`core/sources/muse.py`), `EEGDrowsinessDetector` (kalibrasi 30s, rasio
   >1.5×baseline di `core/eeg_drowsiness.py`), dan fusion OR-rule di
   `ui/widgets/status_panel.py` (`drowsy > awake > calibrating > idle`). Kalau
   sebuah task sepertinya butuh ubah angka/logic ini, berhenti dan tanya user
   dulu — jangan asumsikan itu bagian dari scope refactor.
2. **Pertahankan light theme** (`styles/light_theme.qss`) — jangan kembalikan
   dark theme atau buat stylesheet baru tanpa diminta.
3. **Pertahankan board id `MUSE_S_ATHENA_BOARD`** di `core/sources/muse.py` —
   jangan ganti ke board id Muse lain tanpa konfirmasi eksplisit.
4. **Jangan tambah dependency baru** (apa pun yang tidak sudah ada di
   `requirements.txt`) tanpa konfirmasi user dulu.
5. **Jangan ubah format kolom `session_*.csv` yang sudah ada**
   (`timestamp,ear_left,ear_right,ear_avg,perclos,status` dari
   `camera/recorder.py`) — data lama di `recordings/` harus tetap bisa
   dibaca dengan skema yang sama. Kalau butuh data tambahan (misal EEG),
   buat file baru, jangan tambah/ubah kolom di file existing.
6. **Jangan `git commit` atau `git push`** kecuali user minta secara
   eksplisit di task tersebut. User yang mengelola commit history sendiri.

## Menjalankan app

```
python main.py                 # hardware asli (webcam + Muse S Athena via BrainFlow)
python main.py --mock          # MockCameraSource + MockEEGSource, tanpa hardware
NEURALISE_MOCK=1 python main.py  # alternatif env var untuk --mock
```

Mode `--mock` memakai `core/sources/mock.py` (`MockCameraSource`/
`MockEEGSource`) lewat `CameraThread(use_mock=True)` dan `MockEEGSource()` di
`ui/main_window.py` — frame kamera animasi sintetis + EAR yang berfluktuasi
dengan periode "drowsy" berkala, dan EEG 4-channel sintetis + band power acak
yang juga periodik memicu status drowsy. Tombol Connect Camera/EEG di UI
tetap dipakai seperti biasa, hanya sumber datanya yang diganti. Berguna untuk
dev/demo tanpa webcam atau headset Muse.
