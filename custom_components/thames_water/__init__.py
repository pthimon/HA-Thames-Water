import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

import voluptuous as vol

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util.unit_conversion import VolumeConverter

from .const import DEFAULT_COST_PER_CUBIC_METRE, DOMAIN
from .sensor import _generate_statistics_from_meter_usage
from .thameswater import ThamesWater

_LOGGER = logging.getLogger(__name__)

SERVICE_FILL_HISTORICAL = "fill_historical_data"
SERVICE_FILL_HISTORICAL_SCHEMA = vol.Schema(
    {
        vol.Required("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
    }
)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Thames Water component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Thames Water from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward the setup to the sensor platform using the new method
    await hass.config_entries.async_forward_entry_setups(entry, ["number", "sensor"])

    # Register the fill_historical_data service (once)
    if not hass.services.has_service(DOMAIN, SERVICE_FILL_HISTORICAL):

        async def handle_fill_historical_data(call: ServiceCall) -> None:
            """Fetch historical data and backfill statistics."""
            start_date = call.data["start_date"]
            end_date = call.data.get(
                "end_date", (datetime.now() - timedelta(days=3)).date()
            )

            # Find config entry credentials
            entry_data = None
            for value in hass.data[DOMAIN].values():
                if isinstance(value, Mapping) and "username" in value:
                    entry_data = value
                    break

            if entry_data is None:
                _LOGGER.error("No Thames Water config entry found")
                return

            thames_water = ThamesWater(
                email=entry_data["username"],
                password=entry_data["password"],
                account_number=entry_data["account_number"],
            )
            meter_id = entry_data["meter_id"]

            # Fetch data in 7-day chunks
            all_stats = []
            chunk_start = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.min.time())
            initial_reading_set = False

            while chunk_start < end_dt:
                chunk_end = min(chunk_start + timedelta(days=7), end_dt)
                _LOGGER.info(
                    "Fetching historical data from %s to %s",
                    chunk_start.strftime("%Y-%m-%d"),
                    chunk_end.strftime("%Y-%m-%d"),
                )

                try:
                    meter_usage = await thames_water.get_meter_usage(
                        meter_id, chunk_start, chunk_end
                    )
                except Exception:
                    _LOGGER.exception(
                        "Failed to fetch data for %s to %s", chunk_start, chunk_end
                    )
                    chunk_start = chunk_end
                    continue

                if not meter_usage.Lines:
                    chunk_start = chunk_end
                    continue

                # Auto-set initial reading from the earliest data point
                if not initial_reading_set:
                    first_line = meter_usage.Lines[0]
                    initial_reading = first_line.Read - first_line.Usage
                    _LOGGER.info(
                        "Auto-setting initial reading to %s "
                        "(first Read=%s, first Usage=%s)",
                        initial_reading,
                        first_line.Read,
                        first_line.Usage,
                    )
                    hass.data[DOMAIN]["initial_reading"] = initial_reading

                    # Update the number entity directly
                    entity = hass.data[DOMAIN].get("initial_reading_entity")
                    if entity is not None:
                        await entity.async_set_native_value(initial_reading)
                        entity.async_write_ha_state()

                    initial_reading_set = True

                initial_reading = hass.data[DOMAIN]["initial_reading"]
                chunk_stats = _generate_statistics_from_meter_usage(
                    chunk_start, meter_usage, initial_reading
                )
                all_stats.extend(chunk_stats)
                chunk_start = chunk_end

            if not all_stats:
                _LOGGER.warning("No historical data found in the given date range")
                return

            # Inject consumption statistics
            stat_id = f"{DOMAIN}:thameswater_consumption"
            metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Thames Water Consumption",
                source=DOMAIN,
                statistic_id=stat_id,
                unit_of_measurement=UnitOfVolume.LITERS,
                unit_class=VolumeConverter.UNIT_CLASS,
            )
            async_add_external_statistics(hass, metadata, all_stats)

            # Inject cost statistics
            cost_per_litre = (
                hass.data[DOMAIN].get(
                    "cost_per_cubic_metre", DEFAULT_COST_PER_CUBIC_METRE
                )
                / 1000
            )
            stat_cost_id = f"{DOMAIN}:thameswater_cost"
            cost_metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name="Thames Water Cost",
                source=DOMAIN,
                statistic_id=stat_cost_id,
                unit_of_measurement="£",
                unit_class=None,
            )
            cost_stats = [
                StatisticData(
                    start=s["start"],
                    state=s["state"] * cost_per_litre,
                    sum=s["sum"] * cost_per_litre,
                )
                for s in all_stats
            ]
            async_add_external_statistics(hass, cost_metadata, cost_stats)

            _LOGGER.info(
                "Successfully backfilled %d hours of historical statistics",
                len(all_stats),
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_FILL_HISTORICAL,
            handle_fill_historical_data,
            schema=SERVICE_FILL_HISTORICAL_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "number")
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    hass.data[DOMAIN].pop(entry.entry_id)

    # Remove service if no config entries remain
    remaining = [
        v
        for v in hass.data[DOMAIN].values()
        if isinstance(v, Mapping) and "username" in v
    ]
    if not remaining:
        hass.services.async_remove(DOMAIN, SERVICE_FILL_HISTORICAL)

    return True
