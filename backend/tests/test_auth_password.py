import pytest

from src.auth import is_valid_password


@pytest.mark.parametrize(
    "password",
    [
        "Abcdefg!",  
        "LongerPassword1?",
        "A" * 7 + "@",
    ],
)
def test_valid_passwords(password):
    assert is_valid_password(password) is True


@pytest.mark.parametrize(
    "password, reason",
    [
        ("Abc!", "too short"),
        ("abcdefg!", "no uppercase"),
        ("Abcdefgh", "no special char"),
        ("", "empty"),
    ],
)
def test_invalid_passwords(password, reason):
    assert is_valid_password(password) is False, reason
