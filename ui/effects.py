from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def apply_card_shadow(widget: QWidget, blur_radius: int = 24, y_offset: int = 6, alpha: int = 30) -> None:
    """Soft drop shadow used to lift card-like surfaces off the light background."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setOffset(0, y_offset)
    shadow.setColor(QColor(20, 30, 60, alpha))
    widget.setGraphicsEffect(shadow)
