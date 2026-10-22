"""Regression tests for Rinnai value parsing in the coordinator state model."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_const_module():
    spec = importlib.util.spec_from_file_location(
        "rinnai_const_under_test",
        ROOT / "custom_components" / "rinnai" / "const.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RinnaiValueParsingTest(unittest.TestCase):
    """The appliance mixes hex counters and decimal timestamps."""

    def setUp(self):
        self.const = load_const_module()

    def test_hex_counter_is_parsed_as_hex(self):
        self.assertEqual(self.const.parse_hex_int("04B6"), 1206)
        self.assertEqual(self.const.parse_hex_int("069A"), 1690)

    def test_digit_only_hex_counter_is_not_read_as_decimal(self):
        """0252 is 594 in hex; reading it as 252 would be wrong."""
        self.assertEqual(self.const.parse_hex_int("0252"), 594)

    def test_decimal_values_stay_exact(self):
        # Parsing these as hex produced absurd integers historically.
        self.assertEqual(self.const.parse_decimal_int("1792624032883"), 1792624032883)
        self.assertEqual(self.const.parse_decimal_int("422804"), 422804)

    def test_auto_parse_uses_letters_to_detect_hex(self):
        self.assertEqual(self.const.parse_auto_int("069A"), 1690)
        self.assertEqual(self.const.parse_auto_int("1792624032883"), 1792624032883)

    def test_parsers_tolerate_missing_values(self):
        for parser in (
            self.const.parse_hex_int,
            self.const.parse_decimal_int,
            self.const.parse_auto_int,
        ):
            for value in (None, "", "   "):
                self.assertIsNone(parser(value))

    def test_timestamp_is_not_oversized_after_auto_parse(self):
        """A mangled timestamp used to reach 4000+ digits and break HA state."""
        parsed = self.const.parse_auto_int("1792624032883")
        self.assertEqual(len(str(parsed)), 13)


class OperationModeDecodingTest(unittest.TestCase):
    """Bit positions confirmed against live readings, not app helpers.

    Values captured from a REB-A2747FF-CH while switching modes in Home
    Assistant. These pin the encoding so a refactor cannot silently break
    mode detection again -- rapid_heating was previously mapped to bit 24
    (0x01000000), which never matched this hardware.
    """

    MODES = {
        "42280C": ("standby", set()),
        "432804": ("normal", {"heating_enabled"}),
        "C32800": ("outdoor", {"heating_enabled", "outdoor_mode"}),
        "432904": ("rapid", {"heating_enabled", "rapid_heating"}),
    }

    def setUp(self):
        self.const = load_const_module()

    def test_mode_keys(self):
        for raw, (expected_mode, _) in self.MODES.items():
            mode, _flags = self.const.parse_reb_operation_mode(raw)
            self.assertEqual(mode, expected_mode, f"operationMode {raw}")

    def test_expected_flags_are_set(self):
        for raw, (_mode, expected_flags) in self.MODES.items():
            _mode, flags = self.const.parse_reb_operation_mode(raw)
            for name in expected_flags:
                self.assertTrue(flags.get(name), f"{raw} should set {name}")

    def test_rapid_heating_is_bit_8(self):
        """Normal 432804 and rapid 432904 differ by exactly 0x000100."""
        normal = int("432804", 16)
        rapid = int("432904", 16)
        self.assertEqual(normal ^ rapid, self.const.REB_OPERATION_MODE_FLAGS["rapid_heating"])

    def test_outdoor_and_rapid_are_not_confused(self):
        _m, outdoor_flags = self.const.parse_reb_operation_mode("C32800")
        self.assertTrue(outdoor_flags["outdoor_mode"])
        self.assertFalse(outdoor_flags["rapid_heating"])

        _m, rapid_flags = self.const.parse_reb_operation_mode("432904")
        self.assertTrue(rapid_flags["rapid_heating"])
        self.assertFalse(rapid_flags["outdoor_mode"])


class CoordinatorConversionTest(unittest.TestCase):
    """Converting a value must not mutate the shared raw payload.

    Writing the parsed integer back into raw_data made every coordinator tick
    re-parse its own output, so 04B6 grew as 1206 -> 4614 -> 17940 -> ... until
    Home Assistant failed to convert the state.
    """

    def _load_state_class(self):
        """Import RinnaiDeviceState with Home Assistant stubbed out."""
        from types import ModuleType

        package = "custom_components.rinnai"

        custom_components = ModuleType("custom_components")
        custom_components.__path__ = [str(ROOT / "custom_components")]
        sys.modules["custom_components"] = custom_components

        rinnai_package = ModuleType(package)
        rinnai_package.__path__ = [str(ROOT / "custom_components" / "rinnai")]
        sys.modules[package] = rinnai_package

        for name in ("homeassistant", "homeassistant.core",
                     "homeassistant.exceptions", "homeassistant.helpers",
                     "homeassistant.helpers.update_coordinator",
                     "homeassistant.util", "homeassistant.util.dt"):
            sys.modules.setdefault(name, ModuleType(name))

        core = sys.modules["homeassistant.core"]
        core.HomeAssistant = object
        core.callback = lambda func: func
        exc = sys.modules["homeassistant.exceptions"]
        exc.HomeAssistantError = Exception
        uc = sys.modules["homeassistant.helpers.update_coordinator"]
        uc.DataUpdateCoordinator = object
        dt_module = sys.modules["homeassistant.util.dt"]
        dt_module.now = lambda: __import__("datetime").datetime.now()

        # client.py pulls in aiohttp and the MQTT client; stub them so only the
        # state model is exercised.
        aiohttp = ModuleType("aiohttp")
        aiohttp.ClientError = Exception
        sys.modules["aiohttp"] = aiohttp

        aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
        aiohttp_client.async_get_clientsession = lambda hass: None
        sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

        mqtt_module = ModuleType(f"{package}.mqtt_client")

        class _StubMQTTClient:
            def __init__(self, *args, **kwargs):
                self.connected = False

        mqtt_module.RinnaiMQTTClient = _StubMQTTClient
        sys.modules[f"{package}.mqtt_client"] = mqtt_module

        spec = importlib.util.spec_from_file_location(
            f"{package}.coordinator",
            ROOT / "custom_components" / "rinnai" / "coordinator.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_repeated_updates_do_not_inflate_counters(self):
        """Re-parsing the same payload must be stable, not exponential.

        The coordinator passes the *shared* client.device_states dict straight
        into update_from_api_data. The old code wrote the converted int back
        into that same dict, so every tick fed its own output back in:
        04B6 -> 1206 -> 4614 -> 17940 -> ... and eventually exceeded Python's
        int-to-str digit limit inside Home Assistant.

        The payload dict is therefore reused deliberately, not copied.
        """
        module = self._load_state_class()
        state = module.RinnaiDeviceState()
        shared_payload = {"totalHeatingBurningTime": "04B6"}

        seen = []
        for _ in range(6):
            state.update_from_api_data(shared_payload)
            seen.append(state.heating_burning_time)

        self.assertEqual(
            seen,
            [1206] * 6,
            f"value inflated across updates: {seen}",
        )

    def test_other_counters_are_stable_across_updates(self):
        """Same guard for the hot water burning counter."""
        module = self._load_state_class()
        state = module.RinnaiDeviceState()
        shared_payload = {"totalHotWaterBurningTime": "0252"}

        for _ in range(4):
            state.update_from_api_data(shared_payload)

        self.assertEqual(state.hot_water_burning_time, 594)

    def test_raw_payload_keeps_original_string(self):
        module = self._load_state_class()
        state = module.RinnaiDeviceState()
        shared_payload = {"totalHeatingBurningTime": "04B6"}
        state.update_from_api_data(shared_payload)

        self.assertEqual(shared_payload["totalHeatingBurningTime"], "04B6")
        self.assertEqual(state.raw_data["totalHeatingBurningTime"], "04B6")


if __name__ == "__main__":
    unittest.main()
