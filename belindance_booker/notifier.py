import logging
import requests


def send(bot_token: str, chat_id: str, text: str) -> None:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        logging.info("Telegram notification sent")
    except Exception as e:
        logging.warning("Failed to send Telegram notification: %s", e)
