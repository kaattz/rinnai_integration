"""Constants for the Rinnai integration."""

from typing import Any, Final

# Integration domain
DOMAIN: Final = "rinnai"

# Configuration keys
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_CONNECT_TIMEOUT: Final = "connect_timeout"

# Data processing configuration

# Attributes and service names
ATTR_HOT_WATER_TEMP: Final = "hot_water_temperature"
ATTR_HEATING_TEMP: Final = "heating_temperature"
ATTR_BURNING_STATE_DHW: Final = "burning_state_dhw"
ATTR_BURNING_STATE_CH: Final = "burning_state_ch"
ATTR_WATER_PRESSURE: Final = "water_pressure"

# Supported platforms
PLATFORMS: Final = frozenset(["sensor", "water_heater", "climate", "switch"])

# Default values
DEFAULT_UPDATE_INTERVAL: Final = 300  # seconds
DEFAULT_CONNECT_TIMEOUT: Final = 30  # seconds

# Rinnai MQTT settings
RINNAI_HOST: Final = "mqtt.rinnai.com.cn"
RINNAI_PORT: Final = 8883

DEFAULT_AUTH_CODE: Final = "03F2"
DEVICE_DEFAULT_AUTH_CODES: Final = {
    "REB": "03F2",
}

#ECO_MODE values
ECO_MODE_ON_VALUE: Final = "31"
ECO_MODE_OFF_VALUE: Final = "31"

# Device type identifiers
DEVICE_TYPE_WATER_HEATER: Final = "water_heater"

# Entity categories
ENTITY_CATEGORY_DIAGNOSTIC: Final = "diagnostic"
ENTITY_CATEGORY_CONFIG: Final = "config"

# Temperature ranges
MIN_TEMP: Final = 35
MAX_TEMP: Final = 65
TEMP_STEP: Final = 1

# Mode mapping definitions
HEATING_MODES: Final = {
    "normal": {
        "display": "Normal Heating",
        "codes": ["normal"],
        "command": "heatingSwitch",
        "value": "31",
        "off_command": "heatingSwitch",
        "off_value": "31",
        "requires_normal": False,
    },
    "outdoor": {
        "display": "Heating Outdoor",
        "codes": ["outdoor"],
        "command": "outdoorMode",
        "value": "31",
        "off_command": "outdoorMode",
        "off_value": "30",
        "requires_normal": True,
    },
    "rapid": {
        "display": "Fast Heating",
        "codes": ["rapid"],
        "command": "rapidHeating",
        "value": "31",
        "off_command": "rapidHeating",
        "off_value": "30",
        "requires_normal": True,
    },
    "standby": {
        "display": "Heating Off",
        "codes": ["standby"],
        "command": "heatingSwitch",
        "value": "31",
        "requires_normal": False,
    },
}

# Map mode codes to mode names
CODE_TO_MODE: Final = {
    code: mode for mode, config in HEATING_MODES.items() for code in config["codes"]
}

# Extract various mode code lists for helper functions
NORMAL_HEATING_CODES: Final = HEATING_MODES["normal"]["codes"]
OUTDOOR_MODES_CODES: Final = HEATING_MODES["outdoor"]["codes"]
RAPID_HEATING_CODES: Final = HEATING_MODES["rapid"]["codes"]
HEATING_OFF_MODES_CODES: Final = HEATING_MODES["standby"]["codes"]

# Burning state mapping
BURNING_STATES: Final = {
    "30": "Standby",
    "31": "Heating Water",
    "32": "Burning",
    "33": "Error",
}

def parse_switch_flag(value: Any) -> bool:
    """Convert Rinnai on/off string values (31/30) to boolean."""
    if value in (None, ""):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"31", "1", "on", "true"}:
            return True
        if normalized in {"30", "0", "off", "false"}:
            return False
        if normalized.startswith("0x"):
            try:
                return int(normalized, 16) != 0
            except ValueError:
                return False
        return normalized not in {"", "0"}
    if isinstance(value, (int, float)):
        return int(value) != 0
    return bool(value)
REB_OPERATION_MODE_FLAGS: Final = {
    "heating_enabled": 0x010000,
    "rapid_heating": 0x000100,
    "eco_mode": 0x400000,
    "outdoor_mode": 0x800000,
}

def parse_reb_operation_mode(value: str | int | None) -> tuple[str, dict[str, bool]]:
    """Parse REB operationMode value into mode key and flag mapping."""
    if value in (None, ""):
        return "standby", {}
    try:
        raw_int = int(value, 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return "standby", {}

    flags = {
        "heating_enabled": bool(raw_int & REB_OPERATION_MODE_FLAGS["heating_enabled"]),
        "rapid_heating": bool(raw_int & REB_OPERATION_MODE_FLAGS["rapid_heating"]),
        "eco_mode": bool(raw_int & REB_OPERATION_MODE_FLAGS["eco_mode"]),
        "outdoor_mode": bool(raw_int & REB_OPERATION_MODE_FLAGS["outdoor_mode"]),
    }

    if flags["outdoor_mode"]:
        mode_key = "outdoor"
    elif flags["rapid_heating"]:
        mode_key = "rapid"
    elif flags["heating_enabled"]:
        mode_key = "normal"
    else:
        mode_key = "standby"

    return mode_key, flags

HOST: Final = "https://iot.rinnai.com.cn/app"
LOGIN_URL: Final = f"{HOST}/V1/login"
INFO_URL: Final = f"{HOST}/V1/device/list"
PROCESS_PARAMETER_URL: Final = f"{HOST}/V1/device/processParameter"

# Rinnai Smart Home app built-in accessKey
AK: Final = "A39C66706B83CCF0C0EE3CB23A39454D"
REFESH_TIME: Final = 86400  # 24 hours
# State parameters
STATE_PARAMETERS: Final = {
    "operationMode",
    "hotWaterTempSetting",
    "heatingTempSetting",
    "burningStateDHW",
    "burningStateCH",
    "temperatureUnit",
    "waterPressureUnit",
    "waterPressure",
    "hotWaterTempBound",
    "heatingTempBound",
}

# Helper methods - for unified state determination
def is_outdoor_mode(operation_mode: str) -> bool:
    """Determine if the mode is outdoor mode. Can handle text status or numeric code."""
    if not operation_mode:
        return False

    # If it's text status
    if "Outdoor" in operation_mode:
        return True

    # If it's numeric code
    return operation_mode in OUTDOOR_MODES_CODES


def is_rapid_heating_mode(operation_mode: str) -> bool:
    """Determine if the mode is rapid heating. Can handle text status or numeric code."""
    if not operation_mode:
        return False

    # If it's text status
    if "Fast" in operation_mode:
        return True

    # If it's numeric code
    return operation_mode in RAPID_HEATING_CODES


def is_heating_off_mode(operation_mode: str) -> bool:
    """Determine if heating is off. Can handle text status or numeric code."""
    if not operation_mode:
        return True

    # If it's text status
    if any(
        off_mode in operation_mode
        for off_mode in ["Power Off", "Heating Off", "Standby"]
    ):
        return True

    # If it's numeric code
    return operation_mode in HEATING_OFF_MODES_CODES


def get_burning_state_ha(burning_state: str) -> str:
    """Get burning state formatted for Home Assistant. Can handle text status or numeric code."""
    if not burning_state:
        return "Standby"

    # If it's numeric code
    if burning_state.isdigit():
        return BURNING_STATES.get(burning_state)

    return burning_state
