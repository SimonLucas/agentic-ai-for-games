"""Read the bundled dictionary independently of the working directory."""

from importlib.resources import files
from pathlib import Path


def read_words(filename: str | Path | None = None) -> list[str]:
    source = Path(filename) if filename is not None else files(__package__).joinpath("data/words.txt")
    words = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        word = line.strip().upper()
        if not word:
            continue
        if not word.isascii() or not word.isalpha():
            raise ValueError(f"invalid dictionary word on line {line_number}")
        words.append(word)
    return words
