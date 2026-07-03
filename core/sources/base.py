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

    def filter_for_display(self, segment: np.ndarray) -> np.ndarray:
        """Clean up a single-channel segment for plotting. Default: no filtering."""
        return segment

    def check_contact(self, segment: np.ndarray) -> bool:
        """Return False if a single-channel segment looks like a lost/floating electrode."""
        return True

    def band_powers(self, segments: np.ndarray, good_channels: list[int]) -> list[float] | None:
        """Return [delta, theta, alpha, beta, gamma] averaged over good_channels, or None if unsupported."""
        return None

    # -- EOG-from-EEG: some headsets (e.g. Muse) have frontal electrodes near the eyes that
    # double as an EOG pickup, so a single EOG channel can be derived from the EEG stream
    # without a second device/connection. Sources that can't do this leave the defaults. --

    @property
    def supports_eog(self) -> bool:
        """Whether derive_eog() yields a usable EOG channel from this source's electrodes."""
        return False

    @property
    def eog_channel_name(self) -> str:
        """Label for the EOG channel derive_eog() produces."""
        return "EOG"

    @property
    def eog_channel_indices(self) -> tuple[int, ...]:
        """Indices into channel_names whose contact status governs the derived EOG channel."""
        return ()

    def derive_eog(self, samples: np.ndarray) -> np.ndarray | None:
        """Derive one EOG channel (shape (n_samples,)) from a fresh EEG chunk
        (n_channels, n_samples). None if this source can't provide EOG."""
        return None

    def filter_eog_for_display(self, segment: np.ndarray) -> np.ndarray:
        """EOG-appropriate cleanup for plotting (keep low freqs, drop DC). Default: DC removal."""
        return segment - segment.mean() if len(segment) else segment


class EOGSource(ABC):
    """Interface every EOG backend (mock, LSL/OpenSignals, etc.) must implement."""

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

    def filter_for_display(self, segment: np.ndarray) -> np.ndarray:
        """Clean up a single-channel segment for plotting. Default: no filtering."""
        return segment

    def check_contact(self, segment: np.ndarray) -> bool:
        """Return False if a single-channel segment looks like a lost/floating electrode."""
        return True
