import datetime
import json
import logging
import requests

_GIST_API = "https://api.github.com/gists"
_FILENAME = "belindance_state.json"


def load_state(gist_id: str, gh_pat: str) -> dict:
    resp = requests.get(
        f"{_GIST_API}/{gist_id}",
        headers=_auth_headers(gh_pat),
        timeout=10,
    )
    resp.raise_for_status()
    content = resp.json()["files"][_FILENAME]["content"]
    state = json.loads(content)
    current_month = datetime.date.today().strftime("%Y-%m")
    if state.get("month") != current_month:
        logging.info("New month (%s), resetting state", current_month)
        state = _empty_state(current_month)
    return state


def save_state(gist_id: str, gh_pat: str, state: dict) -> None:
    resp = requests.patch(
        f"{_GIST_API}/{gist_id}",
        headers=_auth_headers(gh_pat),
        json={"files": {_FILENAME: {"content": json.dumps(state, indent=2)}}},
        timeout=10,
    )
    resp.raise_for_status()
    logging.info("State saved to Gist")


def _empty_state(month: str) -> dict:
    return {"month": month, "bookings": [], "consecutive_errors": 0}


def _auth_headers(gh_pat: str) -> dict:
    return {
        "Authorization": f"token {gh_pat}",
        "Accept": "application/vnd.github+json",
    }
