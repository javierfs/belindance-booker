import datetime
import logging

from .config import Config
from .scraper import Scraper
from .scanner import find_private_classes, PrivateClass
from .state import load_state, save_state
from . import notifier
from .exceptions import BookingFailed


def run(config: Config) -> None:
    state = load_state(config.gist_id, config.gh_pat)

    if len(state["bookings"]) >= config.target_per_month:
        logging.info("Monthly quota met (%d/%d). Nothing to do.", len(state["bookings"]), config.target_per_month)
        return

    scraper = Scraper(config.wb_email, config.wb_password, config.box_url)
    scraper.login()

    candidates = find_private_classes(scraper, config.class_name)
    logging.info("Found %d bookable private class(es)", len(candidates))

    booked_dates = [
        datetime.date.fromisoformat(b["date"]) for b in state["bookings"]
    ]

    target = _pick_candidate(candidates, booked_dates, config.min_days_between)
    if target is None:
        logging.info("No suitable class found (all too close to existing bookings or none available)")
        state["consecutive_errors"] = 0
        save_state(config.gist_id, config.gh_pat, state)
        return

    logging.info("Target: %s at %s (id=%d)", target.date, target.time, target.class_id)

    if config.dry_run:
        logging.info("DRY RUN — skipping actual booking")
        notifier.send(
            config.telegram_bot_token,
            config.telegram_chat_id,
            f"[DRY RUN] Would book: {config.class_name} on {target.date} at {target.time}",
        )
        return

    try:
        scraper.book_class(target.class_id, target.epoch)
    except BookingFailed as e:
        state["consecutive_errors"] += 1
        save_state(config.gist_id, config.gh_pat, state)
        _maybe_alert(config, state["consecutive_errors"], f"Booking failed: {e}")
        raise

    booking_record = {
        "date": target.date.isoformat(),
        "time": target.time,
        "class_id": target.class_id,
        "booked_at": datetime.datetime.utcnow().isoformat(),
    }
    state["bookings"].append(booking_record)
    state["consecutive_errors"] = 0
    save_state(config.gist_id, config.gh_pat, state)

    n = len(state["bookings"])
    notifier.send(
        config.telegram_bot_token,
        config.telegram_chat_id,
        f"Booked! {config.class_name}\n{target.date} at {target.time}\n({n}/{config.target_per_month} this month)",
    )
    logging.info("Successfully booked %s on %s at %s", config.class_name, target.date, target.time)


def _pick_candidate(
    candidates: list[PrivateClass],
    booked_dates: list[datetime.date],
    min_days: int,
) -> PrivateClass | None:
    for c in candidates:
        too_close = any(
            abs((c.date - d).days) < min_days for d in booked_dates
        )
        if not too_close:
            return c
    return None


def _maybe_alert(config: Config, consecutive_errors: int, message: str) -> None:
    if consecutive_errors >= 3:
        notifier.send(
            config.telegram_bot_token,
            config.telegram_chat_id,
            f"Belindance booker error ({consecutive_errors} in a row): {message}",
        )
