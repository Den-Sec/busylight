from __future__ import annotations


def validate_ssid(ssid: str) -> str:
    value = ssid.strip()
    if not value:
        raise ValueError("Wi-Fi SSID is required.")
    if len(value) > 32:
        raise ValueError("Wi-Fi SSID cannot exceed 32 characters.")
    return value


def validate_pin(pin: str) -> str:
    value = pin.strip()
    if not value.isdigit() or not 4 <= len(value) <= 8:
        raise ValueError("PIN must be 4-8 digits.")
    return value


def validate_password(password: str) -> str:
    value = password
    if len(value) > 63:
        raise ValueError("Wi-Fi password cannot exceed 63 characters.")
    return value
