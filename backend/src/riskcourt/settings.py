"""Typed, fail-closed runtime configuration for RiskCourt."""

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class RuntimeMode(StrEnum):
    """The only runtime modes RiskCourt supports."""

    RECORDED = "recorded"
    PAPER = "paper"


class Settings(BaseSettings):
    """Load environment settings while permanently excluding live trading."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    riskcourt_mode: RuntimeMode = RuntimeMode.RECORDED
    alpaca_api_key_id: SecretStr | None = None
    alpaca_api_secret_key: SecretStr | None = None
    alpaca_paper_base_url: AnyHttpUrl = AnyHttpUrl("https://paper-api.alpaca.markets")
    riskcourt_live_trading: bool = False
    alpaca_live_trading: bool = False
    riskcourt_state_dir: Path = PROJECT_ROOT / ".riskcourt"
    riskcourt_allowed_origins: str = ""

    @model_validator(mode="after")
    def reject_unsafe_configuration(self) -> Self:
        """Reject credentials and endpoints that could create a live-money path."""

        is_official_paper_endpoint = (
            str(self.alpaca_paper_base_url) == "https://paper-api.alpaca.markets/"
        )
        if not is_official_paper_endpoint:
            raise ValueError(
                "ALPACA_PAPER_BASE_URL must be exactly the Alpaca paper-trading endpoint"
            )

        if self.riskcourt_live_trading or self.alpaca_live_trading:
            raise ValueError("live trading is permanently disabled in RiskCourt")

        has_key = self._secret_has_value(self.alpaca_api_key_id)
        has_secret = self._secret_has_value(self.alpaca_api_secret_key)
        if self.riskcourt_mode is RuntimeMode.PAPER and not (has_key and has_secret):
            raise ValueError("paper mode requires ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY")

        return self

    @staticmethod
    def _secret_has_value(value: SecretStr | None) -> bool:
        return value is not None and bool(value.get_secret_value().strip())

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """Return the exact configured CORS allowlist, never a wildcard."""

        return tuple(
            origin.strip().rstrip("/")
            for origin in self.riskcourt_allowed_origins.split(",")
            if origin.strip()
        )
