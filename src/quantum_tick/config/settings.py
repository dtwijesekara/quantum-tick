"""Application settings, loaded from environment / .env.

Note: list-typed fields (e.g. symbols) are deliberately kept as plain `str`
and parsed via a computed property. pydantic-settings tries to JSON-decode
any complex-typed env var before validators run, so a plain comma-separated
value like `SYMBOLS=R_10,R_25` raises at startup if the field is typed
`list[str]`. See docs/postmortem/PROJECT_POSTMORTEM.md item 9.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Deriv credentials / connection
    deriv_app_id: str
    deriv_api_token: str
    deriv_account_type: str = "demo"  # "demo" or "real"
    deriv_currency: str = "USD"

    # Instruments
    symbols: str = "R_10,R_25,R_50,R_75,R_100"
    timeframe_seconds: int = 60

    # Risk / sizing
    stake: float = 1.00
    max_daily_loss: float = 10.00
    max_trades_per_day: int = 10

    # Persistence / logging
    database_url: str = "sqlite:///./data/quantum_tick.db"
    log_level: str = "INFO"

    # Safety interlock: live_trading_service refuses real orders unless both
    # this is false AND deriv_account_type == "real".
    dry_run: bool = True

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
