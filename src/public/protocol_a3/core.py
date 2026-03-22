"""ABV Protocol-A3 — Network Environment Fingerprinting.

Detects the current network environment (Home, Office, Transit, Unknown)
by analyzing SSID, gateway MAC, public IP geolocation, and VPN/mesh
connectivity status.
"""

from __future__ import annotations

import os
import socket
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

import requests

from src.public.common.logging_utils import get_logger
from src.public.common.config import get_config

logger = get_logger("protocol_a3.core")


class Environment(Enum):
    """Classified network environment."""
    HOME = "home"
    OFFICE = "office"
    TRANSIT = "transit"
    UNKNOWN = "unknown"


@dataclass
class NetworkFingerprint:
    """Snapshot of the current network environment."""
    ssid: Optional[str] = None
    gateway_mac: Optional[str] = None
    gateway_ip: Optional[str] = None
    public_ip: Optional[str] = None
    geo_country: Optional[str] = None
    geo_city: Optional[str] = None
    vpn_active: bool = False
    mesh_active: bool = False
    hostname: str = field(default_factory=socket.gethostname)
    machine_id: str = field(default_factory=lambda: str(uuid.getnode()))


class ProtocolA3:
    """Network environment fingerprinting and classification engine.

    Gathers local network metadata and classifies the operating
    environment so that downstream modules can adapt their behavior.
    """

    # Known-safe SSIDs and gateway MACs (configured at deploy time)
    KNOWN_HOME_SSIDS: List[str] = []
    KNOWN_OFFICE_SSIDS: List[str] = []

    def __init__(self) -> None:
        cfg = get_config()
        self._vpn_endpoint: str = cfg.vpn_mesh_endpoint
        self._last_fingerprint: Optional[NetworkFingerprint] = None
        self._environment: Environment = Environment.UNKNOWN
        self._on_env_change: List[Callable[[Environment, Environment], None]] = []

        # Load known SSIDs from environment
        home_ssids = os.environ.get("ABV_HOME_SSIDS", "")
        office_ssids = os.environ.get("ABV_OFFICE_SSIDS", "")
        if home_ssids:
            self.KNOWN_HOME_SSIDS = [s.strip() for s in home_ssids.split(",")]
        if office_ssids:
            self.KNOWN_OFFICE_SSIDS = [s.strip() for s in office_ssids.split(",")]

        # BEGIN_PRIVATE
        # Extension hook: Protocol-A3 DCM (Defensive Countermeasures) attaches here
        self._private_dcm: Optional[Callable[["ProtocolA3", NetworkFingerprint], None]] = None
        # END_PRIVATE

    def register_env_change_callback(
        self, cb: Callable[[Environment, Environment], None]
    ) -> None:
        """Register a callback for environment transitions."""
        self._on_env_change.append(cb)

    def scan_ssid(self) -> Optional[str]:
        """Attempt to read the currently connected SSID (Linux only)."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if line.startswith("yes:"):
                    return line.split(":", 1)[1]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("SSID scan unavailable (nmcli not found or timed out)")
        return None

    def get_gateway_mac(self) -> Optional[str]:
        """Attempt to read the default gateway MAC address (Linux ARP table)."""
        try:
            result = subprocess.run(
                ["ip", "neigh", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            parts = result.stdout.strip().split()
            # Look for a MAC-address-like token
            for part in parts:
                if len(part) == 17 and part.count(":") == 5:
                    return part.upper()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("Gateway MAC lookup unavailable")
        return None

    def get_public_ip_geo(self) -> Dict[str, Optional[str]]:
        """Fetch public IP and rough geolocation via a free API."""
        try:
            resp = requests.get("https://ipinfo.io/json", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return {
                "public_ip": data.get("ip"),
                "geo_country": data.get("country"),
                "geo_city": data.get("city"),
            }
        except requests.RequestException:
            logger.debug("Public IP geo lookup failed")
            return {"public_ip": None, "geo_country": None, "geo_city": None}

    def check_vpn_active(self) -> bool:
        """Heuristic VPN detection: check for tun/wg interfaces."""
        try:
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.lower()
            return any(iface in output for iface in ("tun0", "wg0", "wg1", "tailscale"))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check_mesh_active(self) -> bool:
        """Check whether the mesh VPN endpoint is reachable."""
        if not self._vpn_endpoint:
            return False
        try:
            resp = requests.get(self._vpn_endpoint, timeout=3)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def fingerprint(self) -> NetworkFingerprint:
        """Capture a full network fingerprint."""
        geo = self.get_public_ip_geo()
        fp = NetworkFingerprint(
            ssid=self.scan_ssid(),
            gateway_mac=self.get_gateway_mac(),
            public_ip=geo["public_ip"],
            geo_country=geo["geo_country"],
            geo_city=geo["geo_city"],
            vpn_active=self.check_vpn_active(),
            mesh_active=self.check_mesh_active(),
        )
        self._last_fingerprint = fp

        # BEGIN_PRIVATE
        # Private DCM hook — run defensive countermeasure analysis
        if self._private_dcm is not None:
            self._private_dcm(self, fp)
        # END_PRIVATE

        return fp

    def classify(self, fp: Optional[NetworkFingerprint] = None) -> Environment:
        """Classify the current environment from a fingerprint.

        Args:
            fp: A :class:`NetworkFingerprint`. If ``None``, a fresh one is captured.

        Returns:
            The classified :class:`Environment`.
        """
        if fp is None:
            fp = self.fingerprint()

        previous = self._environment

        if fp.ssid and fp.ssid in self.KNOWN_HOME_SSIDS:
            new_env = Environment.HOME
        elif fp.ssid and fp.ssid in self.KNOWN_OFFICE_SSIDS:
            new_env = Environment.OFFICE
        elif fp.vpn_active or fp.mesh_active:
            new_env = Environment.TRANSIT
        elif fp.ssid is None and fp.public_ip is None:
            new_env = Environment.UNKNOWN
        else:
            new_env = Environment.UNKNOWN

        self._environment = new_env

        if new_env != previous:
            logger.info("Environment changed: %s -> %s", previous.value, new_env.value)
            for cb in self._on_env_change:
                try:
                    cb(previous, new_env)
                except Exception:
                    logger.exception("Environment change callback error")

        return new_env

    @property
    def last_fingerprint(self) -> Optional[NetworkFingerprint]:
        """Return the most recent fingerprint."""
        return self._last_fingerprint

    @property
    def environment(self) -> Environment:
        """Return the current classified environment."""
        return self._environment
