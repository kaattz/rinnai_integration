"""Support for Rinnai heating climate control."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CODE_TO_MODE, DOMAIN, HEATING_MODES, MAX_TEMP, MIN_TEMP, TEMP_STEP
from .mode_utils import async_apply_heating_mode
from .coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)


MODE_TO_HVAC = {
    "normal": HVACMode.HEAT,
    "rapid": HVACMode.AUTO,
    "outdoor": HVACMode.DRY,
    "standby": HVACMode.OFF,
}

HVAC_TO_MODE = {value: key for key, value in MODE_TO_HVAC.items()}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rinnai climate based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RinnaiHeatingClimateEntity(coordinator, device_id)
        for device_id in coordinator.data["devices"]
    ]

    async_add_entities(entities)


class RinnaiHeatingClimateEntity(CoordinatorEntity, ClimateEntity):
    """Representation of a Rinnai heating climate entity."""

    coordinator: RinnaiCoordinator

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._device_id = device_id

        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = MIN_TEMP
        self._attr_max_temp = MAX_TEMP
        self._attr_target_temperature_step = TEMP_STEP

        self._attr_hvac_modes = [
            HVACMode.HEAT,
            HVACMode.AUTO,
            HVACMode.DRY,
            HVACMode.OFF,
        ]

        # Use has_entity_name flag to enable proper translation
        self._attr_has_entity_name = True

        self._current_mode = "standby"

        self._update_attributes()

    @property
    def _device(self):
        """Get the device object."""
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        """Get the device state object."""
        return self.coordinator.get_device_state(self._device_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Update entity attributes based on coordinator data."""
        device = self._device
        if not device:
            self._attr_available = False
            _LOGGER.debug("Heating device not available")
            return

        self._attr_unique_id = f"{self._device_id}_climate"
        self._attr_translation_key = "rinnai"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": device.device_name,
            "manufacturer": "Rinnai",
            "model": device.device_type,
        }

        self._attr_available = device.online
        if not device.online:
            _LOGGER.debug("Heating device offline")
            return

        state = self._device_state
        if not state:
            _LOGGER.debug("Heating state not available")
            return

        if state.heating_temp_min:
            self._attr_min_temp = state.heating_temp_min
        if state.heating_temp_max:
            self._attr_max_temp = state.heating_temp_max

        mode_key = state.operation_mode or ""
        if not mode_key:
            mode_code = state.raw_data.get("operationMode")
            mode_key = CODE_TO_MODE.get(mode_code, "") if mode_code else ""
        if mode_key not in HEATING_MODES and mode_key != "standby":
            mode_key = "standby"

        self._current_mode = mode_key or "standby"
        hvac_mode = MODE_TO_HVAC.get(self._current_mode, HVACMode.OFF)
        self._attr_hvac_mode = hvac_mode

        if self._current_mode == "standby":
            self._attr_hvac_action = HVACAction.OFF
        else:
            burning_state = state.burning_state_ch
            if burning_state in ["31", "32"]:
                self._attr_hvac_action = HVACAction.HEATING
            else:
                self._attr_hvac_action = HVACAction.IDLE

        if self._current_mode == "outdoor":
            self._attr_target_temperature = self.min_temp
        else:
            self._attr_target_temperature = state.heating_temp

        extra_attrs: dict[str, Any] = {}
        if self._current_mode == "outdoor":
            extra_attrs["outdoor_mode"] = True

        self._attr_extra_state_attributes = extra_attrs if extra_attrs else None

        _LOGGER.debug(
            "Climate entity mode: %s, target temp: %s, hvac_mode: %s",
            self._current_mode,
            self._attr_target_temperature,
            self._attr_hvac_mode,
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        temperature = int(temperature)
        if temperature < self.min_temp or temperature > self.max_temp:
            _LOGGER.warning(
                "Temperature %s out of range (min: %s, max: %s)",
                temperature,
                self.min_temp,
                self.max_temp,
            )
            return
        # froce update data
        await self.coordinator.async_request_refresh()
        state = self._device_state
        if state and state.operation_mode:
            self._current_mode = state.operation_mode
        elif state:
            mode_name = CODE_TO_MODE.get(state.raw_data.get("operationMode"))
            if mode_name:
                self._current_mode = mode_name
        _LOGGER.debug(
            "Updating mode before setting temperature: %s", self._current_mode
        )

        # Cannot set temperature if in standby mode
        if self._current_mode == "standby":
            _LOGGER.warning("Cannot set heating temperature when heating is off")
            return

        # Cannot set temperature in outdoor mode
        if self._current_mode == "outdoor":
            _LOGGER.warning("Cannot set heating temperature in outdoor mode")
            return

        # Set appropriate temperature based on current mode
        hex_temperature = hex(temperature)[2:].upper()

        if self._current_mode == "normal":
            # Normal mode - set normal heating temperature
            command = {"heatingTempSetting": hex_temperature}
            _LOGGER.debug("Setting normal heating temperature to %s C", temperature)
        elif self._current_mode == "rapid":
            command = {"heatingTempSetting": hex_temperature}
            _LOGGER.debug(
                "Setting rapid heating temperature to %s C", temperature
            )
        else:
            # Default to normal temperature for other modes
            command = {"heatingTempSetting": hex_temperature}
            _LOGGER.debug("Setting heating temperature to %s C", temperature)

        # Send command
        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            # Update local state
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode not in HVAC_TO_MODE:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")

        target_mode = HVAC_TO_MODE[hvac_mode]
        success = await async_apply_heating_mode(
            self.coordinator, self._device_id, target_mode
        )
        if success:
            self._current_mode = target_mode
            self._attr_hvac_mode = hvac_mode
            if target_mode == "standby":
                self._attr_hvac_action = HVACAction.OFF
            else:
                state = self._device_state
                if state and state.burning_state_ch in ["31", "32"]:
                    self._attr_hvac_action = HVACAction.HEATING
                else:
                    self._attr_hvac_action = HVACAction.IDLE
            self.async_write_ha_state()
