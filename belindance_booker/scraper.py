import datetime
import logging
import requests
import pytz
from urllib.parse import urlparse

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

    def login_with_cookies(self, cookies: list[dict]) -> None:
        self._load_cookies(cookies)
        self.logged = True
        logging.info("Session restored from %d cookies", len(cookies))

    def login_with_playwright(self) -> list[dict]:
        """
        Drive a real browser to complete the JS-based login flow.
        Returns cookies to be cached in state for subsequent runs.
        Requires: playwright install chromium
        """
        from playwright.sync_api import sync_playwright

        # WodBuster uses Firebase + AJAX — no plain HTTP login possible.
        # The ?cb= param tells the main login to authenticate for this box subdomain.
        box_name = urlparse(self._box_url).hostname.split(".")[0]
        start_url = (
            f"https://wodbuster.com/account/login.aspx"
            f"?cb={box_name}&ReturnUrl={self._box_url}/user/"
        )

        logging.info("Launching browser for login...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=_HEADERS["User-Agent"])
                page = context.new_page()

                page.goto(start_url, timeout=30000)
                page.fill('input[name="ctl00$ctl00$body$body$CtlLogin$IoEmail"]', self._email)
                page.fill('input[name="ctl00$ctl00$body$body$CtlLogin$IoPassword"]', self._password)
                page.click('input[name="ctl00$ctl00$body$body$CtlLogin$CtlAceptar"]')

                page.wait_for_load_state("networkidle", timeout=15000)

                seguro = page.locator('input[value="CtlSeguro"]')
                seguro.wait_for(state="visible", timeout=10000)
                seguro.check()
                page.locator('input[name="ctl00$ctl00$body$body$CtlConfiar$CtlSeguro"]').click()
                page.wait_for_url(f"{self._box_url}/**", timeout=20000)

                cookies = context.cookies()

        finally:
            self._password = None

        logging.info("Browser login succeeded, extracted %d cookies", len(cookies))
        self._load_cookies(cookies)
        self.logged = True
        return cookies

    def _load_cookies(self, cookies: list[dict]) -> None:
        for c in cookies:
            self._session.cookies.set(c["name"], c["value"], domain=c.get("domain", "").lstrip("."))

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
        if resp.status_code == 302:
            location = resp.headers.get("Location", "")
            if "login" in location:
                raise LoginError("Cookies expired — need to re-login")
            raise InvalidWodBusterResponse(f"Unexpected redirect to: {location}")
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
