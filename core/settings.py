from PySide6.QtCore import QSettings

_ORG = "Neuralise"
_APP = "Neuralise"
_KEY_WARN_MISSING_DASS21 = "warn_missing_dass21"
_KEY_FEATURE_PREFIX = "features/"

# Modalitas yang bisa dipilih di menu awal (FeatureSelectDialog). "museeog" adalah EOG turunan
# dari elektrode frontal headset Muse — menumpang koneksi EEG, jadi hanya valid saat "eeg" aktif.
FEATURE_KEYS = ("camera", "eeg", "museeog", "eog")


def get_warn_missing_dass21() -> bool:
    return bool(QSettings(_ORG, _APP).value(_KEY_WARN_MISSING_DASS21, True, type=bool))


def set_warn_missing_dass21(enabled: bool) -> None:
    QSettings(_ORG, _APP).setValue(_KEY_WARN_MISSING_DASS21, enabled)


def get_enabled_features() -> dict[str, bool]:
    """Pilihan fitur terakhir dari menu awal; default semua aktif (perilaku lama). Muse-EOG
    dipaksa mati kalau EEG mati — ia menumpang koneksi EEG, tidak bisa berdiri sendiri."""
    settings = QSettings(_ORG, _APP)
    features = {
        key: bool(settings.value(_KEY_FEATURE_PREFIX + key, True, type=bool))
        for key in FEATURE_KEYS
    }
    if not features["eeg"]:
        features["museeog"] = False
    return features


def set_enabled_features(features: dict[str, bool]) -> None:
    settings = QSettings(_ORG, _APP)
    for key in FEATURE_KEYS:
        settings.setValue(_KEY_FEATURE_PREFIX + key, bool(features.get(key, True)))
