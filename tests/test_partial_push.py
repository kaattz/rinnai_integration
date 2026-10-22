"""Regression tests for partial MQTT pushes.

The appliance pushes a variable subset of fields: ``inf`` messages can carry a
full state or only a handful of ids. A partial push must not wipe values it did
not mention, otherwise entities flicker to "unknown" between updates.
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
    sys.modules["homeassistant.util.dt"].now = datetime.datetime.now

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


class PartialPushTest(unittest.TestCase):
    def setUp(self):
        self.module = load_coordinator()
        self.state = self.module.RinnaiDeviceState()

    def test_partial_push_keeps_previous_operation_mode(self):
        """A push without operationMode must not blank the raw value."""
        self.state.update_from_api_data({"operationMode": "432804"})
        self.assertEqual(self.state.operation_mode_raw, "432804")

        # Partial push: only burning state, no operationMode.
        self.state.update_from_api_data({"burningStateCH": "30"})

        self.assertEqual(
            self.state.operation_mode_raw,
            "432804",
            "operation_mode_raw must survive a partial push",
        )
        self.assertEqual(self.state.operation_mode, "normal")

    def test_partial_push_keeps_eco_mode(self):
        self.state.update_from_api_data({"operationMode": "422804"})  # eco on
        self.assertTrue(self.state.eco_mode)

        self.state.update_from_api_data({"waterPressure": "0730"})

        self.assertTrue(self.state.eco_mode, "eco state must survive")

    def test_new_value_still_updates(self):
        """The guard must not make the field read-only."""
        self.state.update_from_api_data({"operationMode": "422804"})
        self.assertEqual(self.state.operation_mode, "standby")

        self.state.update_from_api_data({"operationMode": "432804"})
        self.assertEqual(self.state.operation_mode_raw, "432804")
        self.assertEqual(self.state.operation_mode, "normal")

    def test_first_push_without_operation_mode_leaves_it_empty(self):
        """Before any mode is known, it stays empty rather than inventing one."""
        self.state.update_from_api_data({"waterPressure": "0730"})
        self.assertEqual(self.state.operation_mode_raw, "")

    def test_mode_name_is_never_used_as_a_bitfield(self):
        """The old fallback treated the mode name as hex and stored it.

        This is the path that produced the "unknown" entity on a live system:
        before any operationMode arrives, self.operation_mode may already hold a
        name like "normal". The old code did
        raw_data.get("operationMode", self.operation_mode) and then tried
        int("normal", 16), failed, and stored the string "normal" as the raw
        bitfield -- which is not hex, so the entity went unknown.
        """
        # Simulate a state object restored with a known mode but no raw payload
        # (what happens right after an entity rebuild).
        self.state.operation_mode = "normal"
        self.state.update_from_api_data({"waterPressure": "0730"})

        self.assertNotEqual(
            self.state.operation_mode_raw,
            "normal",
            "a mode name must never be stored as the raw bitfield",
        )
        self.assertEqual(self.state.operation_mode_raw, "")


if __name__ == "__main__":
    unittest.main()
