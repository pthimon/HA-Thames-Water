"""Tests for sensor statistics generation logic.

Mocks all Home Assistant imports so tests can run without HA installed.
"""

import datetime
import sys
from types import ModuleType
from unittest.mock import MagicMock

# Mock all homeassistant modules before importing our code
_HA_MODULES = [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.number",
    "homeassistant.components.recorder",
    "homeassistant.components.recorder.models",
    "homeassistant.components.recorder.statistics",
    "homeassistant.components.sensor",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
    "homeassistant.helpers.restore_state",
    "homeassistant.util",
    "homeassistant.util.unit_conversion",
    "voluptuous",
]

_mocks = {}
for mod_name in _HA_MODULES:
    if mod_name not in sys.modules:
        _mocks[mod_name] = MagicMock()
        sys.modules[mod_name] = _mocks[mod_name]


# Make StatisticData behave like a TypedDict (dict-like access)
class FakeStatisticData(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


sys.modules["homeassistant.components.recorder.models"].StatisticData = FakeStatisticData
sys.modules["homeassistant.components.recorder.models"].StatisticMetaData = MagicMock
sys.modules["homeassistant.components.recorder.models"].StatisticMeanType = MagicMock()

# Now we can import our modules
from custom_components.thames_water.thameswater import (
    Line,
    MeterUsage,
    meter_usage_lines_to_timeseries,
)
from custom_components.thames_water.sensor import _generate_statistics_from_meter_usage


def _make_line(label: str, usage: float, read: float) -> Line:
    return Line(
        Label=label,
        Usage=usage,
        Read=read,
        IsEstimated=False,
        MeterSerialNumberHis="TEST123",
    )


def _make_meter_usage(lines: list[Line]) -> MeterUsage:
    return MeterUsage(
        IsError=False,
        IsDataAvailable=True,
        IsConsumptionAvailable=True,
        TargetUsage=0,
        AverageUsage=0,
        ActualUsage=0,
        MyUsage="0",
        AverageUsagePerPerson=0,
        IsMO365Customer=False,
        IsMOPartialCustomer=False,
        IsMOCompleteCustomer=False,
        IsExtraMonthConsumptionMessage=False,
        Lines=lines,
    )


class TestGenerateStatistics:
    def test_basic_statistics(self):
        """Stats should have usage as state and total-initial as sum."""
        lines = [
            _make_line("0:00", 2, 1002),
            _make_line("1:00", 3, 1005),
            _make_line("2:00", 1, 1006),
        ]
        meter_usage = _make_meter_usage(lines)
        start = datetime.datetime(2024, 6, 15)
        initial_reading = 1000.0

        stats = _generate_statistics_from_meter_usage(start, meter_usage, initial_reading)

        assert len(stats) == 3
        assert stats[0]["state"] == 2
        assert stats[0]["sum"] == 1002 - 1000  # total - initial
        assert stats[1]["state"] == 3
        assert stats[1]["sum"] == 1005 - 1000
        assert stats[2]["state"] == 1
        assert stats[2]["sum"] == 1006 - 1000

    def test_initial_reading_offset(self):
        """Different initial readings should shift all sums."""
        lines = [_make_line("5:00", 10, 500)]
        meter_usage = _make_meter_usage(lines)
        start = datetime.datetime(2024, 6, 15)

        stats_a = _generate_statistics_from_meter_usage(start, meter_usage, 0)
        stats_b = _generate_statistics_from_meter_usage(start, meter_usage, 400)

        assert stats_a[0]["sum"] == 500
        assert stats_b[0]["sum"] == 100

    def test_empty_lines(self):
        meter_usage = _make_meter_usage([])
        start = datetime.datetime(2024, 6, 15)
        stats = _generate_statistics_from_meter_usage(start, meter_usage, 0)
        assert stats == []

    def test_stats_have_start_times(self):
        """Each stat should have a timezone-aware start time."""
        lines = [
            _make_line("10:00", 5, 200),
            _make_line("11:00", 3, 203),
        ]
        meter_usage = _make_meter_usage(lines)
        start = datetime.datetime(2024, 6, 15)

        stats = _generate_statistics_from_meter_usage(start, meter_usage, 0)

        assert stats[0]["start"].hour == 10
        assert stats[1]["start"].hour == 11
        assert stats[0]["start"].tzinfo is not None
