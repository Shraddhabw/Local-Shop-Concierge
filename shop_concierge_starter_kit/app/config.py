"""Environment-based settings. No secrets are hard-coded here."""
import os


def database_path() -> str:
    return os.environ.get("DATABASE_PATH", "data/shop_concierge.db")
