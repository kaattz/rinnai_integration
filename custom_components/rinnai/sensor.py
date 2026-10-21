"""Support for Rinnai water heater sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BURNING_STATE_CH,
    ATTR_BURNING_STATE_DHW,
    ATTR_CUMULATIVE_RUNNING_TIME,
    ATTR_DEBUG_RAW,
    ATTR_FAULT_CODE,
    ATTR_GAS_CONSUMPTION,
    ATTR_HEATING_OUTLET_WATER_TEMP,
    ATTR_HEATING_RETURN_WATER_TEMP,
    ATTR_HEATING_TEMP,
    ATTR_HOT_WATER_FLOW,
    ATTR_HOT_WATER_OUTLET_WATER_TEMP,
    ATTR_HOT_WATER_TEMP,
    ATTR_OPERATION_MODE_RAW,
    ATTR_ROOM_TEMPERATURE,
    ATTR_WATER_PRESSURE,
    DOMAIN,
    get_burning_state_ha,
)
from .coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)


def _temp_sensor(
    key: str, translation_key: str, name: str, attribute: str
) -> "RinnaiSensorEntityDescription":
    """Build a temperature sensor backed by one RinnaiDeviceState attribute."""
    return RinnaiSensorEntityDescription(
        key=key,
        translation_key=translation_key,
        name=name,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        # None (not reported) must stay None so the entity reads "unavailable"
        # instead of a misleading 0 C.
        value_fn=lambda _, state: getattr(state, attribute) if state else None,
    )


@dataclass
class RinnaiSensorEntityDescription(SensorEntityDescription):
    """Describes Rinnai sensor entity."""

    value_fn: Callable[[Any, Any], Any] = lambda _, __: None


SENSOR_TYPES: Final[tuple[RinnaiSensorEntityDescription, ...]] = (
    RinnaiSensorEntityDescription(
        key=ATTR_HOT_WATER_TEMP,
        translation_key="hot_water_temperature",
        name="Hot Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, state: state.hot_water_temp if state else 0,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_HEATING_TEMP,
        translation_key="heating_temperature",
        name="Heating Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, state: state.heating_temp if state else 0,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_BURNING_STATE_DHW,
        translation_key="burning_state_dhw",
        name="DHW Burning State",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: get_burning_state_ha(
            state.burning_state_dhw if state else "Standby"
        ),
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_BURNING_STATE_CH,
        translation_key="burning_state_ch",
        name="CH Burning State",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: get_burning_state_ha(
            state.burning_state_ch if state else "Standby"
        ),
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_WATER_PRESSURE,
        translation_key="water_pressure",
        name="Water Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        value_fn=lambda _, state: round(state.water_pressure, 3) if state else None,
    ),
    # --- Measured water temperatures -------------------------------------
    # The appliance has dedicated sensors for these (diagnostic codes 353/363).
    # They stay unavailable unless the cloud actually reports the field, so a
    # "unavailable" state here is the honest answer, not a bug.
    _temp_sensor(
        ATTR_HEATING_OUTLET_WATER_TEMP,
        "heating_outlet_water_temp",
        "Heating Outlet Water Temperature",
        "heating_outlet_water_temp",
    ),
    _temp_sensor(
        ATTR_HEATING_RETURN_WATER_TEMP,
        "heating_return_water_temp",
        "Heating Return Water Temperature",
        "heating_return_water_temp",
    ),
    _temp_sensor(
        ATTR_HOT_WATER_OUTLET_WATER_TEMP,
        "hot_water_outlet_water_temp",
        "Hot Water Outlet Temperature",
        "hot_water_outlet_water_temp",
    ),
    _temp_sensor(
        ATTR_ROOM_TEMPERATURE,
        "room_temperature",
        "Room Temperature",
        "room_temperature",
    ),
    # --- Other telemetry --------------------------------------------------
    RinnaiSensorEntityDescription(
        key=ATTR_HOT_WATER_FLOW,
        translation_key="hot_water_flow",
        name="Hot Water Flow",
        native_unit_of_measurement="L/min",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: state.hot_water_flow if state else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_GAS_CONSUMPTION,
        translation_key="gas_consumption",
        name="Gas Consumption",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: state.gas_consumption if state else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_CUMULATIVE_RUNNING_TIME,
        translation_key="cumulative_running_time",
        name="Cumulative Running Time",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: state.cumulative_running_time if state else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_FAULT_CODE,
        translation_key="fault_code",
        name="Fault Code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: (state.fault_code or state.error_code) or None
        if state
        else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_OPERATION_MODE_RAW,
        translation_key="operation_mode_raw",
        name="Operation Mode Raw",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: state.operation_mode_raw or None if state else None,
    ),
    # --- Field discovery --------------------------------------------------
    # Attaches every key the cloud actually reports to one entity. Use this to
    # confirm whether heatingOutletWaterTemp / returnWaterTemp are present for
    # a given model instead of guessing.
    RinnaiSensorEntityDescription(
        key=ATTR_DEBUG_RAW,
        translation_key="debug_raw",
        name="Debug Raw State",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda _, state: len(state.raw_data) if state else 0,
    ),
)




async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rinnai sensors based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RinnaiSensor(coordinator, device_id, description)
        for device_id in coordinator.data["devices"]
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities)


class RinnaiSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Rinnai sensor."""

    coordinator: RinnaiCoordinator
    entity_description: RinnaiSensorEntityDescription

    def __init__(
        self,
        coordinator: RinnaiCoordinator,
        device_id: str,
        description: RinnaiSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id

        device = coordinator.get_device(device_id)
        if device:
            self._attr_unique_id = f"{device_id}_{description.key}"
            self._attr_has_entity_name = True
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
                "name": device.device_name,
                "manufacturer": "Rinnai",
                "model": device.device_type,
            }
        else:
            self._attr_unique_id = f"{device_id}_{description.key}"
            self._attr_name = f"Rinnai Device {description.name}"

        self._update_attributes()

    @property
    def _device(self):
        """Get the device object."""
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        """Get the device state object."""
        return self.coordinator.get_device_state(self._device_id)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._device or not self._device.online:
            return False
        return self._device_state is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle device updates."""
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Update sensor attributes based on device state."""
        device = self._device
        if not device:
            self._attr_available = False
            return

        state = self.coordinator.get_device_state(self._device_id)
        self._attr_native_value = self.entity_description.value_fn(device, state)

        # Expose the full payload on the discovery entity so the exact set of
        # fields a given model reports can be read straight from the UI.
        if self.entity_description.key == ATTR_DEBUG_RAW:
            raw = dict(state.raw_data) if state else {}
            self._attr_extra_state_attributes = {
                "device_type": device.device_type,
                "device_id": self._device_id,
                "raw_field_count": len(raw),
                "raw_fields": sorted(raw),
                "raw_values": {k: str(v) for k, v in sorted(raw.items())},
            }
