"""Service handlers for Thames Water integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .sensor import _generate_statistics_from_meter_usage, inject_statistics
from .thameswater import ThamesWater

_LOGGER = logging.getLogger(__name__)

SERVICE_FILL_HISTORICAL = "fill_historical_data"
SERVICE_FILL_HISTORICAL_SCHEMA = vol.Schema(
    {
        vol.Required("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register Thames Water services."""
    if hass.services.has_service(DOMAIN, SERVICE_FILL_HISTORICAL):
        return

    async def handle_fill_historical_data(call: ServiceCall) -> None:
        """Fetch historical data and backfill statistics."""
        start_date = call.data["start_date"]
        end_date = call.data.get(
            "end_date", (datetime.now() - timedelta(days=3)).date()
        )

        entry_data = next(
            (
                v
                for v in hass.data[DOMAIN].values()
                if isinstance(v, Mapping) and "username" in v
            ),
            None,
        )
        if entry_data is None:
            _LOGGER.error("No Thames Water config entry found")
            return

        thames_water = ThamesWater(
            email=entry_data["username"],
            password=entry_data["password"],
            account_number=entry_data["account_number"],
        )
        meter_id = entry_data["meter_id"]

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

                entity = hass.data[DOMAIN].get("initial_reading_entity")
                if entity is not None:
                    await entity.async_set_native_value(initial_reading)
                    entity.async_write_ha_state()

                initial_reading_set = True

            chunk_stats = _generate_statistics_from_meter_usage(
                chunk_start,
                meter_usage,
                hass.data[DOMAIN]["initial_reading"],
            )
            all_stats.extend(chunk_stats)
            chunk_start = chunk_end

        if not all_stats:
            _LOGGER.warning("No historical data found in the given date range")
            return

        inject_statistics(hass, all_stats)
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


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove Thames Water services if no config entries remain."""
    remaining = any(
        isinstance(v, Mapping) and "username" in v
        for v in hass.data[DOMAIN].values()
    )
    if not remaining:
        hass.services.async_remove(DOMAIN, SERVICE_FILL_HISTORICAL)
