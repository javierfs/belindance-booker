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

    booked_dates = [datetime.date.fromisoformat(b["date"]) for b in state["bookings"]]
    target = _pick_candidate(candidates, booked_dates, config.min_days_between)

    if target is None:
        logging.info("No suitable class found (none available or all too close to existing bookings)")
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


def _pick_candidate(
    candidates: List[PrivateClass],
    booked_dates: List[datetime.date],
    min_days: int,
) -> Optional[PrivateClass]:
    eligible = [c for c in candidates if not any(abs((c.date - d).days) < min_days for d in booked_dates)]
    if not eligible:
        return None
    eligible.sort(key=lambda c: (_slot_priority(c), c.date, c.time))
    return eligible[0]


def _maybe_alert(config: Config, consecutive_errors: int, message: str) -> None:
    if consecutive_errors >= 3:
        notifier.send(
            config.smtp_username,
            config.smtp_password,
            config.email_address,
            subject=f"⚠ Belindance Booker Error ({consecutive_errors} errors)",
            body=f"Belindance booker error ({consecutive_errors} in a row): {message}",
        )
