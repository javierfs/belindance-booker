import argparse
import logging
import sys
import time

from belindance_booker.config import load_config
from belindance_booker import booker
from belindance_booker.exceptions import LoginError, InvalidWodBusterResponse, CloudflareBlocked

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turbo", action="store_true", help="Poll repeatedly for a fixed duration")
    parser.add_argument("--duration", type=int, default=300, help="Turbo mode duration in seconds")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between polls in turbo mode")
    args = parser.parse_args()

    config = load_config()

    if args.turbo or config.turbo:
        duration = args.duration if args.turbo else config.turbo_duration
        interval = args.interval if args.turbo else config.poll_interval
        _run_turbo(config, duration, interval)
    else:
        _run_once(config)


def _run_once(config):
    try:
        booker.run(config)
    except (LoginError, InvalidWodBusterResponse, CloudflareBlocked) as e:
        logging.error("Fatal error: %s", e)
        sys.exit(1)


def _run_turbo(config, duration: int, interval: int):
    logging.info("Turbo mode: polling every %ds for %ds", interval, duration)
    end_time = time.monotonic() + duration
    while time.monotonic() < end_time:
        try:
            booker.run(config)
        except (LoginError, CloudflareBlocked) as e:
            logging.error("Stopping turbo: %s", e)
            sys.exit(1)
        except Exception as e:
            logging.warning("Error in turbo cycle: %s", e)

        remaining = end_time - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))

    logging.info("Turbo mode finished")


if __name__ == "__main__":
    main()
