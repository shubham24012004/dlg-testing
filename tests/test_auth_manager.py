"""Unit tests for AuthManager password hashing — pure logic, no database needed."""
from Managers.AuthManager import AuthManager


def test_hash_password_does_not_return_plain_text():
    hashed = AuthManager.hash_password("Welcome@123")
    assert hashed != "Welcome@123"
    assert hashed.startswith("pbkdf2:sha256")


def test_hash_password_is_not_deterministic():
    # generate_password_hash salts each hash, so the same password hashes differently each time
    first = AuthManager.hash_password("Welcome@123")
    second = AuthManager.hash_password("Welcome@123")
    assert first != second


def test_verify_password_succeeds_with_correct_password():
    hashed = AuthManager.hash_password("Welcome@123")
    assert AuthManager.verify_password("Welcome@123", hashed) is True


def test_verify_password_fails_with_wrong_password():
    hashed = AuthManager.hash_password("Welcome@123")
    assert AuthManager.verify_password("WrongPassword", hashed) is False
