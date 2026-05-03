import datetime
import logging
from typing import List, Optional

from .config import Config
from .scraper import Scraper
from .scanner import find_private_classes, PrivateClass
from .state import load_state, save_state
from . import notifier
from . import time_window
from .exceptions import BookingFailed, LoginError


def run(config: Config) -> None:
    # Check if current time is within the configured time window
    if not time_window.is_within_window(config):
        logging.info("Outside configured time window. Skipping check.")
        return

    state = load_state(config.gist_id, config.gh_pat)

    if len(state["bookings"]) >= config.target_per_month:
        logging.info("Monthly quota met (%d/%d). Nothing to do.", len(state["bookings"]), config.target_per_month)
        return

    scraper = Scraper(config.wb_email, config.wb_password, config.box_url)
    state_dirty = False

    cached_cookies = state.get("cookies", [])
    if cached_cookies:
        scraper.login_with_cookies(cached_cookies)
    else:
        state["cookies"] = scraper.login_with_playwright(config.wb_password)
        state_dirty = True

    try:
        logging.info("Searching for class: '%s'", config.class_name)
        candidates = find_private_classes(scraper, config.class_name)
    except LoginError:
        logging.warning("Cookies expired, re-logging in with browser")
        state["cookies"] = scraper.login_with_playwright(config.wb_password)
        state_dirty = True
        logging.info("Retrying search for class: '%s'", config.class_name)
        candidates = find_private_classes(scraper, config.class_name)

    logging.info("Found %d bookable private class(es) matching '%s'", len(candidates), config.class_name)

    candidates = _filter_by_booking_date_range(candidates, config.booking_start_date, config.booking_end_date)
    booked_dates = [datetime.date.fromisoformat(b["date"]) for b in state["bookings"]]
    target = _pick_candidate(candidates, booked_dates, config.min_days_between, config.max_bookings_per_week)

    if target is None:
        logging.info("No suitable class found (none available or all too close to existing bookings)")
        _notify_no_slots_once_per_day(config, state)
        state["consecutive_errors"] = 0
        save_state(config.gist_id, config.gh_pat, state)
        return

    logging.info("Target: %s at %s (id=%d)", target.date, target.time, target.class_id)

    if config.dry_run:
        logging.info("DRY RUN — skipping actual booking")
        if state_dirty:
            save_state(config.gist_id, config.gh_pat, state)
        notifier.send(
            config.smtp_username,
            config.smtp_password,
            config.email_address,
            subject="✓ I just booked a class!",
            body="I just booked a class!",
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
        )
        return

    try:
        scraper.book_class(target.class_id, target.epoch)
    except BookingFailed as e:
        state["consecutive_errors"] += 1
        save_state(config.gist_id, config.gh_pat, state)
        _maybe_alert(config, state["consecutive_errors"], f"Booking failed: {e}")
        raise

    state["bookings"].append({
        "date": target.date.isoformat(),
        "time": target.time,
        "class_id": target.class_id,
        "booked_at": datetime.datetime.utcnow().isoformat(),
    })
    state["consecutive_errors"] = 0
    save_state(config.gist_id, config.gh_pat, state)

    n = len(state["bookings"])
    notifier.send(
        config.smtp_username,
        config.smtp_password,
        config.email_address,
        subject=f"✓ Booked: {config.class_name} on {target.date}",
        body=f"Booked! {config.class_name}\n{target.date} at {target.time}\n({n}/{config.target_per_month} this month)",
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
    )
    logging.info("Successfully booked %s on %s at %s", config.class_name, target.date, target.time)


def _slot_priority(c: PrivateClass) -> int:
    """
    Lower number = higher priority.
    1. Friday 18h
    2. Friday 17h
    3. Friday 19h
    4. Any other weekday (Mon/Wed/etc.)
    """
    is_friday = c.date.weekday() == 4  # Monday=0 … Friday=4
    hour = int(c.time.split(":")[0])
    if is_friday and hour == 18:
        return 0
    if is_friday and hour == 17:
        return 1
    if is_friday and hour == 19:
        return 2
    return 3


def _same_week(a: datetime.date, b: datetime.date) -> bool:
    return a.isocalendar()[:2] == b.isocalendar()[:2]


def _pick_candidate(
    candidates: List[PrivateClass],
    booked_dates: List[datetime.date],
    min_days: int,
    max_bookings_per_week: int,
) -> Optional[PrivateClass]:
    def eligible_for(gap: int) -> Optional[PrivateClass]:
        ok = [
            c for c in candidates
            if not any(abs((c.date - d).days) < gap for d in booked_dates)
            and sum(1 for d in booked_dates if _same_week(c.date, d)) < max_bookings_per_week
        ]
        if not ok:
            return None
        ok.sort(key=lambda c: (_slot_priority(c), c.date, c.time))
        return ok[0]

    # Prefer 14-day gap, fall back to 7-day if nothing found
    return eligible_for(min_days) or eligible_for(7)


def _maybe_alert(config: Config, consecutive_errors: int, message: str) -> None:
    if consecutive_errors >= 3:
        notifier.send(
            config.smtp_username,
            config.smtp_password,
            config.email_address,
            subject=f"⚠ Belindance Booker Error ({consecutive_errors} errors)",
            body=f"Belindance booker error ({consecutive_errors} in a row): {message}",
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
        )


def _filter_by_booking_date_range(
    candidates: List[PrivateClass],
    booking_start_date: Optional[str],
    booking_end_date: Optional[str],
) -> List[PrivateClass]:
    if not booking_start_date and not booking_end_date:
        return candidates

    min_date = datetime.date.fromisoformat(booking_start_date) if booking_start_date else datetime.date.min
    max_date = datetime.date.fromisoformat(booking_end_date) if booking_end_date else datetime.date.max

    return [c for c in candidates if min_date <= c.date <= max_date]


def _notify_no_slots_once_per_day(config: Config, state: dict) -> None:
    if not config.notify_when_no_slots:
        return

    today = datetime.date.today().isoformat()
    if state.get("last_no_slots_notification_date") == today:
        return

    notifier.send(
        config.smtp_username,
        config.smtp_password,
        config.email_address,
        subject=f"No slots yet for {config.class_name}",
        body=(
            f"Checked availability and found no eligible slots for '{config.class_name}'.\n"
            f"Date window: {config.booking_start_date or 'any'} to {config.booking_end_date or 'any'}."
        ),
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
    )
    state["last_no_slots_notification_date"] = today
