from abc import ABC, abstractmethod

import numpy as np


class CameraSource(ABC):
    """Interface every camera backend (mock, OpenCV, etc.) must implement."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def get_frame(self) -> np.ndarray | None:
        """Return the latest frame as an RGB uint8 array, or None if unavailable."""
        ...


class EEGSource(ABC):
    """Interface every EEG backend (mock, LSL, BLE headset, etc.) must implement."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @property
    @abstractmethod
    def channel_names(self) -> list[str]:
        ...

    @property
    @abstractmethod
    def sample_rate(self) -> float:
        ...

    @abstractmethod
    def get_samples(self) -> np.ndarray | None:
        """Return new samples since the last call, shape (n_channels, n_samples)."""
        ...
