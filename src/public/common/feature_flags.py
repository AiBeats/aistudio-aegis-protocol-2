"""ABV Sovereign Stack — Feature Flag System.

Simple, environment-driven feature flags for toggling capabilities at runtime
without redeployment. Flags default to *off* unless explicitly enabled.
"""

from __future__ import annotations

import os
from typing import Dict


class FeatureFlags:
    """Evaluate feature flags from environment variables.

    Convention: ``ABV_FLAG_<NAME>=1`` enables a flag.  Anything else
    (including absence) disables it.
    """

    _PREFIX = "ABV_FLAG_"

    # Built-in flag names and their descriptions
    KNOWN_FLAGS: Dict[str, str] = {
        "THERMAL_GOVERNOR": "Enable adaptive thermal throttling",
        "SOS_LISTENER": "Enable remote SOS lock/wipe listener",
        "PROTOCOL_A3": "Enable network fingerprinting",
        "CRYSTAL_VAULT": "Enable encrypted file vault",
        "TRANSPORT_MODE": "Enable GPS-tethered transport mode",
        "SQUAD_MESH": "Enable squad mesh BLE/UWB scanning",
        "BIOMETRIC_DURESS": "Enable biometric duress detection",
        "SCORCHED_EARTH": "Enable scorched earth purge capability",
    }

    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """Check whether *flag_name* is enabled.

        Args:
            flag_name: The flag name (without the ``ABV_FLAG_`` prefix).

        Returns:
            ``True`` when the corresponding env var is ``"1"``.
        """
        return os.environ.get(f"{cls._PREFIX}{flag_name.upper()}", "0") == "1"

    @classmethod
    def enabled_flags(cls) -> Dict[str, bool]:
        """Return a dict of all known flags and their current state."""
        return {name: cls.is_enabled(name) for name in cls.KNOWN_FLAGS}

    @classmethod
    def summary(cls) -> str:
        """Return a human-readable summary of flag states."""
        lines = []
        for name, desc in cls.KNOWN_FLAGS.items():
            state = "ON" if cls.is_enabled(name) else "OFF"
            lines.append(f"  [{state:>3}] {name}: {desc}")
        return "\n".join(lines)
