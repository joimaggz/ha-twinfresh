"""Sensor platform for integration_blueprint."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SikuEntity
from .const import DEFAULT_NAME
from .const import DOMAIN
from .coordinator import SikuDataUpdateCoordinator

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Siku sensor."""
    async_add_entities(
        [
            SikuSensor(
                hass,
                hass.data[DOMAIN][entry.entry_id],
                f"{entry.entry_id}",
                DEFAULT_NAME,
            )
        ]
    )


class SikuSensor(SikuEntity, SensorEntity):
    """Siku Sensor class."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SikuDataUpdateCoordinator,
        unique_id: str,
        name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.hass = hass
        self._unique_id = unique_id
        if name is None:
            name = {DEFAULT_NAME}
        self._attr_name = f"{name} {coordinator.api.host}"

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self.coordinator.data.get("body")
