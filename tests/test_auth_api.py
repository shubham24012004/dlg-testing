"""Integration tests for the /api/auth/login endpoint via Flask's test client.

AuthService is mocked so these tests check routing, status codes and response
shape — not the database. The real authentication logic is covered by
test_auth_service.py.
"""
import pytest
from flask import Flask

from Controllers.AuthController import auth_bp
from utils.rate_limiter import limiter


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    limiter.init_app(app)
    app.register_blueprint(auth_bp, url_prefix="/dlg-analysis")
    return app.test_client()


def test_login_without_body_returns_400(client):
    res = client.post("/dlg-analysis/api/auth/login")
    assert res.status_code == 400


def test_login_with_missing_password_returns_400(client):
    res = client.post("/dlg-analysis/api/auth/login", json={"username": "admin"})
    assert res.status_code == 400
    assert res.get_json()["message"] == "Username and password are required"


def test_login_success_returns_token_and_user(client, mocker):
    mocker.patch(
        "Controllers.AuthController.AuthService.authenticate_user",
        return_value=(True, {
            "user_id": 1, "username": "admin", "role": "admin",
            "reset_password": False, "active": True,
        }, None),
    )

    res = client.post("/dlg-analysis/api/auth/login",
                      json={"username": "admin", "password": "Welcome@123"})
    body = res.get_json()

    assert res.status_code == 200
    assert "token" in body["data"]
    assert body["data"]["user"]["username"] == "admin"
    assert body["data"]["user"]["role"] == "admin"


def test_login_with_wrong_password_returns_401(client, mocker):
    mocker.patch(
        "Controllers.AuthController.AuthService.authenticate_user",
        return_value=(False, None, "Invalid password"),
    )

    res = client.post("/dlg-analysis/api/auth/login",
                      json={"username": "admin", "password": "wrong-password"})
    body = res.get_json()

    assert res.status_code == 401
    assert body["message"] == "Invalid password"


def test_login_route_requires_post(client):
    res = client.get("/dlg-analysis/api/auth/login")
    assert res.status_code == 405
