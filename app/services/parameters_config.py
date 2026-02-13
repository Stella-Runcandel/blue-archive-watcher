"""Runtime/base configuration wrappers for Parameters tab."""
from __future__ import annotations

from dataclasses import dataclass

from core.profiles import get_detection_threshold, update_profile_detection_threshold


@dataclass(frozen=True)
class BaseProfileConfig:
    profile_name: str
    detection_threshold: float

    @classmethod
    def from_profile(cls, profile_name: str) -> "BaseProfileConfig":
        return cls(
            profile_name=profile_name,
            detection_threshold=get_detection_threshold(profile_name),
        )


@dataclass
class RuntimeDebugConfig:
    detection_threshold: float

    @classmethod
    def from_base(cls, base: BaseProfileConfig) -> "RuntimeDebugConfig":
        return cls(detection_threshold=base.detection_threshold)


def apply_debug_settings(base: BaseProfileConfig, runtime: RuntimeDebugConfig) -> BaseProfileConfig:
    """Persist debug-only fields and return refreshed base config."""
    update_profile_detection_threshold(base.profile_name, runtime.detection_threshold)
    return BaseProfileConfig.from_profile(base.profile_name)
