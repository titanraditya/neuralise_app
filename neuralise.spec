# neuralise.spec — spesifikasi build PyInstaller untuk Neuralise.
#
# Build (dari dalam venv yang aktif):
#     pyinstaller neuralise.spec
#
# Hasil: dist/Neuralise/Neuralise.exe (mode onedir — bagikan seluruh folder dist/Neuralise/).
#
# Tips debug: set console=True di EXE(...) untuk build pertama supaya traceback terlihat
# saat dijalankan dari PowerShell; balikkan ke False setelah semuanya jalan.

from PyInstaller.utils.hooks import collect_all, collect_data_files

# File resource yang di-load lewat Path(__file__).parent — harus ada di lokasi relatif yg sama.
datas = [
    ('camera/face_landmarker.task', 'camera'),   # model MediaPipe (camera/detector.py)
    ('styles/light_theme.qss', 'styles'),        # stylesheet (main.py)
]
binaries = []
hiddenimports = []

# Paket dengan native library / data file yang tidak terjaring otomatis oleh hook standar.
for pkg in ('mediapipe', 'brainflow', 'pylsl'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Font bawaan reportlab untuk render PDF (tools/report.py).
datas += collect_data_files('reportlab')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Neuralise',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # GUI app. Set True sementara untuk melihat traceback saat debug.
    disable_windowed_traceback=False,
    icon=None,       # ganti ke 'app.ico' bila punya ikon aplikasi
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Neuralise',
)
