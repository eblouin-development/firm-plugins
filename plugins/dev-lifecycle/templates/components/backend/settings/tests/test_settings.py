"""Tests for the settings drop-in (settings.py). No real secrets — every
value used is obviously fake."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import Field, ValidationError

from settings import AppSettings


# --- env-loading -------------------------------------------------------


def test_settings_loads_required_field_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pw@localhost/fakedb")
    settings = AppSettings()
    assert settings.database_url == "postgresql+asyncpg://user:pw@localhost/fakedb"


def test_settings_missing_required_field_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        AppSettings(_env_file=None)  # ignore any real .env on disk for this test


def test_settings_default_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    settings = AppSettings()
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.cors_allowed_origins == []


def test_settings_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    settings = AppSettings()
    assert settings.environment == "production"
    assert settings.debug is True


def test_settings_rejects_invalid_environment_literal(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ENVIRONMENT", "not-a-real-environment")
    with pytest.raises(ValidationError):
        AppSettings()


def test_settings_case_insensitive_env_var_names(monkeypatch):
    monkeypatch.setenv("database_url", "sqlite+aiosqlite:///:memory:")  # lowercase
    settings = AppSettings()
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


# --- extra="forbid" ------------------------------------------------------


def test_settings_rejects_unknown_field_passed_directly():
    with pytest.raises(ValidationError):
        AppSettings(database_url="sqlite+aiosqlite:///:memory:", not_a_real_field="x")


def test_settings_unrelated_system_env_vars_are_not_treated_as_extra(monkeypatch):
    # pydantic-settings' env source only maps declared field names -- an
    # unrelated system env var must not trip extra="forbid".
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SOME_UNRELATED_SYSTEM_VAR", "irrelevant-value")
    settings = AppSettings()  # must not raise
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


# --- .env file loading -----------------------------------------------------


def test_settings_loads_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=sqlite+aiosqlite:///./from-dotenv-fake.db\n")

    settings = AppSettings(_env_file=str(env_file))

    assert settings.database_url == "sqlite+aiosqlite:///./from-dotenv-fake.db"


def test_settings_process_env_overrides_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=sqlite+aiosqlite:///./from-dotenv-fake.db\n")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./from-process-env-fake.db")

    settings = AppSettings(_env_file=str(env_file))

    assert settings.database_url == "sqlite+aiosqlite:///./from-process-env-fake.db"


# --- documented secret_store composition point ------------------------------


def test_settings_composes_with_secret_store_via_subclass(monkeypatch):
    """Demonstrates the composition point this component's README and
    module docstring document: a project subclasses AppSettings and wires
    a field's default_factory to secret_store.get_secret(). settings.py
    itself never imports secret_store -- this test imports both
    independently to prove the seam works end to end."""
    import secret_store  # the sibling security/secrets-loading component

    class SettingsWithComposedSecret(AppSettings):
        secret_key: str = Field(default_factory=lambda: secret_store.get_secret("FAKE_SECRET_KEY"))

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("FAKE_SECRET_KEY", "not-a-real-secret-value")

    settings = SettingsWithComposedSecret()

    assert settings.secret_key == "not-a-real-secret-value"


def test_settings_composed_secret_missing_raises_secret_not_found(monkeypatch):
    import secret_store

    class SettingsWithComposedSecret(AppSettings):
        secret_key: str = Field(default_factory=lambda: secret_store.get_secret("DEFINITELY_UNSET_FAKE_KEY"))

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.delenv("DEFINITELY_UNSET_FAKE_KEY", raising=False)

    # secret_store.get_secret(required=True) raises SecretNotFoundError,
    # which pydantic-settings surfaces wrapped as part of the default_factory
    # failure -- fail-fast at startup, exactly the point of the composition.
    with pytest.raises(Exception, match="FAKE_KEY|SecretNotFoundError|not found"):
        SettingsWithComposedSecret()


def test_settings_does_not_import_secret_store_itself():
    # settings.py has no hard dependency on secret_store -- confirm by
    # checking it never appears in settings.py's own module globals unless
    # a test explicitly imported it into ITS OWN namespace (as the tests
    # above do) rather than settings.py doing so.
    import settings as settings_mod

    assert "secret_store" not in vars(settings_mod)
    assert "get_secret" not in vars(settings_mod)
