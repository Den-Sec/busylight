"""Edge case tests for the input validation helpers."""

from __future__ import annotations

import pytest

from busylight_setup.validation import (
    validate_password,
    validate_pin,
    validate_ssid,
)


# ---------------------------------------------------------------------------
# validate_ssid
# ---------------------------------------------------------------------------
def test_validate_ssid_rejects_empty() -> None:
    with pytest.raises(ValueError, match="required"):
        validate_ssid("   ")


def test_validate_ssid_accepts_unicode() -> None:
    assert validate_ssid("Caffè-Wifi-éñ") == "Caffè-Wifi-éñ"


def test_validate_ssid_trims_whitespace() -> None:
    assert validate_ssid("  HomeNet  ") == "HomeNet"


def test_validate_ssid_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="32"):
        validate_ssid("a" * 33)


def test_validate_ssid_accepts_max_length() -> None:
    name = "a" * 32
    assert validate_ssid(name) == name


# ---------------------------------------------------------------------------
# validate_pin
# ---------------------------------------------------------------------------
def test_validate_pin_accepts_minimum_length() -> None:
    assert validate_pin("1234") == "1234"


def test_validate_pin_accepts_maximum_length() -> None:
    assert validate_pin("12345678") == "12345678"


def test_validate_pin_strips_surrounding_whitespace() -> None:
    assert validate_pin("  4242  ") == "4242"


def test_validate_pin_rejects_too_short() -> None:
    with pytest.raises(ValueError, match="4-8"):
        validate_pin("123")


def test_validate_pin_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="4-8"):
        validate_pin("123456789")


def test_validate_pin_rejects_letters() -> None:
    with pytest.raises(ValueError, match="4-8"):
        validate_pin("abcd")


def test_validate_pin_rejects_mixed_chars() -> None:
    with pytest.raises(ValueError, match="4-8"):
        validate_pin("12a4")


# ---------------------------------------------------------------------------
# validate_password
# ---------------------------------------------------------------------------
def test_validate_password_allows_empty_for_open_networks() -> None:
    # Open networks pass empty passwords; the firmware still accepts them.
    assert validate_password("") == ""


def test_validate_password_accepts_max_length() -> None:
    value = "a" * 63
    assert validate_password(value) == value


def test_validate_password_rejects_64_chars() -> None:
    with pytest.raises(ValueError, match="63"):
        validate_password("a" * 64)


def test_validate_password_preserves_unicode_and_specials() -> None:
    value = "P@ssw0rd!è#"
    assert validate_password(value) == value
