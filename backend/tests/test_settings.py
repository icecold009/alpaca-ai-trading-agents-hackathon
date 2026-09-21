from typing import Any, cast

import pytest
from pydantic import SecretStr, ValidationError

from riskcourt.settings import AiMode, RuntimeMode, Settings


def local_settings(**values: object) -> Settings:
    """Keep settings unit tests independent of an operator's ignored .env."""

    settings_factory = cast(Any, Settings)
    return cast(Settings, settings_factory(_env_file=None, **values))


def test_recorded_mode_is_credential_free_with_typesafe_defaults() -> None:
    settings = local_settings(riskcourt_mode=RuntimeMode.RECORDED)

    assert settings.riskcourt_ai_mode is AiMode.DETERMINISTIC
    assert settings.typesafe_api_key is None
    assert settings.typesafe_model == "jev-latest"


def test_paper_typesafe_mode_requires_typesafe_key() -> None:
    with pytest.raises(ValidationError, match="requires TYPESAFE_API_KEY"):
        local_settings(
            riskcourt_mode=RuntimeMode.PAPER,
            alpaca_api_key_id=SecretStr("paper-key"),
            alpaca_api_secret_key=SecretStr("paper-secret"),
            riskcourt_ai_mode=AiMode.TYPESAFE,
        )


def test_paper_typesafe_mode_accepts_non_empty_key() -> None:
    settings = local_settings(
        riskcourt_mode=RuntimeMode.PAPER,
        alpaca_api_key_id=SecretStr("paper-key"),
        alpaca_api_secret_key=SecretStr("paper-secret"),
        typesafe_api_key=SecretStr("ts-key"),
        riskcourt_ai_mode=AiMode.TYPESAFE,
    )

    assert settings.typesafe_credentials_configured is True
