"""Tests for the daily gas consumption schedule.

The fetch must happen once per day at a fixed local time, not on a rolling
24-hour cycle, so the hour does not drift with Home Assistant restarts.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
import sys
import unittest
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "custom_components.rinnai"


def _install_stubs() -> None:
    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = custom_components

    package = ModuleType(PACKAGE)
    package.__path__ = [str(ROOT / "custom_components" / "rinnai")]
    sys.modules[PACKAGE] = package

    for name in (
        "homeassistant",
        "homeassistant.core",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.util",
        "homeassistant.util.dt",
    ):
        sys.modules.setdefault(name, ModuleType(name))

    core = sys.modules["homeassistant.core"]
    core.HomeAssistant = object
    core.callback = lambda func: func
    sys.modules["homeassistant.exceptions"].HomeAssistantError = Exception
    sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = object

    dt_module = sys.modules["homeassistant.util.dt"]
    dt_module.now = lambda: datetime.datetime.now()

    aiohttp = ModuleType("aiohttp")
    aiohttp.ClientError = Exception
    sys.modules["aiohttp"] = aiohttp

    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: None
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    mqtt = ModuleType(f"{PACKAGE}.mqtt_client")

    class _Stub:
        def __init__(self, *args, **kwargs):
            self.connected = False

    mqtt.RinnaiMQTTClient = _Stub
    sys.modules[f"{PACKAGE}.mqtt_client"] = mqtt


def load_coordinator():
    _install_stubs()
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.coordinator",
        ROOT / "custom_components" / "rinnai" / "coordinator.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GasScheduleTest(unittest.TestCase):
    """Exercise the window calculation directly."""

    def setUp(self):
        self.module = load_coordinator()
        # Keep the assertion independent of the shipped default.
        self.module.GAS_FETCH_TIME = "04:10"
        self.module.GAS_FETCH_CATCHUP = 6 * 3600

        class _Client:
            def register_state_listener(self, cb):
                pass

        self.coordinator = self.module.RinnaiCoordinator.__new__(
            self.module.RinnaiCoordinator
        )
        self.coordinator._last_gas_update = {}
        self.coordinator._gas_fail_count = {}

    def _window(self, when: str):
        ts = datetime.datetime.fromisoformat(when)
        return self.coordinator._gas_window_start(ts)

    def test_window_is_todays_time_after_the_hour(self):
        w = self._window("2026-10-22T04:10:00")
        self.assertEqual(w, datetime.datetime(2026, 10, 22, 4, 10))

        w = self._window("2026-10-22T05:00:00")
        self.assertEqual(w, datetime.datetime(2026, 10, 22, 4, 10))

    def test_before_the_hour_returns_todays_upcoming_window(self):
        """03:00 is outside yesterday's grace, so nothing is pending yet."""
        w = self._window("2026-10-22T03:00:00")
        self.assertEqual(w, datetime.datetime(2026, 10, 22, 4, 10))

    def test_yesterday_is_caught_up_inside_its_grace(self):
        """08:00 is within 6 h of today 04:10, so today's window is pending."""
        w = self._window("2026-10-22T08:00:00")
        self.assertEqual(w, datetime.datetime(2026, 10, 22, 4, 10))

    def test_before_hour_outside_grace_returns_todays_upcoming_window(self):
        """02:00 is 21.8 h past yesterday 04:10: that window is gone."""
        w = self._window("2026-10-22T02:00:00")
        self.assertEqual(w, datetime.datetime(2026, 10, 22, 4, 10))

    def test_window_rolls_forward_after_the_catchup_window(self):
        """A missed morning must not retry all day."""
        w = self._window("2026-10-22T12:00:00")
        self.assertEqual(w, datetime.datetime(2026, 10, 23, 4, 10))

    def test_catchup_still_uses_todays_window(self):
        w = self._window("2026-10-22T09:30:00")  # within 6 h of 04:10
        self.assertEqual(w, datetime.datetime(2026, 10, 22, 4, 10))


class GasDueLogicTest(unittest.TestCase):
    """A window is fetched once, then not again."""

    def setUp(self):
        self.module = load_coordinator()
        self.module.GAS_FETCH_TIME = "04:10"
        self.module.GAS_FETCH_CATCHUP = 6 * 3600
        self.coordinator = self.module.RinnaiCoordinator.__new__(
            self.module.RinnaiCoordinator
        )
        self.coordinator._last_gas_update = {}
        self.coordinator._gas_fail_count = {}

    def _patch_now(self, when: str):
        fixed = datetime.datetime.fromisoformat(when)
        self.module.dt_util.now = lambda: fixed
        return fixed.timestamp()

    def test_due_once_per_window(self):
        now = self._patch_now("2026-10-22T04:15:00")
        self.assertTrue(self.coordinator._gas_is_due("dev", now))

        window = self.coordinator._gas_window_start(datetime.datetime(2026, 10, 22, 4, 15))
        self.coordinator._last_gas_update["dev"] = window.timestamp()

        # Later in the same window: no second fetch.
        now2 = self._patch_now("2026-10-22T09:00:00")
        self.assertFalse(self.coordinator._gas_is_due("dev", now2))

    def test_not_due_before_the_hour_when_already_run(self):
        """After yesterday's run, 02:00 waits for today's window."""
        window = self.coordinator._gas_window_start(
            datetime.datetime(2026, 10, 21, 4, 10)
        )
        self.coordinator._last_gas_update["dev"] = window.timestamp()
        now = self._patch_now("2026-10-22T02:00:00")
        self.assertFalse(self.coordinator._gas_is_due("dev", now))

    def test_failure_backs_off_a_whole_day(self):
        now = self._patch_now("2026-10-22T04:15:00")
        self.coordinator._gas_fail_count["dev"] = 1
        # First backoff is one day, so the same window must be skipped.
        self.assertFalse(self.coordinator._gas_is_due("dev", now))


if __name__ == "__main__":
    unittest.main()
