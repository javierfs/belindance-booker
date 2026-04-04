import datetime
import logging
import requests
import pytz
from bs4 import BeautifulSoup

from .exceptions import LoginError, InvalidWodBusterResponse, CloudflareBlocked, BookingFailed

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    )
}

_UTC_TZ = pytz.timezone("UTC")


class Scraper:
    def __init__(self, email: str, password: str, box_url: str):
        self._email = email
        self._password = password
        self._box_url = box_url.rstrip("/")
        self._session = requests.Session()
        self.logged = False

    def login(self) -> None:
        if self.logged:
            return

        login_url = "https://wodbuster.com/account/login.aspx"
        initial = self._session.get(login_url, headers=_HEADERS, timeout=10)
        self._check_cloudflare(initial)

        try:
            soup = BeautifulSoup(initial.content, "lxml")
            viewstatec = soup.find(id="__VIEWSTATEC")["value"]
            eventvalidation = soup.find(id="__EVENTVALIDATION")["value"]
            csrftoken = soup.find(id="CSRFToken")["value"]
        except TypeError as e:
            raise InvalidWodBusterResponse("Could not parse WodBuster login page") from e

        data_login = {
            "ctl00$ctl00$body$ctl00": "ctl00$ctl00$body$ctl00|ctl00$ctl00$body$body$CtlLogin$CtlAceptar",
            "ctl00$ctl00$body$body$CtlLogin$IoTri": "",
            "ctl00$ctl00$body$body$CtlLogin$IoTrg": "",
            "ctl00$ctl00$body$body$CtlLogin$IoTra": "",
            "ctl00$ctl00$body$body$CtlLogin$IoEmail": self._email,
            "ctl00$ctl00$body$body$CtlLogin$IoPassword": self._password,
            "ctl00$ctl00$body$body$CtlLogin$cIoUid": "",
            "ctl00$ctl00$body$body$CtlLogin$CtlAceptar": "Aceptar\n",
        }

        login_resp = self._post_form(login_url, viewstatec, eventvalidation, csrftoken, data_login)

        if 'class="Warning"' in login_resp.text:
            raise LoginError("Invalid WodBuster credentials")

        viewstatec2 = self._parse_hidden_value(login_resp.text, "__VIEWSTATEC")
        eventvalidation2 = self._parse_hidden_value(login_resp.text, "__EVENTVALIDATION")

        data_confirm = {
            "ctl00$ctl00$body$ctl00": "ctl00$ctl00$body$ctl00|ctl00$ctl00$body$body$CtlConfiar$CtlSeguro",
            "ctl00$ctl00$body$body$CtlConfiar$CtlSeguro": "Recordar\n",
        }

        self._post_form(login_url, viewstatec2, eventvalidation2, csrftoken, data_confirm)

        logging.info("Logged in as %s", self._email)
        self.logged = True
        self._password = None

    def _post_form(self, url, viewstatec, eventvalidation, csrftoken, extra):
        data = {
            "CSRFToken": csrftoken,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATEC": viewstatec,
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": eventvalidation,
            "__ASYNCPOST": "true",
            **extra,
        }
        resp = self._session.post(url, data=data, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        return resp

    @staticmethod
    def _parse_hidden_value(text: str, field_name: str) -> str:
        idx = text.index(field_name)
        return text[idx + len(field_name) + 1:].split("|")[0]

    def get_classes(self, date: datetime.date) -> tuple:
        midnight = _UTC_TZ.localize(datetime.datetime.combine(date, datetime.time.min))
        epoch = int(midnight.timestamp())
        url = f"{self._box_url}/athlete/handlers/LoadClass.ashx?ticks={epoch}"
        data = self._get_json(url)
        return data, epoch

    def book_class(self, class_id: int, epoch: int) -> bool:
        url = f"{self._box_url}/athlete/handlers/Calendario_Inscribir.ashx?id={class_id}&ticks={epoch}"
        result = self._get_json(url)
        res = result.get("Res", {})
        if res.get("EsCorrecto"):
            return True
        raise BookingFailed(res.get("ErrorMsg", "Unknown booking error"))

    def _get_json(self, url: str) -> dict:
        resp = self._session.get(url, headers=_HEADERS, allow_redirects=False, timeout=10)
        if resp.status_code == 302 and "login" in resp.headers.get("Location", ""):
            raise LoginError("Session expired — redirect to login")
        if resp.status_code != 200:
            raise InvalidWodBusterResponse(f"Unexpected status {resp.status_code}")
        self._check_cloudflare(resp)
        try:
            return resp.json()
        except Exception as e:
            raise InvalidWodBusterResponse("Non-JSON response from WodBuster") from e

    def _check_cloudflare(self, resp: requests.Response) -> None:
        if resp.status_code in (403, 503) and "cloudflare" in resp.text.lower():
            raise CloudflareBlocked("Cloudflare is blocking requests")
