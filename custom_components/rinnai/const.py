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
ATTR_FAULT_CODE: Final = "fault_code"
ATTR_GAS_CONSUMPTION_TODAY: Final = "gas_consumption_today"
ATTR_GAS_CONSUMPTION_MONTH: Final = "gas_consumption_month"
ATTR_GAS_CONSUMPTION_YEAR: Final = "gas_consumption_year"
ATTR_ERROR_CODE: Final = "error_code"
ATTR_HEATING_BURNING_TIME: Final = "heating_burning_time"
ATTR_HOT_WATER_BURNING_TIME: Final = "hot_water_burning_time"
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

# Gas consumption is aggregated per day upstream, so polling it hourly would
# send identical requests 24 times for the same answer. Once a day is plenty and
# keeps the account well clear of any rate limiting.
GAS_REFRESH_INTERVAL: Final = 86400
GAS_BACKOFF: Final = (86400, 172800, 604800)
# Small delay between the month and year requests so the two calls never burst.
GAS_REQUEST_SPACING: Final = 5.0

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
    "heating_enabled": 0x010000,   # bit16, app checkBit(op, 0)
    "hot_water_enabled": 0x020000,  # bit17, app checkBit(op, 1)
    "one_key": 0x100000,           # bit20, app checkBit(op, 4) 一键循环
    "standard_mode": 0x200000,     # bit21, app checkBit(op, 5) 标准模式
    "eco_mode": 0x400000,          # bit22, app checkBit(op, 6) 节能
    "outdoor_mode": 0x800000,      # bit23, app checkBit(op, 7) 外出模式
    "rapid_heating": 0x1000000,    # bit24, app checkBit(op, 8) 快速采暖
}

def parse_reb_operation_mode(value: str | int | None) -> tuple[str, dict[str, bool]]:
    """Parse REB operationMode value into mode key and flag mapping.

    Bit positions mirror the app's GBuilderExKt.checkBit(op, n) helper, where
    toLocation() shifts indices 0-7 to bits 16-23. rapid_heating is the
    exception: the app calls checkBit(op, 8), and toLocation leaves 8 as-is, so
    that flag lives at bit 24 (0x01000000) and not at bit 8 (0x00000100).
    """
    if value in (None, ""):
        return "standby", {}
    try:
        raw_int = int(value, 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return "standby", {}

    flags = {
        key: bool(raw_int & mask) for key, mask in REB_OPERATION_MODE_FLAGS.items()
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
GAS_CONSUMPTION_URL: Final = f"{HOST}/V1/device/gasWaterConsumption"

# Gas consumption query parameters, mirroring the app's CostActivityV2:
#   dateType 2 -> one slot per day of the month named by `date` (YYYY-MM)
#   dateType 3 -> one slot per month of the year named by `date` (YYYY)
#   searchType 1 -> gas, 2 -> water
# The API reply is {"total": "<sum>", "consumption": ["...", ...]} in m3.
GAS_DATE_TYPE_DAY: Final = 2
GAS_DATE_TYPE_MONTH: Final = 3
GAS_SEARCH_GAS: Final = 1

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


def to_float(value: Any) -> float | None:
    """Parse a numeric string from the API, treating blanks as no reading.

    The gas consumption series pads unused slots with empty strings.
    """
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_hex_int(value: Any) -> int | None:
    """Parse an explicitly hex-encoded Rinnai counter.

    Only use this for fields known to be hex. Note that a hex counter made of
    digits alone ("0252" = 594) is indistinguishable from a decimal string, so
    the encoding must be chosen per field rather than guessed.
    """
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip(), 16)
    except (TypeError, ValueError):
        return None


def parse_decimal_int(value: Any) -> int | None:
    """Parse an explicitly decimal-encoded Rinnai value.

    Timestamps and bit fields ("1792624032883", "422804") are decimal. Parsing
    them as hex yields absurd integers that overflow HA's state conversion.
    """
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip(), 10)
    except (TypeError, ValueError):
        return None


def parse_auto_int(value: Any) -> int | None:
    """Parse a counter whose encoding is not known ahead of time.

    A letter means hex for certain; pure digits are treated as decimal, which
    is right for the timestamps and bit fields this integration sees. Only use
    this where a wrong guess is harmless.
    """
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if any(c in "abcdefABCDEF" for c in text):
        return parse_hex_int(text)
    return parse_decimal_int(text)


# The appliance reports cumulative burning time as a raw hex counter with no
# documented unit. Observed values (04B6 = 1206) are consistent with minutes,
# which is what the official app assumes for these counters.
BURNING_TIME_UNIT: Final = "min"
