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
ATTR_HEATING_OUTLET_WATER_TEMP: Final = "heating_outlet_water_temp"
ATTR_HEATING_RETURN_WATER_TEMP: Final = "heating_return_water_temp"
ATTR_HOT_WATER_OUTLET_WATER_TEMP: Final = "hot_water_outlet_water_temp"
ATTR_ROOM_TEMPERATURE: Final = "room_temperature"
ATTR_HOT_WATER_FLOW: Final = "hot_water_flow"
ATTR_GAS_CONSUMPTION: Final = "gas_consumption"
ATTR_FAULT_CODE: Final = "fault_code"
ATTR_ERROR_CODE: Final = "error_code"
ATTR_CUMULATIVE_RUNNING_TIME: Final = "cumulative_running_time"
ATTR_OPERATION_MODE_RAW: Final = "operation_mode_raw"
ATTR_DEBUG_RAW: Final = "debug_raw"

# Supported platforms
PLATFORMS: Final = frozenset(["sensor", "water_heater", "climate", "switch"])

# Default values
DEFAULT_UPDATE_INTERVAL: Final = 300  # seconds
DEFAULT_CONNECT_TIMEOUT: Final = 30  # seconds

# Minimum seconds between two outbound HTTP calls, guarded by the client.
# MQTT push is the primary data path, HTTP only backfills.
MIN_HTTP_REQUEST_GAP: Final = 3.0

# HTTP backfill cadence (seconds). A successful poll refreshes the baseline;
# a failed poll pushes the next attempt further out through HTTP_BACKOFF.
HTTP_REFRESH_INTERVAL: Final = 3600
HTTP_BACKOFF: Final = (3600, 10800, 21600)
HTTP_BACKOFF_MAX: Final = HTTP_BACKOFF[-1]

# Seconds to wait after publishing a toggle command before reading state back.
# The appliance needs a moment to apply and report the new bitfield.
TOGGLE_SETTLE_DELAY: Final = 1.5

# Local HTTP API paths
LOCAL_API_PATH_STATUS: Final = "/status"

# Rinnai MQTT settings
RINNAI_HOST: Final = "mqtt.rinnai.com.cn"
RINNAI_PORT: Final = 8883

DEFAULT_AUTH_CODE: Final = "03F2"
DEVICE_DEFAULT_AUTH_CODES: Final = {
    "REB": "03F2",
}

# Eco mode
# The appliance treats "31" on *toggle* fields as "flip current state", it is not
# a level. The official app does the same: DataPusher.option() always publishes
# "31" for ecoMode / outdoorMode / rapidHeating and relies on the device reply.
# So switching eco mode means: publish "31", wait, then read the real state back
# from operationMode bit 22.
ECO_MODE_TOGGLE_VALUE: Final = "31"
# Kept for backwards compatibility with older call sites.
ECO_MODE_ON_VALUE: Final = ECO_MODE_TOGGLE_VALUE
ECO_MODE_OFF_VALUE: Final = ECO_MODE_TOGGLE_VALUE

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


# Raw temperature fields reported as hex strings. The scale is not documented;
# the official app divides by 10 for heat pump heating inlet/outlet values
# (HeaterPumperMachineModel), so that is the default assumption here.
HEX_TEMP_FIELDS: Final = (
    "heatingOutletWaterTemp",
    "returnWaterTemp",
    "hotWaterOutletWaterTemp",
)


def parse_hex_temp(value: Any, divisor: float = 10.0) -> float | None:
    """Parse a hex-encoded temperature into Celsius.

    Returns None when the field is absent, blank, non-hex, or a sentinel such as
    "0000" / "FFFF", so a missing report never looks like a real 0 C reading.
    """
    if value in (None, ""):
        return None
    try:
        raw = int(str(value).strip(), 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return None
    # 0x0000 and 0xFFFF are the usual "no reading" markers.
    if raw in (0x0000, 0xFFFF):
        return None
    return round(raw / divisor, 1)


def parse_hex_int(value: Any) -> int | None:
    """Parse a plain hex-encoded integer, tolerating decimal strings."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    for base in (16, 10):
        try:
            return int(text, base)
        except (TypeError, ValueError):
            continue
    return None
