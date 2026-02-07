"""Number platform for Thames Water configurable entities."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_COST_PER_CUBIC_METRE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> bool:
    """Set up the Thames Water number platform."""
    meter_id = entry.data["meter_id"]
    cost_entity = ThamesWaterCostPerCubicMetre(hass, meter_id)
    initial_reading_entity = ThamesWaterInitialReading(hass, meter_id)
    async_add_entities([cost_entity, initial_reading_entity])
    return True


class ThamesWaterCostPerCubicMetre(RestoreEntity, NumberEntity):
    """Number entity for configuring the water cost per cubic metre."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 0.0001
    _attr_native_unit_of_measurement = "£/m³"
    _attr_mode = NumberMode.BOX
    _attr_name = "Thames Water Cost Per Cubic Metre"
    _attr_icon = "mdi:currency-gbp"

    def __init__(self, hass: HomeAssistant, meter_id: str) -> None:
        """Initialize the number entity."""
        self._hass = hass
        self._attr_unique_id = f"cost_per_cubic_metre_{meter_id}"
        self._attr_native_value = DEFAULT_COST_PER_CUBIC_METRE

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, "thames_water")},
            manufacturer="Thames Water",
            model="Thames Water",
            name="Thames Water Meter",
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous value on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = float(last_state.state)
        self._hass.data[DOMAIN]["cost_per_cubic_metre"] = self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the cost per cubic metre."""
        self._attr_native_value = value
        self._hass.data[DOMAIN]["cost_per_cubic_metre"] = value


class ThamesWaterInitialReading(RestoreEntity, NumberEntity):
    """Number entity for configuring the initial meter reading."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 999999999.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "L"
    _attr_mode = NumberMode.BOX
    _attr_name = "Thames Water Initial Meter Reading"
    _attr_icon = "mdi:counter"

    def __init__(self, hass: HomeAssistant, meter_id: str) -> None:
        """Initialize the number entity."""
        self._hass = hass
        self._attr_unique_id = f"initial_reading_{meter_id}"
        self._attr_native_value = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, "thames_water")},
            manufacturer="Thames Water",
            model="Thames Water",
            name="Thames Water Meter",
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous value on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = float(last_state.state)
        if self._attr_native_value is not None:
            self._hass.data[DOMAIN]["initial_reading"] = self._attr_native_value
        self._hass.data[DOMAIN]["initial_reading_entity"] = self

    async def async_set_native_value(self, value: float) -> None:
        """Update the initial meter reading."""
        self._attr_native_value = value
        self._hass.data[DOMAIN]["initial_reading"] = value
