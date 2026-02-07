"""Tests for the Thames Water API client and data models."""

import datetime

import pytest

from custom_components.thames_water.thameswater import (
    Line,
    Measurement,
    MeterUsage,
    meter_usage_lines_to_timeseries,
)


def _make_line(label: str, usage: float, read: float) -> Line:
    return Line(
        Label=label,
        Usage=usage,
        Read=read,
        IsEstimated=False,
        MeterSerialNumberHis="TEST123",
    )


class TestLine:
    def test_create(self):
        line = _make_line("13:00", 5.0, 100.0)
        assert line.Label == "13:00"
        assert line.Usage == 5.0
        assert line.Read == 100.0
        assert line.IsEstimated is False

    def test_from_kwargs(self):
        data = {
            "Label": "0:00",
            "Usage": 0.0,
            "Read": 50.0,
            "IsEstimated": True,
            "MeterSerialNumberHis": "M1",
        }
        line = Line(**data)
        assert line.Label == "0:00"
        assert line.IsEstimated is True


class TestMeterUsage:
    def test_empty_lines(self):
        usage = MeterUsage(
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
        )
        assert usage.Lines == []
        assert usage.AlertsValues == {}


class TestMeterUsageLinesToTimeseries:
    def test_single_day(self):
        """Basic test with a few hours on one day."""
        lines = [
            _make_line("0:00", 2, 100),
            _make_line("1:00", 3, 103),
            _make_line("2:00", 1, 104),
        ]
        start = datetime.datetime(2024, 6, 15)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert len(result) == 3
        assert all(isinstance(m, Measurement) for m in result)

        assert result[0].hour_start.hour == 0
        assert result[0].usage == 2
        assert result[0].total == 100

        assert result[1].hour_start.hour == 1
        assert result[1].usage == 3
        assert result[1].total == 103

        assert result[2].hour_start.hour == 2
        assert result[2].usage == 1
        assert result[2].total == 104

    def test_day_rollover(self):
        """Hours going from 23 to 0 should increment the date."""
        lines = [
            _make_line("22:00", 1, 200),
            _make_line("23:00", 2, 202),
            _make_line("0:00", 3, 205),
            _make_line("1:00", 1, 206),
        ]
        start = datetime.datetime(2024, 6, 15)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert result[0].hour_start.day == 15
        assert result[1].hour_start.day == 15
        assert result[2].hour_start.day == 16
        assert result[3].hour_start.day == 16

    def test_multi_day(self):
        """Full 24-hour cycle wrapping into the next day."""
        lines = []
        reading = 1000
        for hour in range(24):
            lines.append(_make_line(f"{hour}:00", 1, reading + hour + 1))
        # Next day starts
        lines.append(_make_line("0:00", 1, reading + 25))
        lines.append(_make_line("1:00", 1, reading + 26))

        start = datetime.datetime(2024, 6, 15)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert len(result) == 26
        # First 24 hours on day 15
        assert result[0].hour_start.day == 15
        assert result[23].hour_start.day == 15
        assert result[23].hour_start.hour == 23
        # Next day
        assert result[24].hour_start.day == 16
        assert result[24].hour_start.hour == 0
        assert result[25].hour_start.day == 16
        assert result[25].hour_start.hour == 1

    def test_dst_autumn_fallback(self):
        """BST -> GMT: clocks go back, 1:00 AM occurs twice on last Sunday of October."""
        # On 2024-10-27, clocks go back at 2:00 AM BST -> 1:00 AM GMT
        # So we see 1:00 twice
        lines = [
            _make_line("0:00", 1, 500),
            _make_line("1:00", 1, 501),  # first 1:00 (BST)
            _make_line("1:00", 1, 502),  # second 1:00 (GMT, fold=1)
            _make_line("2:00", 1, 503),
        ]
        start = datetime.datetime(2024, 10, 27)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert len(result) == 4
        # All on same date
        assert all(r.hour_start.day == 27 for r in result)

        # First 1:00 has fold=0 (BST)
        assert result[1].hour_start.hour == 1
        assert result[1].hour_start.fold == 0

        # Second 1:00 has fold=1 (GMT)
        assert result[2].hour_start.hour == 1
        assert result[2].hour_start.fold == 1

        assert result[3].hour_start.hour == 2

    def test_dst_spring_forward(self):
        """GMT -> BST: clocks go forward, 1:00 AM jumps to 2:00 AM.

        On 2024-03-31 at 1:00 GMT, clocks jump to 2:00 BST.
        There's no 1:00 AM in BST, so the API would skip hour 1
        and go 0:00 -> 2:00.
        """
        lines = [
            _make_line("0:00", 1, 400),
            _make_line("2:00", 1, 401),  # 1:00 is skipped
            _make_line("3:00", 1, 402),
        ]
        start = datetime.datetime(2024, 3, 31)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert len(result) == 3
        assert result[0].hour_start.hour == 0
        assert result[1].hour_start.hour == 2
        assert result[2].hour_start.hour == 3
        # All same day (no rollover since hours are increasing)
        assert all(r.hour_start.day == 31 for r in result)

    def test_empty_lines(self):
        start = datetime.datetime(2024, 6, 15)
        result = meter_usage_lines_to_timeseries(start, [])
        assert result == []

    def test_timezone_aware_start_raises(self):
        """Start must be a naive datetime."""
        import zoneinfo

        start = datetime.datetime(
            2024, 6, 15, tzinfo=zoneinfo.ZoneInfo("Europe/London")
        )
        with pytest.raises(ValueError, match="naive"):
            meter_usage_lines_to_timeseries(start, [])

    def test_results_are_timezone_aware(self):
        lines = [_make_line("10:00", 5, 300)]
        start = datetime.datetime(2024, 6, 15)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert result[0].hour_start.tzinfo is not None
        assert str(result[0].hour_start.tzinfo) == "Europe/London"

    def test_usage_and_total_are_ints(self):
        """meter_usage_lines_to_timeseries casts to int."""
        lines = [_make_line("5:00", 3.7, 100.9)]
        start = datetime.datetime(2024, 6, 15)
        result = meter_usage_lines_to_timeseries(start, lines)

        assert result[0].usage == 3
        assert result[0].total == 100
        assert isinstance(result[0].usage, int)
        assert isinstance(result[0].total, int)
