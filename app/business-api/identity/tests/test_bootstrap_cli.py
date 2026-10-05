"""Bootstrap validation never exposes input or configuration secrets."""
from __future__ import annotations

import argparse
import sys

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, select

from banking_shared import CustomerUser, IdentityAudit, Role, User, UserRole

from identity.services import bootstrap
from identity.settings import Settings


@pytest.fixture(autouse=True)
def prevent_database_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_engine(*args: object, **kwargs: object) -> None:
        pytest.fail("Bootstrap validation must not construct a database engine")

    monkeypatch.setattr(bootstrap, "create_engine", unexpected_engine)
    for key in ("ADMIN_BOOTSTRAP_EMAIL", "ADMIN_BOOTSTRAP_PASSWORD", "DEMO_USER_PASSWORD"):
        monkeypatch.delenv(key, raising=False)


def test_invalid_password_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--email", "first@synthetic.invalid",
                                     "--locale", "en", "--confirm-bootstrap"])
    monkeypatch.setattr(bootstrap, "getpass", lambda prompt: "short-secret")
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.err == "Invalid bootstrap input or Auth configuration\n"
    assert "short-secret" not in output.err + output.out


def test_invalid_configuration_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--email", "first@synthetic.invalid",
                                     "--locale", "en", "--confirm-bootstrap"])
    monkeypatch.setattr(bootstrap, "getpass", lambda prompt: "synthetic-bootstrap-password")

    def invalid_settings() -> Settings:
        raise ValidationError.from_exception_data("Settings", [{
            "type": "string_too_short", "loc": ("jwt_secret_key",),
            "input": "configuration-secret", "ctx": {"min_length": 32},
        }])

    monkeypatch.setattr(bootstrap, "Settings", invalid_settings)
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.err == "Invalid bootstrap input or Auth configuration\n"
    assert "configuration-secret" not in output.err + output.out


def bootstrap_args(*, from_env: bool, email: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        credentials_from_env=from_env, email=email, locale="en", name=None,
    )


def test_environment_credentials_require_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    def hidden_password(prompt: str) -> str:
        prompts.append(prompt)
        return "separate-hidden-password"

    monkeypatch.setattr(bootstrap, "getpass", hidden_password)
    request = bootstrap.load_bootstrap_request(
        bootstrap_args(from_env=False, email="prompt@synthetic.invalid"),
        {"ADMIN_BOOTSTRAP_EMAIL": "env@synthetic.invalid",
         "ADMIN_BOOTSTRAP_PASSWORD": "unused-environment-password"},
    )
    assert request.email == "prompt@synthetic.invalid"
    assert request.password.get_secret_value() == "separate-hidden-password"
    assert prompts == ["New administrator password: ", "Confirm password: "]


def test_environment_credentials_preserve_password_and_normalize_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_prompt(prompt: str) -> str:
        pytest.fail("Environment opt-in must not prompt")

    monkeypatch.setattr(bootstrap, "getpass", unexpected_prompt)
    request = bootstrap.load_bootstrap_request(
        bootstrap_args(from_env=True),
        {"ADMIN_BOOTSTRAP_EMAIL": " Admin@Synthetic.Invalid ",
         "ADMIN_BOOTSTRAP_PASSWORD": "  separate-admin-password  ",
         "DEMO_USER_PASSWORD": "customer-password"},
    )
    assert request.email == "admin@synthetic.invalid"
    assert request.password.get_secret_value() == "  separate-admin-password  "


@pytest.mark.parametrize("environment", [
    {}, {"ADMIN_BOOTSTRAP_EMAIL": "admin@synthetic.invalid"},
    {"ADMIN_BOOTSTRAP_PASSWORD": "separate-admin-password"},
    {"ADMIN_BOOTSTRAP_EMAIL": "admin@synthetic.invalid", "ADMIN_BOOTSTRAP_PASSWORD": " "},
])
def test_environment_credentials_fail_closed_without_prompt_or_database(
    environment: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_prompt(prompt: str) -> str:
        pytest.fail("Incomplete environment credentials must not fall back to prompts")

    monkeypatch.setattr(bootstrap, "getpass", unexpected_prompt)
    with pytest.raises(ValueError, match="environment credentials"):
        bootstrap.load_bootstrap_request(bootstrap_args(from_env=True), environment)


@pytest.mark.parametrize("from_env", [False, True])
def test_customer_password_reuse_is_rejected_before_database(
    from_env: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "getpass", lambda prompt: "shared-synthetic-password")
    with pytest.raises(ValueError, match="must differ"):
        bootstrap.load_bootstrap_request(
            bootstrap_args(from_env=from_env, email=None if from_env else "admin@synthetic.invalid"),
            {"ADMIN_BOOTSTRAP_EMAIL": "admin@synthetic.invalid",
             "ADMIN_BOOTSTRAP_PASSWORD": "shared-synthetic-password",
             "DEMO_USER_PASSWORD": " shared-synthetic-password "},
        )


@pytest.mark.parametrize("from_env,email", [(False, None), (True, "admin@synthetic.invalid")])
def test_missing_or_ambiguous_email_is_rejected(from_env: bool, email: str | None) -> None:
    with pytest.raises(ValueError):
        bootstrap.load_bootstrap_request(bootstrap_args(from_env=from_env, email=email), {})


@pytest.mark.parametrize("extra", [[], ["--password", "sensitive-cli-value"]])
def test_environment_cli_failure_is_sanitized(
    extra: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--credentials-from-env", "--locale", "en",
                                     "--confirm-bootstrap", *extra])
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "admin@synthetic.invalid")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "short-secret")
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == (2 if extra else 1)
    output = capsys.readouterr()
    assert "short-secret" not in output.err + output.out
    assert "sensitive-cli-value" not in output.err + output.out


def test_bootstrap_requires_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--credentials-from-env", "--locale", "en"])
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2


def test_environment_cli_bootstraps_independent_admin_on_synthetic_database(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with Session(engine) as session:
        assignment = session.get(UserRole, "admin")
        assert assignment is not None
        session.delete(assignment)
        session.commit()
    disposed: list[bool] = []
    monkeypatch.setattr(engine, "dispose", lambda: disposed.append(True))
    monkeypatch.setattr(bootstrap, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(bootstrap, "Settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--credentials-from-env", "--locale", "en",
                                     "--confirm-bootstrap"])
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "new-admin@synthetic.invalid")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "separate-synthetic-admin-password")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "synthetic-customer-password")
    bootstrap.main()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "new-admin@synthetic.invalid")).one()
        membership = session.get(UserRole, user.id)
        assert membership is not None
        assert session.get(Role, membership.role_id).name == "admin"
        assert session.get(CustomerUser, user.id) is None
        assert bootstrap.IdentityService(settings).passwords.verify(
            "separate-synthetic-admin-password", user.password_hash,
        )
        assert session.exec(select(IdentityAudit).where(
            IdentityAudit.target_id == user.id,
        )).one().action == "admin_bootstrap"
    assert disposed == [True]
    output = capsys.readouterr()
    assert output.out == "Administrator bootstrapped\n"
    assert output.err == ""


def test_hidden_confirmation_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter(("first-synthetic-password", "second-synthetic-password"))
    monkeypatch.setattr(bootstrap, "getpass", lambda prompt: next(values))
    with pytest.raises(ValueError, match="Passwords do not match"):
        bootstrap.load_bootstrap_request(
            bootstrap_args(from_env=False, email="admin@synthetic.invalid"), {},
        )
