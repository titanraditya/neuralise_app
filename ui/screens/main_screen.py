from PySide6.QtCore import QTime, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.effects import apply_card_shadow
from ui.widgets.camera_panel import CameraPanel
from ui.widgets.device_row import DeviceRow
from ui.widgets.eeg_panel import EEGPanel
from ui.widgets.eog_panel import EOGPanel
from ui.widgets.history_drawer import HistoryDrawer
from ui.widgets.session_strip import SessionControlStrip
from ui.widgets.status_panel import StatusPanel


def _section(label: str, widget: QWidget) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    caption = QLabel(label)
    caption.setObjectName("sectionLabel")
    layout.addWidget(caption)
    layout.addWidget(widget, stretch=1)
    return container


class MainScreen(QWidget):
    """Single screen, two modes (SIAP / SESI AKTIF) — replaces the old 4-page wizard.

    Pure composition + child widgets exposed as public attributes; DeviceManager/Session
    lifecycle and signal wiring live in MainWindow.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.device_row = DeviceRow()
        apply_card_shadow(self.device_row)

        self.camera_panel = CameraPanel()
        self.eeg_panel = EEGPanel()
        self.eog_panel = EOGPanel()  # OpenSignals/BITalino EOG (LSL)
        self.museeog_panel = EOGPanel()  # EOG derived from the Muse AF7 frontal electrode
        self.status_panel = StatusPanel()

        self.control_strip = SessionControlStrip()
        apply_card_shadow(self.control_strip)

        self.history_drawer = HistoryDrawer()
        apply_card_shadow(self.history_drawer)

        self._clock_label = QLabel()
        self._clock_label.setObjectName("clockLabel")
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)
        self._update_clock()

        main_column = QVBoxLayout()
        main_column.setContentsMargins(0, 0, 0, 0)
        main_column.setSpacing(6)
        main_column.addWidget(self._build_header())
        main_column.addWidget(self.device_row)

        content = QHBoxLayout()
        content.setSpacing(10)
        content.addWidget(_section("Camera", self.camera_panel), stretch=1)

        # The two single-trace EOG panels sit side by side rather than stacked: the screen's
        # tight dimension is height, so giving each modality its own vertical slot no longer
        # fits on one screen. Horizontally there's room to spare.
        eog_row = QHBoxLayout()
        eog_row.setContentsMargins(0, 0, 0, 0)
        eog_row.setSpacing(8)
        eog_row.addWidget(_section("EOG · BITalino", self.eog_panel), stretch=1)
        eog_row.addWidget(_section("EOG · Muse (AF7)", self.museeog_panel), stretch=1)
        eog_row_widget = QWidget()
        eog_row_widget.setLayout(eog_row)

        right_column = QVBoxLayout()
        right_column.setSpacing(6)
        right_column.addWidget(_section("EEG Signal", self.eeg_panel), stretch=3)
        right_column.addWidget(eog_row_widget, stretch=2)
        content.addLayout(right_column, stretch=1)

        content_widget = QWidget()
        content_widget.setLayout(content)

        # No QScrollArea here on purpose: the layout is compact enough to fit on one screen, and
        # sizing content purely by stretch factors keeps every panel proportional. (A scroll area
        # would size this to its tall sizeHint whenever a word-wrapped "not connected" placeholder
        # became visible — via heightForWidth — ballooning the EEG plot and forcing a scrollbar.)
        main_column.addWidget(content_widget, stretch=1)
        # Status is a full-width strip (not inside the scrollable content column): a single row
        # of badges reads better across the whole width, and keeping it out of the right column
        # frees the vertical space that was forcing everything to scroll.
        main_column.addWidget(self.status_panel)
        main_column.addWidget(self.control_strip)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(12)
        root.addLayout(main_column, stretch=1)
        root.addWidget(self.history_drawer)

    def _build_header(self) -> QWidget:
        title_box = QVBoxLayout()
        title = QLabel("Neuralise")
        title.setObjectName("appTitle")
        subtitle = QLabel("Drowsiness Detection — EEG + Camera Monitoring")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header_bar = QFrame()
        header_bar.setObjectName("headerBar")
        apply_card_shadow(header_bar)
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(12, 6, 12, 6)
        header.addLayout(title_box)
        header.addStretch(1)
        header.addWidget(self._clock_label, alignment=Qt.AlignmentFlag.AlignRight)
        return header_bar

    def _update_clock(self) -> None:
        self._clock_label.setText(QTime.currentTime().toString("hh:mm:ss"))
