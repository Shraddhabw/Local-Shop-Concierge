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
        self.trusted_proxies = [p.strip() for p in env("TRUSTED_PROXIES", "").split(",") if p.strip()]
        self.session_days = int(env("SESSION_DAYS", "7"))
        self.verify_hours = int(env("VERIFY_HOURS", "48"))
        self.rate_limits_enabled = env("RATE_LIMITS_ENABLED", "true").lower() != "false"
        if len(self.secret_key) < 32 or self.secret_key.startswith("change-me"):
            raise RuntimeError("SECRET_KEY must be set to a random value of 32+ characters")
