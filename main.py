import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog

from core.settings import get_enabled_features, set_enabled_features
from ui.dialogs.feature_select_dialog import FeatureSelectDialog
from ui.main_window import MainWindow


def main() -> None:
    # Saat di-freeze jadi exe, GUI tidak bisa memanggil `sys.executable -m tools.report`
    # (exe hasil PyInstaller mengabaikan -m). Sebagai gantinya GUI memanggil ulang exe ini
    # dengan sentinel --run-report <session_dir>; di sini kita jalankan report worker lalu
    # keluar — SEBELUM QApplication/dialog dibuat, supaya subprocess tidak ikut membuka UI.
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-report":
        from tools.report import render_session_report

        render_session_report(sys.argv[2])
        return

    parser = argparse.ArgumentParser(description="Neuralise drowsiness detection app")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=os.environ.get("NEURALISE_MOCK") == "1",
        help="Use synthetic camera/EEG sources instead of real hardware (no webcam/Muse needed)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    qss_path = Path(__file__).parent / "styles" / "light_theme.qss"
    app.setStyleSheet(qss_path.read_text())

    # Menu awal: pilih fitur yang dipakai di panel monitoring untuk run ini. Pilihan tersimpan
    # di QSettings jadi centang default mengikuti run sebelumnya; batal berarti keluar.
    feature_dialog = FeatureSelectDialog(get_enabled_features(), startup=True)
    if feature_dialog.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)
    features = feature_dialog.selected_features()
    set_enabled_features(features)

    window = MainWindow(mock=args.mock, features=features)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
