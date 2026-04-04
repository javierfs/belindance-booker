import os
from dataclasses import dataclass, field


@dataclass
class Config:
    wb_email: str
    wb_password: str
    box_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    gist_id: str
    gh_pat: str
    target_per_month: int
    min_days_between: int
    class_name: str
    dry_run: bool
    turbo: bool
    turbo_duration: int
    poll_interval: int


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
        telegram_bot_token=required("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=required("TELEGRAM_CHAT_ID"),
        gist_id=required("GIST_ID"),
        gh_pat=required("GH_PAT"),
        target_per_month=int(os.environ.get("TARGET_PER_MONTH", "2")),
        min_days_between=int(os.environ.get("MIN_DAYS_BETWEEN", "5")),
        class_name=os.environ.get("CLASS_NAME", "CLASES PARTICULARES BELINDA"),
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        turbo=os.environ.get("TURBO", "false").lower() == "true",
        turbo_duration=int(os.environ.get("TURBO_DURATION", "300")),
        poll_interval=int(os.environ.get("POLL_INTERVAL", "10")),
    )
