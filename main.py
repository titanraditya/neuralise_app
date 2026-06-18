import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)

    qss_path = Path(__file__).parent / "styles" / "dark_theme.qss"
    app.setStyleSheet(qss_path.read_text())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
