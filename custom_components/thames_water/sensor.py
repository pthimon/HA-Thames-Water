"""Platform for sensor integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging

from .thameswater import MeterUsage, ThamesWater, meter_usage_lines_to_timeseries

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util.unit_conversion import VolumeConverter

from .const import DEFAULT_COST_PER_CUBIC_METRE, DOMAIN

_LOGGER = logging.getLogger(__name__)
UPDATE_HOURS = [12, 0]

_DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "thames_water")},
    manufacturer="Thames Water",
    model="Thames Water",
    name="Thames Water Meter",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> bool:
    """Set up the Thames Water sensor platform."""
    sensor = ThamesWaterSensor(hass, entry)
    async_add_entities([sensor], update_before_add=True)

    async_track_time_change(
        hass,
        sensor.async_update_callback,
        hour=UPDATE_HOURS,
        minute=0,
        second=0,
    )
    return True


def _generate_statistics_from_meter_usage(
    start: date, meter_usage: MeterUsage, initial_reading: float
) -> list[StatisticData]:
    """Convert meter usage lines into StatisticData entries."""
    return [
        StatisticData(
            start=measurement.hour_start,
            state=measurement.usage,
            sum=measurement.total - initial_reading,
        )
        for measurement in meter_usage_lines_to_timeseries(start, meter_usage.Lines)
    ]


def inject_statistics(hass: HomeAssistant, stats: list[StatisticData]) -> None:
    """Inject consumption and cost statistics into the recorder."""
    async_add_external_statistics(
        hass,
        StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="Thames Water Consumption",
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:thameswater_consumption",
            unit_of_measurement=UnitOfVolume.LITERS,
            unit_class=VolumeConverter.UNIT_CLASS,
        ),
        stats,
    )

    cost_per_litre = (
        hass.data[DOMAIN].get("cost_per_cubic_metre", DEFAULT_COST_PER_CUBIC_METRE)
        / 1000
    )
    async_add_external_statistics(
        hass,
        StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="Thames Water Cost",
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:thameswater_cost",
            unit_of_measurement="£",
            unit_class=None,
        ),
        [
            StatisticData(
                start=s["start"],
                state=s["state"] * cost_per_litre,
                sum=s["sum"] * cost_per_litre,
            )
            for s in stats
        ],
    )


class ThamesWaterSensor(SensorEntity):
    """Thames Water Sensor class."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_should_poll = False
    _attr_device_info = _DEVICE_INFO

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._attr_unique_id = f"water_usage_{entry.data['meter_id']}"
        self._attr_name = entry.data.get(CONF_NAME, "Thames Water Sensor")
        self._username = entry.data["username"]
        self._password = entry.data["password"]
        self._account_number = entry.data["account_number"]
        self._meter_id = entry.data["meter_id"]

    @callback
    async def async_update_callback(self, ts) -> None:
        """Callback triggered by time change to update the sensor."""
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self):
        """Fetch data, build hourly statistics, and inject external statistics."""
        end_dt = datetime.now() - timedelta(days=3)
        start_dt = end_dt - timedelta(days=3)

        thames_water = ThamesWater(
            email=self._username,
            password=self._password,
            account_number=self._account_number,
        )
        meter_usage = await thames_water.get_meter_usage(
            self._meter_id, start_dt, end_dt
        )
        _LOGGER.info("Fetched %d historical entries", len(meter_usage.Lines))

        if not meter_usage.Lines:
            return

        initial_reading = self._hass.data[DOMAIN].get("initial_reading")
        if initial_reading is None:
            _LOGGER.warning(
                "Initial meter reading not set — skipping statistics update"
            )
            return

        stats = _generate_statistics_from_meter_usage(
            start_dt, meter_usage, initial_reading
        )
        self._attr_native_value = meter_usage.Lines[-1].Read - initial_reading

        inject_statistics(self._hass, stats)
