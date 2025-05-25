"""Switch platform for Kidde Homesafe integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiddeCoordinator
from .entity import KiddeCommand, KiddeEntity

KEY_MODEL = "model"

logger = logging.getLogger(__name__)


@dataclass
class KiddeSwitchEntityDescriptionMixin:
    """Mixin for required keys."""

    kidde_command_on: KiddeCommand
    kidde_command_off: KiddeCommand


@dataclass
class KiddeSwitchEntityDescription(
    SwitchEntityDescription, KiddeSwitchEntityDescriptionMixin
):
    """Describes Kidde Switch entity."""


_SWITCH_DESCRIPTIONS = (
    KiddeSwitchEntityDescription(
        key="identifying",
        name="Identifying",
        icon="mdi:home-sound-out",
        kidde_command_on=KiddeCommand.IDENTIFY,
        kidde_command_off=KiddeCommand.IDENTIFYCANCEL,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up the switch platform."""
    coordinator: KiddeCoordinator = hass.data[DOMAIN][entry.entry_id]
    switches: list[SwitchEntity] = []

    for device_id, device_data in coordinator.data.devices.items():
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Checking model: [%s]",
                coordinator.data.devices[device_id].get(KEY_MODEL, "Unknown"),
            )

        for entity_description in _SWITCH_DESCRIPTIONS:
            if entity_description.key in device_data:
                switches.append(
                    KiddeSwitchEntity(coordinator, device_id, entity_description)
                )

    async_add_devices(switches)


class KiddeSwitchEntity(KiddeEntity, SwitchEntity):
    """Switch for Kidde HomeSafe."""

    entity_description: KiddeSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the value of the switch."""
        return self.kidde_device.get(self.entity_description.key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.kidde_command(self.entity_description.kidde_command_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.kidde_command(self.entity_description.kidde_command_off)
