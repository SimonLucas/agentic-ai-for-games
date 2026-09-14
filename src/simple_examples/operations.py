"""Ordinary Python functions—the capabilities our MCP server will expose."""


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def count_letters(text: str, letter: str) -> int:
    """Count a letter in text, ignoring case.

    A "letter" is one Unicode character. This deliberately simple rule makes
    the tool's contract easy to see and test.
    """
    if len(letter) != 1:
        raise ValueError("letter must contain exactly one character")
    return text.casefold().count(letter.casefold())
