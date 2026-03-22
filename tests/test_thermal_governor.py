"""Tests for the ABV Fortress Thermal Governor."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure test env vars are set before importing modules
os.environ.setdefault("ABV_LOG_LEVEL", "WARNING")

from src.public.fortress.thermal_governor import (
    ThermalGovernor,
    ThermalReading,
    ThermalZone,
    ThrottleAction,
)


class TestThermalZoneClassification(unittest.TestCase):
    """Test thermal zone classification logic."""

    def setUp(self) -> None:
        self.governor = ThermalGovernor()

    def test_nominal_zone(self) -> None:
        self.assertEqual(self.governor.classify_zone(50.0), ThermalZone.NOMINAL)
        self.assertEqual(self.governor.classify_zone(0.0), ThermalZone.NOMINAL)
        self.assertEqual(self.governor.classify_zone(69.9), ThermalZone.NOMINAL)

    def test_elevated_zone(self) -> None:
        self.assertEqual(self.governor.classify_zone(70.0), ThermalZone.ELEVATED)
        self.assertEqual(self.governor.classify_zone(80.0), ThermalZone.ELEVATED)
        self.assertEqual(self.governor.classify_zone(84.9), ThermalZone.ELEVATED)

    def test_throttle_zone(self) -> None:
        self.assertEqual(self.governor.classify_zone(85.0), ThermalZone.THROTTLE)
        self.assertEqual(self.governor.classify_zone(90.0), ThermalZone.THROTTLE)
        self.assertEqual(self.governor.classify_zone(94.9), ThermalZone.THROTTLE)

    def test_critical_zone(self) -> None:
        self.assertEqual(self.governor.classify_zone(95.0), ThermalZone.CRITICAL)
        self.assertEqual(self.governor.classify_zone(100.0), ThermalZone.CRITICAL)
        self.assertEqual(self.governor.classify_zone(120.0), ThermalZone.CRITICAL)


class TestThermalGovernorCallbacks(unittest.TestCase):
    """Test throttle callback registration and invocation."""

    def setUp(self) -> None:
        self.governor = ThermalGovernor()
        self.callback_calls: list[ThrottleAction] = []

    def _callback(self, action: ThrottleAction) -> None:
        self.callback_calls.append(action)

    @patch.object(ThermalGovernor, "read_sensors")
    def test_callback_invoked_on_throttle(self, mock_sensors: MagicMock) -> None:
        mock_sensors.return_value = [
            ThermalReading(sensor_name="test/cpu", temperature=90.0),
        ]
        self.governor.register_throttle_callback(self._callback)
        actions = self.governor.evaluate()

        self.assertEqual(len(actions), 1)
        self.assertEqual(len(self.callback_calls), 1)
        self.assertEqual(self.callback_calls[0].zone, ThermalZone.THROTTLE)

    @patch.object(ThermalGovernor, "read_sensors")
    def test_no_callback_for_nominal(self, mock_sensors: MagicMock) -> None:
        mock_sensors.return_value = [
            ThermalReading(sensor_name="test/cpu", temperature=50.0),
        ]
        self.governor.register_throttle_callback(self._callback)
        actions = self.governor.evaluate()

        self.assertEqual(len(actions), 0)
        self.assertEqual(len(self.callback_calls), 0)


class TestThermalGovernorHistory(unittest.TestCase):
    """Test throttle action history tracking."""

    def setUp(self) -> None:
        self.governor = ThermalGovernor()

    @patch.object(ThermalGovernor, "read_sensors")
    def test_history_accumulated(self, mock_sensors: MagicMock) -> None:
        mock_sensors.return_value = [
            ThermalReading(sensor_name="test/gpu", temperature=92.0),
        ]
        self.governor.evaluate()
        self.governor.evaluate()

        self.assertEqual(len(self.governor.history), 2)

    def test_initial_state(self) -> None:
        self.assertFalse(self.governor.is_running)
        self.assertEqual(len(self.governor.history), 0)


class TestThermalGovernorStop(unittest.TestCase):
    """Test stop signaling."""

    def test_stop_sets_flag(self) -> None:
        governor = ThermalGovernor()
        governor._running = True
        governor.stop()
        self.assertFalse(governor.is_running)


if __name__ == "__main__":
    unittest.main()
