"""Tests for ABV Protocol-A3 network environment fingerprinting."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ABV_LOG_LEVEL", "WARNING")
os.environ["ABV_HOME_SSIDS"] = "HomeWiFi,HomeLAN"
os.environ["ABV_OFFICE_SSIDS"] = "CorpNet"

from src.public.protocol_a3.core import Environment, NetworkFingerprint, ProtocolA3


class TestEnvironmentClassification(unittest.TestCase):
    """Test network environment classification logic."""

    def setUp(self) -> None:
        self.proto = ProtocolA3()

    def test_home_ssid(self) -> None:
        fp = NetworkFingerprint(ssid="HomeWiFi", vpn_active=False)
        env = self.proto.classify(fp)
        self.assertEqual(env, Environment.HOME)

    def test_office_ssid(self) -> None:
        fp = NetworkFingerprint(ssid="CorpNet", vpn_active=False)
        env = self.proto.classify(fp)
        self.assertEqual(env, Environment.OFFICE)

    def test_transit_vpn(self) -> None:
        fp = NetworkFingerprint(ssid="Airport_WiFi", vpn_active=True)
        env = self.proto.classify(fp)
        self.assertEqual(env, Environment.TRANSIT)

    def test_transit_mesh(self) -> None:
        fp = NetworkFingerprint(ssid="CafeNet", mesh_active=True)
        env = self.proto.classify(fp)
        self.assertEqual(env, Environment.TRANSIT)

    def test_unknown_no_network(self) -> None:
        fp = NetworkFingerprint(ssid=None, public_ip=None)
        env = self.proto.classify(fp)
        self.assertEqual(env, Environment.UNKNOWN)

    def test_unknown_ssid(self) -> None:
        fp = NetworkFingerprint(ssid="RandomCafe", vpn_active=False, public_ip="1.2.3.4")
        env = self.proto.classify(fp)
        self.assertEqual(env, Environment.UNKNOWN)


class TestEnvironmentChangeCallbacks(unittest.TestCase):
    """Test environment change callback mechanism."""

    def setUp(self) -> None:
        self.proto = ProtocolA3()
        self.transitions: list[tuple] = []

    def _on_change(self, old: Environment, new: Environment) -> None:
        self.transitions.append((old, new))

    def test_callback_on_transition(self) -> None:
        self.proto.register_env_change_callback(self._on_change)

        fp_home = NetworkFingerprint(ssid="HomeWiFi")
        self.proto.classify(fp_home)

        fp_transit = NetworkFingerprint(ssid="Airport", vpn_active=True)
        self.proto.classify(fp_transit)

        # UNKNOWN -> HOME, then HOME -> TRANSIT
        self.assertEqual(len(self.transitions), 2)
        self.assertEqual(self.transitions[0], (Environment.UNKNOWN, Environment.HOME))
        self.assertEqual(self.transitions[1], (Environment.HOME, Environment.TRANSIT))

    def test_no_callback_same_environment(self) -> None:
        self.proto.register_env_change_callback(self._on_change)

        fp = NetworkFingerprint(ssid="HomeWiFi")
        self.proto.classify(fp)
        initial_count = len(self.transitions)

        self.proto.classify(fp)  # Same environment
        self.assertEqual(len(self.transitions), initial_count)


class TestNetworkFingerprint(unittest.TestCase):
    """Test NetworkFingerprint data structure."""

    def test_default_values(self) -> None:
        fp = NetworkFingerprint()
        self.assertIsNone(fp.ssid)
        self.assertIsNone(fp.public_ip)
        self.assertFalse(fp.vpn_active)
        self.assertFalse(fp.mesh_active)
        self.assertIsNotNone(fp.hostname)
        self.assertIsNotNone(fp.machine_id)


class TestProtocolA3Properties(unittest.TestCase):
    """Test Protocol-A3 property accessors."""

    def test_initial_environment(self) -> None:
        proto = ProtocolA3()
        self.assertEqual(proto.environment, Environment.UNKNOWN)
        self.assertIsNone(proto.last_fingerprint)


if __name__ == "__main__":
    unittest.main()
