from datetime import datetime, timedelta, timezone

from auth import _as_utc


def test_naive_datetime_is_considered_utc():
    result = _as_utc(datetime(2026, 1, 1, 12, 0))
    assert result == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_aware_datetime_is_left_untouched():
    paris = timezone(timedelta(hours=2))
    value = datetime(2026, 1, 1, 12, 0, tzinfo=paris)
    assert _as_utc(value) is value
