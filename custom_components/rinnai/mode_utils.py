"""Helpers for managing Rinnai heating modes."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .const import CODE_TO_MODE, HEATING_MODES

if TYPE_CHECKING:  # pragma: no cover
    from .coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_apply_heating_mode(
    coordinator: "RinnaiCoordinator", device_id: str, target_mode_key: str
) -> bool:
    """Apply the desired heating mode by sending the appropriate command sequence."""
    if target_mode_key not in HEATING_MODES and target_mode_key != "standby":
        _LOGGER.warning("Unknown heating mode requested: %s", target_mode_key)
        return False

    await coordinator.async_request_refresh()
    state = coordinator.get_device_state(device_id)
    if not state:
        _LOGGER.warning("No state available for device %s", device_id)
        return False

    current_mode_code = state.raw_data.get("operationMode")
    current_mode_key = state.operation_mode
    if not current_mode_key and current_mode_code:
        current_mode_key = CODE_TO_MODE.get(current_mode_code, "standby")
    current_mode_key = current_mode_key or "standby"

    if current_mode_key == target_mode_key:
        _LOGGER.debug("Device %s already in %s mode", device_id, target_mode_key)
        return True

    commands_to_send: list[dict[str, Any]] = []
    normal_config = HEATING_MODES["normal"]
    standby_config = HEATING_MODES["standby"]

    if target_mode_key == "standby":
        if current_mode_key not in ["normal", "standby"]:
            current_mode_config = HEATING_MODES.get(current_mode_key)
            if current_mode_config:
                off_command = current_mode_config.get(
                    "off_command", current_mode_config["command"]
                )
                off_value = current_mode_config.get(
                    "off_value", current_mode_config["value"]
                )
                commands_to_send.append({off_command: off_value})
        commands_to_send.append({standby_config["command"]: standby_config["value"]})

    else:
        target_config = HEATING_MODES[target_mode_key]
        target_command = target_config["command"]
        target_value = target_config["value"]

        if current_mode_key == "standby" and target_mode_key != "normal":
            commands_to_send.append({normal_config["command"]: normal_config["value"]})
            commands_to_send.append({target_command: target_value})
        elif current_mode_key not in ["normal", "standby"] and target_mode_key == "normal":
            current_mode_config = HEATING_MODES[current_mode_key]
            off_command = current_mode_config.get(
                "off_command", current_mode_config["command"]
            )
            off_value = current_mode_config.get(
                "off_value", current_mode_config["value"]
            )
            commands_to_send.append({off_command: off_value})
            commands_to_send.append({normal_config["command"]: normal_config["value"]})
        elif current_mode_key not in ["normal", "standby"] and target_mode_key != "standby":
            current_mode_config = HEATING_MODES[current_mode_key]
            off_command = current_mode_config.get(
                "off_command", current_mode_config["command"]
            )
            off_value = current_mode_config.get(
                "off_value", current_mode_config["value"]
            )
            commands_to_send.append({off_command: off_value})
            commands_to_send.append({target_command: target_value})
        else:
            commands_to_send.append({target_command: target_value})

    for command in commands_to_send:
        _LOGGER.debug("Sending heating mode command for %s: %s", device_id, command)
        success = await coordinator.async_send_command(device_id, command)
        if not success:
            _LOGGER.warning("Failed to execute heating mode command: %s", command)
            return False
        await asyncio.sleep(0)

    await coordinator.async_request_refresh()
    return True