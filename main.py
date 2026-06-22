import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> None:
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

    window = MainWindow(mock=args.mock)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
