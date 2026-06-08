"""Tests for AuthService.authenticate_user — DB managers are mocked so no real DB is touched."""
from types import SimpleNamespace

import pytest

from Service.AuthService import AuthService


@pytest.fixture
def service(mocker):
    """An AuthService whose AuthManager/UserManager/AuditLogService are mocks."""
    mock_auth_manager = mocker.patch("Service.AuthService.AuthManager").return_value
    mock_user_manager = mocker.patch("Service.AuthService.UserManager").return_value
    mocker.patch("Service.AuthService.AuditLogService")

    return AuthService(), mock_auth_manager, mock_user_manager


def fake_user(**overrides):
    defaults = dict(id=1, username="admin", role="admin", password="hashed-pw",
                    reset_password=False, active=True)
    return SimpleNamespace(**{**defaults, **overrides})


def test_rejects_missing_username_or_password(service):
    auth_service, _, _ = service

    ok, data, error = auth_service.authenticate_user("", "")

    assert ok is False
    assert data is None
    assert error == "Username and password are required"


def test_rejects_unknown_username(service):
    auth_service, mock_auth_manager, _ = service
    mock_auth_manager.find_user_by_username.return_value = None

    ok, data, error = auth_service.authenticate_user("ghost", "whatever")

    assert ok is False
    assert data is None
    assert "User not found" in error


def test_rejects_wrong_password(service):
    auth_service, mock_auth_manager, _ = service
    mock_auth_manager.find_user_by_username.return_value = fake_user()
    mock_auth_manager.verify_password.return_value = False

    ok, data, error = auth_service.authenticate_user("admin", "wrong-password")

    assert ok is False
    assert data is None
    assert error == "Invalid password"


def test_rejects_user_with_no_password_set(service):
    auth_service, mock_auth_manager, _ = service
    mock_auth_manager.find_user_by_username.return_value = fake_user(password=None)

    ok, data, error = auth_service.authenticate_user("admin", "whatever")

    assert ok is False
    assert data is None
    assert "reset password" in error.lower()


def test_accepts_correct_credentials(service):
    auth_service, mock_auth_manager, mock_user_manager = service
    mock_auth_manager.find_user_by_username.return_value = fake_user()
    mock_auth_manager.verify_password.return_value = True

    ok, data, error = auth_service.authenticate_user("admin", "Welcome@123")

    assert ok is True
    assert error is None
    assert data["username"] == "admin"
    assert data["role"] == "admin"
    assert data["user_id"] == 1
    # a successful login should also bump the user's last_login timestamp
    mock_user_manager.update_last_login.assert_called_once_with(1)
