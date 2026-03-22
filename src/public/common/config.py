"""ABV Sovereign Stack — Shared Configuration.

Centralizes all environment-driven configuration for the Sovereign Stack.
Hardware IDs, encryption keys, and service endpoints are loaded from
environment variables to prevent secrets from leaking into source control.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class SovereignConfig:
    """Immutable configuration container for the ABV Sovereign Stack."""

    # --- Fob MAC addresses (squad mesh) ---
    fob_macs: List[str] = field(default_factory=lambda: [
        os.environ.get(f"FOB_MAC_{i}", f"00:00:00:00:00:0{i}")
        for i in range(1, 6)
    ])

    # --- TPM / Encryption ---
    tpm_secret_key: str = field(
        default_factory=lambda: os.environ.get("TPM_SECRET_KEY", "")
    )
    crystal_encryption_key: str = field(
        default_factory=lambda: os.environ.get("CRYSTAL_ENCRYPTION_KEY", "")
    )

    # --- SOS Relay ---
    sos_relay_url: str = field(
        default_factory=lambda: os.environ.get("SOS_RELAY_URL", "http://localhost:9000/sos")
    )
    sos_hmac_secret: str = field(
        default_factory=lambda: os.environ.get("SOS_HMAC_SECRET", "")
    )

    # --- Transport ---
    transport_gps_api_key: str = field(
        default_factory=lambda: os.environ.get("TRANSPORT_GPS_API_KEY", "")
    )

    # --- VPN / Mesh ---
    vpn_mesh_endpoint: str = field(
        default_factory=lambda: os.environ.get("VPN_MESH_ENDPOINT", "")
    )

    # --- Thermal ---
    cpu_temp_critical: float = field(
        default_factory=lambda: float(os.environ.get("CPU_TEMP_CRITICAL", "95"))
    )
    gpu_temp_critical: float = field(
        default_factory=lambda: float(os.environ.get("GPU_TEMP_CRITICAL", "90"))
    )
    thermal_poll_interval: float = field(
        default_factory=lambda: float(os.environ.get("THERMAL_POLL_INTERVAL", "2.0"))
    )

    # --- General ---
    build_mode: str = field(
        default_factory=lambda: os.environ.get("ABV_BUILD_MODE", "PUBLIC")
    )
    log_level: str = field(
        default_factory=lambda: os.environ.get("ABV_LOG_LEVEL", "INFO")
    )

    @property
    def is_private_build(self) -> bool:
        """Return True when running a private (tactical) build."""
        return self.build_mode.upper() == "PRIVATE"

    def validate(self) -> List[str]:
        """Return a list of configuration warnings (missing keys, etc.)."""
        warnings: List[str] = []
        if not self.tpm_secret_key:
            warnings.append("TPM_SECRET_KEY is not set")
        if not self.crystal_encryption_key:
            warnings.append("CRYSTAL_ENCRYPTION_KEY is not set")
        if not self.sos_hmac_secret:
            warnings.append("SOS_HMAC_SECRET is not set")
        return warnings


# Module-level singleton for convenience
_config: Optional[SovereignConfig] = None


def get_config() -> SovereignConfig:
    """Return the global config singleton, creating it on first call."""
    global _config
    if _config is None:
        _config = SovereignConfig()
    return _config
