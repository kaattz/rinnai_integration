"""Data update coordinator for Rinnai integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import RinnaiClient
from .const import BURNING_STATES, CODE_TO_MODE, DOMAIN, parse_reb_operation_mode, parse_switch_flag

_LOGGER = logging.getLogger(__name__)


def _convert_water_pressure(value: Any) -> float:
    """Convert hex encoded water pressure to bar."""
    if value in (None, ""):
        return 0.0
    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0.0
            converted = int(value, 16)
        else:
            converted = int(value)
    except (ValueError, TypeError):
        _LOGGER.warning("Failed to convert water pressure value: %s", value)
        return 0.0
    return round(converted / 1000.0, 3)


@dataclass
class RinnaiDeviceState:
    """Representation of a Rinnai device state with typed fields."""

    # Operation mode (e.g., winter, summer, energy saving)
    operation_mode: str = ""
    # Hot water temperature setting (target) in celsius
    hot_water_temp: int = 0
    # General heating temperature setting in celsius
    heating_temp: int = 0
    # Domestic hot water burning state (DHW)
    burning_state_dhw: str = ""
    # Central heating burning state (CH)
    burning_state_ch: str = ""
    # Temperature unit flag reported by device
    temperature_unit: str = ""
    # Water pressure unit flag reported by device
    water_pressure_unit: str = ""
    # Current water pressure in bar
    water_pressure: float = 0.0
    # Raw temperature bound values from device
    hot_water_temp_bound_raw: str = ""
    heating_temp_bound_raw: str = ""
    # Derived hot water temperature range
    hot_water_temp_min: int = 0
    hot_water_temp_max: int = 0
    # Derived heating temperature range
    heating_temp_min: int = 0
    heating_temp_max: int = 0
    eco_mode: bool | None = None

    # Raw data from device
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Field mapping between API fields and object properties
    _field_mapping: ClassVar[dict[str, tuple[str, type | None]]] = {
        "operationMode": ("operation_mode", None),
        "hotWaterTempSetting": ("hot_water_temp", None),
        "heatingTempSetting": ("heating_temp", None),
        "burningStateDHW": ("burning_state_dhw", None),
        "burningStateCH": ("burning_state_ch", None),
        "temperatureUnit": ("temperature_unit", None),
        "waterPressureUnit": ("water_pressure_unit", None),
        "waterPressure": ("water_pressure", _convert_water_pressure),
        "hotWaterTempBound": ("hot_water_temp_bound_raw", None),
        "heatingTempBound": ("heating_temp_bound_raw", None),
        "ecoMode": ("eco_mode", parse_switch_flag),
    }

    # List of fields that need hex conversion
    _hex_fields: ClassVar[list[str]] = [
        "hotWaterTempSetting",
        "heatingTempSetting",
    ]

    def update_from_api_data(self, api_data: dict[str, Any]) -> None:
        """Update state from API data."""
        # Store raw data
        self.raw_data.update(api_data)

        # Process hex values
        self._process_hex_values(api_data)

        # Update typed fields using mapping
        for api_field, (obj_field, converter) in self._field_mapping.items():
            if api_field not in api_data:
                continue

            value = api_data[api_field]
            if value in (None, ""):
                continue

            if converter:
                try:
                    converted = converter(value)
                except (ValueError, TypeError):
                    _LOGGER.warning(
                        "Failed to convert %s value '%s' to %s",
                        obj_field,
                        value,
                        converter.__name__,
                    )
                    continue
                setattr(self, obj_field, converted)
                api_data[api_field] = converted
            else:
                setattr(self, obj_field, value)

        self._apply_derived_values()

    def _process_hex_values(self, api_data: dict[str, Any]) -> None:
        """Process values that need hex conversion."""
        for field_name in self._hex_fields:
            if hex_value := api_data.get(field_name):
                try:
                    # Ensure value is string and convert from hex
                    if isinstance(hex_value, str):
                        # Add more detailed logs
                        original_value = hex_value
                        int_value = int(hex_value, 16)
                        api_data[field_name] = int_value
                        _LOGGER.debug(
                            "Converting hex value: %s: %s -> %s",
                            field_name,
                            original_value,
                            int_value,
                        )
                except ValueError:
                    _LOGGER.warning(
                        "Failed to convert hex value %s: %s", field_name, hex_value
                    )

    def _apply_derived_values(self) -> None:
        """Update derived fields such as temperature ranges."""
        bounds = self._decode_temperature_bound(self.hot_water_temp_bound_raw)
        if bounds:
            self.hot_water_temp_min, self.hot_water_temp_max = bounds
        bounds = self._decode_temperature_bound(self.heating_temp_bound_raw)
        if bounds:
            self.heating_temp_min, self.heating_temp_max = bounds

        operation_raw = self.raw_data.get("operationMode", self.operation_mode)
        mode_key, flags = parse_reb_operation_mode(operation_raw)
        if operation_raw not in (None, ""):
            if isinstance(operation_raw, str):
                self.raw_data["operationModeRaw"] = operation_raw
            else:
                try:
                    self.raw_data["operationModeRaw"] = f"{int(operation_raw):06X}"
                except (TypeError, ValueError):
                    self.raw_data["operationModeRaw"] = str(operation_raw)
        if flags:
            self.raw_data["operationModeFlags"] = flags
            if "eco_mode" in flags:
                self.eco_mode = flags["eco_mode"]
        if mode_key:
            self.operation_mode = mode_key

    @staticmethod
    def _decode_temperature_bound(bound: str | int | None) -> tuple[int, int] | None:
        """Decode Rinnai two-byte bound format (high byte max, low byte min)."""
        if bound in (None, ""):
            return None
        if isinstance(bound, int):
            value = f"{bound:04X}"
        elif isinstance(bound, str):
            value = bound.strip()
            if len(value) < 4:
                return None
            value = value[-4:]
        else:
            return None
        try:
            upper = int(value[:2], 16)
            lower = int(value[2:4], 16)
        except ValueError:
            return None
        if lower > upper:
            lower, upper = upper, lower
        return lower, upper




@dataclass
class RinnaiDevice:
    """Representation of a Rinnai device with typed fields."""

    device_id: str
    device_name: str = "Rinnai Device"
    device_type: str = "Unknown"
    auth_code: str = "FFFF"
    online: bool = False

    # Device state information
    state: RinnaiDeviceState = field(default_factory=RinnaiDeviceState)

    # Raw data from API
    raw_data: dict[str, Any] = field(default_factory=dict)

    def update_from_api_data(self, api_data: dict[str, Any]) -> None:
        """Update device from API data."""
        # Store raw data
        self.raw_data.update(api_data)

        # Update basic device properties
        self.device_name = api_data.get("name", self.device_name)
        self.device_type = api_data.get("deviceType", self.device_type)
        self.auth_code = api_data.get("authCode", self.auth_code)

        # Update online status
        online_status = api_data.get("online")
        if online_status is not None:
            self.online = online_status == "1"


class RinnaiCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Rinnai devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RinnaiClient,
        update_interval: int = 300,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.client.register_state_listener(self._handle_client_state_update)
        self._first_update = True
        self._devices: dict[str, RinnaiDevice] = {}
        self._last_http_update: dict[str, float] = {}
        self.data = {"devices": {}, "device_states": {}}

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""

        def handle_error(msg: str) -> None:
            """Handle error in data update."""
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

        try:
            # Ensure we're logged in (needed for both HTTP and potentially MQTT operations)
            if not await self.client.login():
                handle_error("Failed to login to Rinnai API")

            # Only fetch devices during first update or when devices list is empty
            if self._first_update or not self.client.devices:
                _LOGGER.debug("Performing initial/full HTTP update for devices")
                if not await self.client.fetch_devices():
                    _LOGGER.warning("Failed to fetch devices from HTTP API")

                for device_id in self.client.devices:
                    _LOGGER.debug("Fetching initial state for device: %s", device_id)
                    if not await self.client.fetch_device_state(device_id):
                        _LOGGER.warning(
                            "Failed to fetch state for device: %s", device_id
                        )
                    else:
                        self._last_http_update[device_id] = time.time()

                self._first_update = False

                # Process initial device data
                self._process_devices_data()
            else:
                _LOGGER.debug("Skipping HTTP device fetch, using MQTT data only")

                current_time = time.time()
                for device_id in self.client.devices:
                    device_state = self.client.device_states.get(device_id, {})
                    if (
                        not device_state
                        or getattr(self, "_last_http_update", {}).get(device_id, 0)
                        < current_time - 3600
                    ):
                        _LOGGER.debug(
                            "Fetching HTTP state update for device: %s", device_id
                        )
                        if await self.client.fetch_device_state(device_id):
                            self._last_http_update[device_id] = current_time

                # MQTT updates happen independently in the client through subscriptions
                # Process any state updates from MQTT
                self._process_device_states()

            self._log_device_states()

        except (ValueError, TypeError, KeyError) as err:
            handle_error(f"Error updating Rinnai data: {err}")

        # Return structured data for Home Assistant entities
        return {
            "devices": self._devices,
            "device_states": {
                device_id: device.state for device_id, device in self._devices.items()
            },
            # Also include raw data for backward compatibility
            "raw_devices": self.client.devices,
            "raw_device_states": self.client.device_states,
        }

    @callback
    def _handle_client_state_update(
        self, device_id: str, state_data: dict[str, Any]
    ) -> None:
        """Handle state updates pushed from the client."""
        device = self._devices.get(device_id)
        if device:
            if "_online" in state_data:
                device.online = self._coerce_online_status(state_data["_online"])
                self.async_set_updated_data(self.data)
                return
            if state_data and not device.online:
                _LOGGER.info(
                    "Device %s is sending MQTT updates, marking online", device_id
                )
                device.online = True

        self._process_device_states()
        self.async_set_updated_data(self.data)

    @staticmethod
    def _coerce_online_status(value: Any) -> bool:
        """Convert MQTT online markers into a boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "online", "on"}:
                return True
            if normalized in {"0", "false", "offline", "off"}:
                return False
        return bool(value)

    def _process_devices_data(self) -> None:
        """Process devices data from client into structured format."""
        for device_id, device_data in self.client.devices.items():
            # Create device if it doesn't exist
            if device_id not in self._devices:
                self._devices[device_id] = RinnaiDevice(device_id=device_id)

            # Update device with API data
            self._devices[device_id].update_from_api_data(device_data)

            # Process initial state if available
            if device_id in self.client.device_states:
                self._devices[device_id].state.update_from_api_data(
                    self.client.device_states[device_id]
                )

    def _process_device_states(self) -> None:
        """Process device states from client into structured format."""
        for device_id, state_data in self.client.device_states.items():
            if device_id in self._devices:
                _LOGGER.debug(
                    "Received state data from client: %s: %s", device_id, state_data
                )

                self._devices[device_id].state.update_from_api_data(state_data)

            else:
                _LOGGER.warning(
                    "Received state for unknown device %s, fetching device info",
                    device_id,
                )
                # This shouldn't normally happen, but if it does, we'll process devices again
                self._process_devices_data()

    def process_device_states(self) -> None:
        """Process device states from client (public method)."""
        self._process_device_states()
        # update data to coordinator
        self.async_set_updated_data(self.data)

    async def async_send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        """Send command to a device."""

        result = await self.client.send_command(device_id, command)

        # If command was successful, update our internal state anticipating the change
        # This improves responsiveness of the UI before the next MQTT update
        if result and device_id in self._devices:
            device = self._devices[device_id]
            old_state = device.state

            old_operation_mode = old_state.operation_mode if old_state else "Unknown"

            self._devices[device_id].state.update_from_api_data(command)

            # update data to coordinator
            self.async_set_updated_data(self.data)

            self.data["device_states"][device_id] = self._devices[device_id].state

            device = self._devices[device_id]
            state = device.state
            _LOGGER.info("===== Command Post-State =====")
            _LOGGER.info("Device: %s (%s)", device.device_name, device_id)

            new_operation_mode = state.operation_mode
            if old_operation_mode != new_operation_mode:
                _LOGGER.info(
                    "  Operation Mode Change: %s -> %s",
                    old_operation_mode,
                    new_operation_mode,
                )
            else:
                _LOGGER.info(
                    "  Operation Mode: %s",
                    new_operation_mode,
                )

            for cmd_key, cmd_value in command.items():
                current_value = state.raw_data.get(cmd_key, "Not Set")
                _LOGGER.info("  %s: %s -> %s", cmd_key, cmd_value, current_value)

            _LOGGER.info("======================")
        else:
            _LOGGER.warning("Command Send Failed: %s", command)

        return result

    def get_device(self, device_id: str) -> RinnaiDevice | None:
        """Get device by ID, with graceful handling of missing devices."""
        return self._devices.get(device_id)

    def get_device_state(self, device_id: str) -> RinnaiDeviceState | None:
        """Get device state by ID, with graceful handling of missing devices."""
        device = self.get_device(device_id)
        return device.state if device else None

    def _log_device_states(self) -> None:
        """Log detailed state information for all devices."""
        for device_id, device in self._devices.items():
            state = device.state
            _LOGGER.info("===== Device Status Sync =====")
            _LOGGER.info(
                "Device: %s (%s), Online: %s",
                device.device_name,
                device_id,
                device.online,
            )
            _LOGGER.info(
                "Type: %s, Auth Code: %s",
                device.device_type,
                device.auth_code,
            )

            mode_name = CODE_TO_MODE.get(state.operation_mode, state.operation_mode)
            _LOGGER.info("Operation Mode: %s", mode_name)
            _LOGGER.info("Hot Water Temperature Setting: %s C", state.hot_water_temp)
            _LOGGER.info("Heating Temperature Setting: %s C", state.heating_temp)

            if state.hot_water_temp_min or state.hot_water_temp_max:
                _LOGGER.info(
                    "Hot Water Temperature Range: %s-%s C",
                    state.hot_water_temp_min,
                    state.hot_water_temp_max,
                )
            if state.heating_temp_min or state.heating_temp_max:
                _LOGGER.info(
                    "Heating Temperature Range: %s-%s C",
                    state.heating_temp_min,
                    state.heating_temp_max,
                )

            if state.burning_state_dhw:
                _LOGGER.info(
                    "DHW Burning State: %s",
                    BURNING_STATES.get(state.burning_state_dhw, state.burning_state_dhw),
                )
            if state.burning_state_ch:
                _LOGGER.info(
                    "CH Burning State: %s",
                    BURNING_STATES.get(state.burning_state_ch, state.burning_state_ch),
                )

            if state.water_pressure:
                _LOGGER.info("Water Pressure: %.3f bar", state.water_pressure)

            _LOGGER.debug("Device Raw Data: %s", device.raw_data)
            _LOGGER.debug("State Raw Data: %s", state.raw_data)
            _LOGGER.info("===========================")
