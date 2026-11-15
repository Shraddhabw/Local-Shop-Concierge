"""Environment-based settings. No secrets are hard-coded here."""
import os


def database_path() -> str:
    return os.environ.get("DATABASE_PATH", "data/shop_concierge.db")


class Settings:
    """Read from the environment when the app is created (so tests can set env first)."""

    def __init__(self):
        env = os.environ.get
        self.secret_key = env("SECRET_KEY", "")
        self.base_domain = env("BASE_DOMAIN", "example.com").strip().lower()
        self.base_url = env("BASE_URL", f"https://{self.base_domain}").rstrip("/")
        self.dev_log_emails = env("DEV_LOG_EMAILS", "false").lower() == "true"
        self.ai_enabled = env("AI_ENABLED", "false").strip().lower() == "true"
        self.claude_model = env("CLAUDE_MODEL", "claude-haiku-5-5")
        self.ai_daily_cap = int(env("AI_DAILY_CAP", "200"))
        self.ai_shop_daily_cap = int(env("AI_SHOP_DAILY_CAP", "30"))
        self.ai_ip_hourly = int(env("AI_IP_HOURLY", "10"))
        self.ai_cooldown_seconds = int(env("AI_COOLDOWN_SECONDS", "300"))
        self.trusted_proxies = [p.strip() for p in env("TRUSTED_PROXIES", "").split(",") if p.strip()]
        self.session_days = int(env("SESSION_DAYS", "7"))
        self.verify_hours = int(env("VERIFY_HOURS", "48"))
        self.rate_limits_enabled = env("RATE_LIMITS_ENABLED", "true").lower() != "false"
        if len(self.secret_key) < 32 or self.secret_key.startswith("change-me"):
            raise RuntimeError("SECRET_KEY must be set to a random value of 32+ characters")
