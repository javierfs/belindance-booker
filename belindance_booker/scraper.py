import datetime
import logging
import requests
import pytz
import shutil
import os
from urllib.parse import urlparse

from .exceptions import LoginError, InvalidWodBusterResponse, CloudflareBlocked, BookingFailed


def _cleanup_broken_playwright_cache():
    """Remove broken headless_shell cache that prevents chromium from launching."""
    cache_dir = os.path.expanduser("~/Library/Caches/ms-playwright")
    headless_shell = os.path.join(cache_dir, "chromium_headless_shell-1208")
    if os.path.exists(headless_shell):
        try:
            shutil.rmtree(headless_shell)
            logging.debug("Cleaned up broken Playwright headless_shell cache")
        except Exception as e:
            logging.debug("Could not clean up headless_shell cache: %s", e)

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

    def login_with_playwright(self, password: str = None) -> list[dict]:
        """
        Drive a real browser to complete the JS-based login flow.
        Returns cookies to be cached in state for subsequent runs.
        Requires: playwright install chromium

        Args:
            password: Optional password override (for retry attempts)
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
        cookies = []  # Initialize before try block
        # Use provided password or fall back to instance password
        login_password = password if password is not None else self._password

        # Clean up broken Playwright cache before attempting to launch
        _cleanup_broken_playwright_cache()

        try:
            with sync_playwright() as p:
                # Use the full chromium executable, not headless_shell
                chromium_path = p.chromium.executable_path
                browser = p.chromium.launch(executable_path=chromium_path, headless=True)
                context = browser.new_context(user_agent=_HEADERS["User-Agent"])
                page = context.new_page()

                logging.info("Loading WodBuster login page...")
                page.goto(start_url, timeout=30000)

                logging.info("Filling email: %s", self._email)
                page.fill('input[name="ctl00$ctl00$body$body$CtlLogin$IoEmail"]', self._email)

                logging.info("Filling password...")
                page.fill('input[name="ctl00$ctl00$body$body$CtlLogin$IoPassword"]', login_password)

                logging.info("Submitting login form...")
                page.click('input[name="ctl00$ctl00$body$body$CtlLogin$CtlAceptar"]')

                logging.info("Waiting for page to load after login...")
                page.wait_for_load_state("networkidle", timeout=15000)

                logging.info("Looking for Trusted Device dialog...")
                try:
                    # Check for trusted device checkbox and try different button selectors
                    logging.info("Using JavaScript to check Trusted Device and submit...")
                    result = page.evaluate("""
                        (() => {
                            const checkbox = document.getElementById('body_body_CtlConfiar_CtlSeguro');
                            if (checkbox) {
                                checkbox.checked = true;
                                // Try multiple selectors for the button
                                let btn = document.querySelector('input[name="ctl00$ctl00$body$body$CtlConfiar$CtlSeguro"]');
                                if (!btn) {
                                    btn = document.querySelector('button[onclick*="CtlConfiar"]');
                                }
                                if (!btn) {
                                    btn = document.querySelector('[name*="CtlConfiar"]');
                                }
                                if (btn) {
                                    btn.click();
                                    return 'Dialog found and clicked';
                                }
                                // List all inputs for debugging
                                const inputs = Array.from(document.querySelectorAll('input[type="submit"], button'));
                                return 'Dialog checkbox found. Inputs: ' + inputs.map(i => i.name || i.id || i.innerText).join(', ');
                            }
                            return 'Dialog checkbox not found';
                        })()
                    """)
                    logging.info("JavaScript result: %s", result)
                    logging.info("Waiting for page to settle...")
                    import time
                    time.sleep(2)
                except Exception as e:
                    logging.warning("JavaScript execution error: %s", e)

                # Navigate to the specific Belindance studio page
                try:
                    logging.info("Navigating to Belindance studio page: %s", self._box_url)
                    page.goto(self._box_url, timeout=15000, wait_until="networkidle")
                    logging.info("Successfully navigated to Belindance studio")

                    # Wait for the page to fully load and establish session
                    import time
                    logging.info("Waiting for session to establish...")
                    time.sleep(3)

                    # Try to verify we're authenticated by checking for user-specific content
                    logging.info("Verifying authentication...")
                    try:
                        page.wait_for_selector("body", timeout=5000)  # Just verify page exists
                    except:
                        pass

                except Exception as e:
                    logging.warning("Navigation error: %s. Proceeding anyway.", e)

                cookies = context.cookies()
                logging.info("Extracted %d cookies from browser", len(cookies))

                # Log cookie names for debugging
                if cookies:
                    cookie_names = [c.get('name', 'unknown') for c in cookies]
                    logging.info("Cookie names: %s", ', '.join(cookie_names))

        finally:
            # Only clear password after successful login (if we have cookies)
            if cookies:
                self._password = None
            else:
                logging.warning("Login failed (no cookies extracted), keeping password for retry")

        if not cookies:
            raise LoginError("Browser login failed — no cookies extracted")

        logging.info("✅ Browser login succeeded with %d cookies", len(cookies))
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
