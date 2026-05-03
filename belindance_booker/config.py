import os
from dotenv import load_dotenv

load_dotenv()
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    wb_email: str
    wb_password: str
    box_url: str
    email_address: str
    smtp_username: str
    smtp_password: str
    gist_id: str
    gh_pat: str
    target_per_month: int
    min_days_between: int
    class_name: str
    dry_run: bool
    turbo: bool
    turbo_duration: int
    poll_interval: int
    check_time_window_enabled: bool
    check_time_window_start: str
    check_time_window_end: str
    check_time_window_timezone: str
    booking_start_date: Optional[str]
    booking_end_date: Optional[str]
    max_bookings_per_week: int
    smtp_host: str
    smtp_port: int
    notify_when_no_slots: bool


def load_config() -> Config:
    def required(key: str) -> str:
        val = os.environ.get(key)
        if not val:
            raise EnvironmentError(f"Required env var {key} is not set")
        return val

    return Config(
        wb_email=required("WB_EMAIL"),
        wb_password=required("WB_PASSWORD"),
        box_url=os.environ.get("BOX_URL", "https://belindance.wodbuster.com"),
        email_address=required("EMAIL_ADDRESS"),
        smtp_username=required("SMTP_USERNAME"),
        smtp_password=required("SMTP_PASSWORD"),
        gist_id=required("GIST_ID"),
        gh_pat=required("GH_PAT"),
        target_per_month=int(os.environ.get("TARGET_PER_MONTH", "2")),
        min_days_between=int(os.environ.get("MIN_DAYS_BETWEEN", "14")),
        class_name=os.environ.get("CLASS_NAME", "CLASES PARTICULARES BELINDA"),
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        turbo=os.environ.get("TURBO", "false").lower() == "true",
        turbo_duration=int(os.environ.get("TURBO_DURATION", "300")),
        poll_interval=int(os.environ.get("POLL_INTERVAL", "10")),
        check_time_window_enabled=os.environ.get("CHECK_TIME_WINDOW_ENABLED", "false").lower() == "true",
        check_time_window_start=os.environ.get("CHECK_TIME_WINDOW_START", "14:50"),
        check_time_window_end=os.environ.get("CHECK_TIME_WINDOW_END", "15:30"),
        check_time_window_timezone=os.environ.get("CHECK_TIME_WINDOW_TIMEZONE", "Atlantic/Canary"),
        booking_start_date=os.environ.get("BOOKING_START_DATE"),
        booking_end_date=os.environ.get("BOOKING_END_DATE"),
        max_bookings_per_week=int(os.environ.get("MAX_BOOKINGS_PER_WEEK", "1")),
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "465")),
        notify_when_no_slots=os.environ.get("NOTIFY_WHEN_NO_SLOTS", "true").lower() == "true",
    )
