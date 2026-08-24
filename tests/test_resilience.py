"""Regression tests for MQTT reconnect and offline entity resilience."""

from __future__ import annotations

import asyncio
from enum import Enum
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "custom_components.rinnai"


def reset_modules() -> None:
    for name in list(sys.modules):
        if (
            name == "custom_components"
            or name.startswith(f"{PACKAGE_NAME}.")
            or name.startswith("homeassistant")
            or name.startswith("paho")
        ):
            sys.modules.pop(name, None)


def install_rinnai_package() -> None:
    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = custom_components

    rinnai_package = ModuleType(PACKAGE_NAME)
    rinnai_package.__path__ = [str(ROOT / "custom_components" / "rinnai")]
    sys.modules[PACKAGE_NAME] = rinnai_package


def load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / relative_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakeHass:
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.tasks = []

    def async_add_executor_job(self, func, *args):
        future = self.loop.create_future()
        future.set_result(func(*args))
        return future

    def async_create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


class FakeMQTTClient:
    def __init__(self, client_id):
        self.client_id = client_id
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.reconnect_calls = 0
        self.subscribe_calls = []

    def username_pw_set(self, username, password):
        self.username = username
        self.password = password

    def tls_set(self, *args):
        return None

    def connect(self, host, port, keepalive):
        self.on_connect(self, None, None, 0)

    def reconnect(self):
        self.reconnect_calls += 1
        self.on_connect(self, None, None, 0)

    def loop_start(self):
        return None

    def disconnect(self):
        return None

    def loop_stop(self):
        return None

    def subscribe(self, topic, qos=0):
        self.subscribe_calls.append((topic, qos))

    def unsubscribe(self, topic):
        return None


def load_mqtt_module():
    reset_modules()
    install_rinnai_package()

    homeassistant_core = ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_core.callback = lambda func: func
    sys.modules["homeassistant"] = ModuleType("homeassistant")
    sys.modules["homeassistant.core"] = homeassistant_core

    paho = ModuleType("paho")
    paho_mqtt = ModuleType("paho.mqtt")
    mqtt_client_module = ModuleType("paho.mqtt.client")
    mqtt_client_module.Client = FakeMQTTClient
    mqtt_client_module.MQTT_ERR_SUCCESS = 0
    mqtt_client_module.error_string = lambda rc: f"error {rc}"
    sys.modules["paho"] = paho
    sys.modules["paho.mqtt"] = paho_mqtt
    sys.modules["paho.mqtt.client"] = mqtt_client_module

    return load_module(
        f"{PACKAGE_NAME}.mqtt_client",
        "custom_components/rinnai/mqtt_client.py",
    )


class HVACMode(Enum):
    HEAT = "heat"
    AUTO = "auto"
    DRY = "dry"
    OFF = "off"


class HVACAction(Enum):
    OFF = "off"
    HEATING = "heating"
    IDLE = "idle"


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def async_write_ha_state(self):
        return None


def load_climate_module():
    reset_modules()
    install_rinnai_package()

    climate_component = ModuleType("homeassistant.components.climate")
    climate_component.ClimateEntity = object
    climate_component.ClimateEntityFeature = SimpleNamespace(TARGET_TEMPERATURE=1)
    climate_component.HVACAction = HVACAction
    climate_component.HVACMode = HVACMode
    sys.modules["homeassistant"] = ModuleType("homeassistant")
    sys.modules["homeassistant.components"] = ModuleType("homeassistant.components")
    sys.modules["homeassistant.components.climate"] = climate_component

    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    const = ModuleType("homeassistant.const")
    const.ATTR_TEMPERATURE = "temperature"
    const.UnitOfTemperature = SimpleNamespace(CELSIUS="C")
    sys.modules["homeassistant.const"] = const

    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func
    sys.modules["homeassistant.core"] = core

    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    update_coordinator.CoordinatorEntity = FakeCoordinatorEntity
    sys.modules["homeassistant.helpers"] = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    coordinator_module = ModuleType(f"{PACKAGE_NAME}.coordinator")
    coordinator_module.RinnaiCoordinator = object
    sys.modules[f"{PACKAGE_NAME}.coordinator"] = coordinator_module

    return load_module(
        f"{PACKAGE_NAME}.climate",
        "custom_components/rinnai/climate.py",
    )


def load_coordinator_module():
    reset_modules()
    install_rinnai_package()

    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = RuntimeError
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    update_coordinator.DataUpdateCoordinator = object
    sys.modules["homeassistant"] = ModuleType("homeassistant")
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.exceptions"] = exceptions
    sys.modules["homeassistant.helpers"] = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    client_module = ModuleType(f"{PACKAGE_NAME}.client")
    client_module.RinnaiClient = object
    sys.modules[f"{PACKAGE_NAME}.client"] = client_module

    return load_module(
        f"{PACKAGE_NAME}.coordinator",
        "custom_components/rinnai/coordinator.py",
    )


class RinnaiResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_mqtt_disconnect_reconnects_and_resubscribes(self):
        mqtt_module = load_mqtt_module()
        mqtt_module._RECONNECT_DELAYS = [0]
        client = mqtt_module.RinnaiMQTTClient(FakeHass(), "user", "password")

        self.assertTrue(await client.async_connect())
        client._subscribes["rinnai/SR/01/SR/mac/inf/"] = (lambda msg: None, 1)

        client.client.on_disconnect(client.client, None, 1)
        await asyncio.sleep(0)
        await asyncio.wait_for(client.hass.tasks[-1], timeout=1)

        self.assertTrue(client.connected)
        self.assertEqual(client.client.reconnect_calls, 1)
        self.assertIn(("rinnai/SR/01/SR/mac/inf/", 1), client.client.subscribe_calls)

    def test_offline_climate_initializes_safe_off_mode(self):
        climate_module = load_climate_module()
        device = SimpleNamespace(
            online=False,
            device_name="REB",
            device_type="REB",
        )
        coordinator = SimpleNamespace(
            data={"devices": {"device-1": device}},
            get_device=lambda device_id: device,
            get_device_state=lambda device_id: None,
        )

        entity = climate_module.RinnaiHeatingClimateEntity(coordinator, "device-1")

        self.assertFalse(entity._attr_available)
        self.assertEqual(entity._attr_hvac_mode, HVACMode.OFF)
        self.assertEqual(entity._attr_hvac_action, HVACAction.OFF)
        self.assertIsNone(entity._attr_preset_mode)

    def test_mqtt_state_update_marks_device_online(self):
        coordinator_module = load_coordinator_module()
        coordinator = object.__new__(coordinator_module.RinnaiCoordinator)
        device = coordinator_module.RinnaiDevice(device_id="device-1")
        coordinator._devices = {"device-1": device}
        coordinator.client = SimpleNamespace(
            device_states={"device-1": {"operationMode": "010000"}}
        )
        coordinator.data = {
            "devices": coordinator._devices,
            "device_states": {"device-1": device.state},
        }
        coordinator.async_set_updated_data = lambda data: setattr(
            coordinator, "updated_data", data
        )

        coordinator._handle_client_state_update(
            "device-1", {"operationMode": "010000"}
        )

        self.assertTrue(device.online)
        self.assertIs(coordinator.updated_data, coordinator.data)

        coordinator._handle_client_state_update("device-1", {"_online": False})

        self.assertFalse(device.online)
