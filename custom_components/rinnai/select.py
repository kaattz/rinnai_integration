"""Select platform for Rinnai heating modes."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CODE_TO_MODE, DOMAIN, HEATING_MODES
from .mode_utils import async_apply_heating_mode
from .coordinator import RinnaiCoordinator

MODE_DISPLAY_TO_KEY = OrderedDict(
    (
        (HEATING_MODES["normal"]["display"], "normal"),
        (HEATING_MODES["rapid"]["display"], "rapid"),
        (HEATING_MODES["outdoor"]["display"], "outdoor"),
        (HEATING_MODES["standby"]["display"], "standby"),
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rinnai heating mode select entities."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RinnaiHeatingModeSelect(coordinator, device_id)
        for device_id in coordinator.data.get("devices", {})
    ]

    async_add_entities(entities)


class RinnaiHeatingModeSelect(CoordinatorEntity[RinnaiCoordinator], SelectEntity):
    """Select entity for Rinnai heating modes."""

    _attr_translation_key = "heating_mode"

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_heating_mode"
        self._attr_options = list(MODE_DISPLAY_TO_KEY.keys())

    @property
    def available(self) -> bool:
        device = self.coordinator.get_device(self._device_id)
        return bool(device and device.online)

    @property
    def current_option(self) -> str | None:
        state = self.coordinator.get_device_state(self._device_id)
        if not state:
            return None
        mode_key = state.operation_mode or ""
        if not mode_key and state.raw_data.get("operationMode"):
            mode_key = CODE_TO_MODE.get(state.raw_data.get("operationMode"), "")
        mode_key = mode_key or "standby"
        for display, key in MODE_DISPLAY_TO_KEY.items():
            if key == mode_key:
                return display
        return None

    async def async_select_option(self, option: str) -> None:
        target_key = MODE_DISPLAY_TO_KEY.get(option)
        if not target_key:
            raise ValueError(f"Unsupported heating mode option: {option}")

        success = await async_apply_heating_mode(
            self.coordinator, self._device_id, target_key
        )
        if success:
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