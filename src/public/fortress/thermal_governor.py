"""ABV Fortress — Thermal Governor.

Monitors CPU and GPU temperatures via ``psutil`` and applies adaptive
throttling logic optimized for Ryzen / Nvidia AI workloads.  Provides
extension hooks for private tactical thermal overrides.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

import psutil

from src.public.common.logging_utils import get_logger
from src.public.common.config import get_config

logger = get_logger("fortress.thermal")


class ThermalZone(Enum):
    """Thermal operating zones."""
    NOMINAL = "nominal"
    ELEVATED = "elevated"
    THROTTLE = "throttle"
    CRITICAL = "critical"


@dataclass
class ThermalReading:
    """A single thermal sensor reading."""
    sensor_name: str
    temperature: float
    high: Optional[float] = None
    critical: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ThrottleAction:
    """Describes a throttle action taken by the governor."""
    zone: ThermalZone
    sensor: str
    temperature: float
    action: str
    timestamp: float = field(default_factory=time.time)


class ThermalGovernor:
    """Adaptive thermal governor for CPU/GPU workloads.

    Reads system thermal sensors, classifies the operating zone, and
    invokes throttle callbacks when thresholds are exceeded.

    Thresholds (°C):
        - Nominal:  < 70
        - Elevated: 70–84
        - Throttle: 85–94
        - Critical: >= 95 (configurable via ``CPU_TEMP_CRITICAL``)
    """

    ZONE_THRESHOLDS: Dict[ThermalZone, float] = {
        ThermalZone.NOMINAL: 0.0,
        ThermalZone.ELEVATED: 70.0,
        ThermalZone.THROTTLE: 85.0,
        ThermalZone.CRITICAL: 95.0,
    }

    def __init__(self) -> None:
        cfg = get_config()
        self.cpu_critical: float = cfg.cpu_temp_critical
        self.gpu_critical: float = cfg.gpu_temp_critical
        self.poll_interval: float = cfg.thermal_poll_interval
        self._running: bool = False
        self._history: List[ThrottleAction] = []
        self._on_throttle_callbacks: List[Callable[[ThrottleAction], None]] = []

        # BEGIN_PRIVATE
        # Extension hook: private thermal overrides attach here
        self._private_override: Optional[Callable[["ThermalGovernor"], None]] = None
        # END_PRIVATE

    def register_throttle_callback(self, cb: Callable[[ThrottleAction], None]) -> None:
        """Register a callback invoked on every throttle action."""
        self._on_throttle_callbacks.append(cb)

    def read_sensors(self) -> List[ThermalReading]:
        """Read all available thermal sensors from the system."""
        readings: List[ThermalReading] = []
        try:
            temps = psutil.sensors_temperatures()
        except (AttributeError, RuntimeError):
            logger.warning("psutil.sensors_temperatures() not available on this platform")
            return readings

        for chip_name, entries in temps.items():
            for entry in entries:
                readings.append(ThermalReading(
                    sensor_name=f"{chip_name}/{entry.label or 'unknown'}",
                    temperature=entry.current,
                    high=entry.high,
                    critical=entry.critical,
                ))
        return readings

    def classify_zone(self, temp: float) -> ThermalZone:
        """Classify a temperature into a thermal zone."""
        if temp >= self.cpu_critical:
            return ThermalZone.CRITICAL
        if temp >= self.ZONE_THRESHOLDS[ThermalZone.THROTTLE]:
            return ThermalZone.THROTTLE
        if temp >= self.ZONE_THRESHOLDS[ThermalZone.ELEVATED]:
            return ThermalZone.ELEVATED
        return ThermalZone.NOMINAL

    def evaluate(self) -> List[ThrottleAction]:
        """Read sensors, classify zones, and return any throttle actions."""
        readings = self.read_sensors()
        actions: List[ThrottleAction] = []

        for reading in readings:
            zone = self.classify_zone(reading.temperature)

            if zone == ThermalZone.NOMINAL:
                continue

            action_desc = self._determine_action(zone, reading)
            action = ThrottleAction(
                zone=zone,
                sensor=reading.sensor_name,
                temperature=reading.temperature,
                action=action_desc,
            )
            actions.append(action)
            self._history.append(action)
            logger.info(
                "Thermal %s: %s at %.1f°C — %s",
                zone.value, reading.sensor_name, reading.temperature, action_desc,
            )

            for cb in self._on_throttle_callbacks:
                try:
                    cb(action)
                except Exception:
                    logger.exception("Throttle callback error")

        # BEGIN_PRIVATE
        # Private override hook — tactical thermal overrides run here
        if self._private_override is not None:
            self._private_override(self)
        # END_PRIVATE

        return actions

    def _determine_action(self, zone: ThermalZone, reading: ThermalReading) -> str:
        """Return a human-readable action description for a given zone."""
        if zone == ThermalZone.CRITICAL:
            return f"CRITICAL: Emergency throttle on {reading.sensor_name}"
        if zone == ThermalZone.THROTTLE:
            return f"THROTTLE: Reducing clock speed for {reading.sensor_name}"
        if zone == ThermalZone.ELEVATED:
            return f"ELEVATED: Increasing fan curve for {reading.sensor_name}"
        return "NOMINAL: No action required"

    def run(self) -> None:
        """Start the thermal monitoring loop (blocking)."""
        self._running = True
        logger.info("Thermal Governor started (poll=%.1fs)", self.poll_interval)
        try:
            while self._running:
                self.evaluate()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("Thermal Governor stopped by user")
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the monitoring loop to stop."""
        self._running = False
        logger.info("Thermal Governor stop requested")

    @property
    def history(self) -> List[ThrottleAction]:
        """Return the history of throttle actions taken."""
        return list(self._history)

    @property
    def is_running(self) -> bool:
        """Return whether the governor loop is active."""
        return self._running
