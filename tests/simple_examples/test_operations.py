import pytest

from operations import add, count_letters, multiply


def test_arithmetic() -> None:
    assert add(2, 3) == 5
    assert multiply(6, 7) == 42


def test_count_letters_is_case_insensitive() -> None:
    assert count_letters("Banana", "a") == 3
    assert count_letters("Mississippi", "S") == 4
    assert count_letters("strawberry", "r") == 3


def test_count_letters_rejects_more_than_one_character() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        count_letters("hello", "ll")
