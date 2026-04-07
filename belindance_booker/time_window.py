import datetime
import logging

import pytz

from .config import Config


def is_within_window(config: Config) -> bool:
    """
    Check if current time is within the configured time window.

    If time window checking is disabled, returns True (allows execution).
    Otherwise, returns True only if current time in the specified timezone
    is between start and end times.
    """
    if not config.check_time_window_enabled:
        return True

    try:
        tz = pytz.timezone(config.check_time_window_timezone)
        now = datetime.datetime.now(tz)
        current_time = now.time()

        # Parse start and end times
        start_parts = config.check_time_window_start.split(":")
        end_parts = config.check_time_window_end.split(":")

        start_time = datetime.time(int(start_parts[0]), int(start_parts[1]))
        end_time = datetime.time(int(end_parts[0]), int(end_parts[1]))

        within_window = start_time <= current_time <= end_time

        if within_window:
            logging.info(
                "Current time %s is within window %s-%s (%s)",
                current_time.strftime("%H:%M:%S"),
                config.check_time_window_start,
                config.check_time_window_end,
                config.check_time_window_timezone,
            )
        else:
            logging.info(
                "Current time %s is outside window %s-%s (%s)",
                current_time.strftime("%H:%M:%S"),
                config.check_time_window_start,
                config.check_time_window_end,
                config.check_time_window_timezone,
            )

        return within_window
    except Exception as e:
        logging.error("Error checking time window: %s. Proceeding anyway.", e)
        return True
