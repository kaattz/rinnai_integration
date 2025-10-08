"""Switch platform for Rinnai integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ECO_MODE_OFF_VALUE,
    ECO_MODE_ON_VALUE,
    parse_switch_flag,
)
from .coordinator import RinnaiCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rinnai switches from a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[RinnaiEcoModeSwitch] = [
        RinnaiEcoModeSwitch(coordinator, device_id)
        for device_id in coordinator.data.get("devices", {})
    ]

    async_add_entities(entities)


class RinnaiEcoModeSwitch(CoordinatorEntity[RinnaiCoordinator], SwitchEntity):
    """Switch to control the water heater eco mode."""

    _attr_translation_key = "eco_mode"
    _attr_icon = "mdi:leaf"

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_eco_mode_switch"

    @property
    def available(self) -> bool:
        device = self.coordinator.get_device(self._device_id)
        return bool(device and device.online)

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.get_device_state(self._device_id)
        if not state:
            return None

        if state.eco_mode is not None:
            return bool(state.eco_mode)

        raw = state.raw_data.get("ecoMode")
        if raw is not None:
            return parse_switch_flag(raw)

        flags: Any = state.raw_data.get("operationModeFlags")
        if isinstance(flags, dict):
            return bool(flags.get("eco_mode"))

        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_eco_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_eco_mode(False)

    async def _set_eco_mode(self, enable: bool) -> None:
        command = {"ecoMode": ECO_MODE_ON_VALUE if enable else ECO_MODE_OFF_VALUE}
        if await self.coordinator.async_send_command(self._device_id, command):
            state = self.coordinator.get_device_state(self._device_id)
            if state:
                state.eco_mode = enable
                state.raw_data["ecoMode"] = ECO_MODE_ON_VALUE if enable else ECO_MODE_OFF_VALUE
            self.async_write_ha_state()

    @property
    def device_info(self) -> dict[str, Any] | None:
        device = self.coordinator.get_device(self._device_id)
        if not device:
            return None
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": device.device_name,
            "manufacturer": "Rinnai",
            "model": device.device_type,
        }