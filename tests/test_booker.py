import datetime

from belindance_booker.booker import _filter_by_booking_date_range, _pick_candidate
from belindance_booker.scanner import PrivateClass


def _c(day: int, time: str = "18:00", class_id: int = 1) -> PrivateClass:
    return PrivateClass(
        date=datetime.date(2026, 5, day),
        time=time,
        class_id=class_id,
        epoch=0,
        spots_left=1,
    )


def test_filter_by_booking_date_range_inclusive():
    candidates = [_c(17, class_id=1), _c(18, class_id=2), _c(31, class_id=3), _c(1, class_id=4)]
    filtered = _filter_by_booking_date_range(candidates, "2026-05-18", "2026-05-31")
    assert [c.class_id for c in filtered] == [2, 3]


def test_pick_candidate_respects_weekly_cap():
    candidates = [_c(19, class_id=1), _c(28, class_id=2)]
    booked_dates = [datetime.date(2026, 5, 18)]  # same ISO week as 19th
    picked = _pick_candidate(candidates, booked_dates, min_days=1, max_bookings_per_week=1)
    assert picked is not None
    assert picked.class_id == 2


def test_pick_candidate_returns_none_if_all_same_week_and_cap_reached():
    candidates = [_c(19, class_id=1), _c(20, class_id=2)]
    booked_dates = [datetime.date(2026, 5, 18)]
    picked = _pick_candidate(candidates, booked_dates, min_days=1, max_bookings_per_week=1)
    assert picked is None
