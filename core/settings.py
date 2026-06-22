from PySide6.QtCore import QSettings

_ORG = "Neuralise"
_APP = "Neuralise"
_KEY_WARN_MISSING_DASS21 = "warn_missing_dass21"


def get_warn_missing_dass21() -> bool:
    return bool(QSettings(_ORG, _APP).value(_KEY_WARN_MISSING_DASS21, True, type=bool))


def set_warn_missing_dass21(enabled: bool) -> None:
    QSettings(_ORG, _APP).setValue(_KEY_WARN_MISSING_DASS21, enabled)
