import random

import pytest

from game_agent.griddle import FlatLetterGrid, GridWordSearch, TrieDict, trie_real_words
from game_agent.griddle.read_words import read_words


def test_prefixes_overlaps_and_repeated_occurrences_all_score():
    grid = FlatLetterGrid(3, tuple("CATCAT   "))
    matches = GridWordSearch(TrieDict(["C", "CA", "CAT", "AT", "CC"]), grid).find_matches()
    assert [(m.word, m.row, m.col, m.direction) for m in matches] == [
        ("CA", 0, 0, "right"), ("CAT", 0, 0, "right"), ("AT", 0, 1, "right"),
        ("CA", 1, 0, "right"), ("CAT", 1, 0, "right"), ("AT", 1, 1, "right"),
        ("CC", 0, 0, "down"),
    ]
    assert sum(m.score for m in matches) == 11


def test_no_backwards_diagonal_wraparound_or_crossing_spaces():
    dictionary = TrieDict(["AB", "BA"])
    for text in ["A   B    ", "  AB     ", "A B      "]:
        assert GridWordSearch(dictionary, FlatLetterGrid(3, tuple(text))).find_words() == []
    assert GridWordSearch(TrieDict(["AB"]), FlatLetterGrid(2, tuple("BA  "))).find_words() == []


@pytest.mark.parametrize("length,score", [(2, 1), (3, 3), (4, 7), (5, 10), (6, 15)])
def test_score_table(length, score):
    word = "ABCDEF"[:length]
    grid = FlatLetterGrid(length, tuple(word + " " * (length**2 - length)))
    matches = GridWordSearch(TrieDict([word]), grid).find_matches()
    assert len(matches) == 1
    assert matches[0].score == score


def test_search_matches_independent_substring_oracle():
    rng = random.Random(42)
    words = {"AB", "BA", "AA", "BB", "ABA", "BAB", "ABBA"}
    dictionary = TrieDict(words)
    for _ in range(50):
        grid = FlatLetterGrid(4, tuple(rng.choice("AB ") for _ in range(16)))
        lines = ["".join(grid.get_letter(r, c) for c in range(4)) for r in range(4)]
        lines += ["".join(grid.get_letter(r, c) for r in range(4)) for c in range(4)]
        expected = [line[start:end] for line in lines for start in range(4)
                    for end in range(start + 2, 5) if line[start:end] in words]
        assert sorted(GridWordSearch(dictionary, grid).find_words()) == sorted(expected)


def test_dictionary_lookup_normalizes_case_and_distinguishes_prefixes():
    trie = TrieDict(["hello", "HE", "hello"])
    assert trie.check_word("Hello")
    assert trie.check_word("he")
    assert not trie.check_word("hell")
    assert not trie.check_word("")
    with pytest.raises(ValueError):
        trie.add_word("a-b")


def test_dictionary_is_available_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert trie_real_words().check_word("HELLO")
    path = tmp_path / "custom.txt"
    path.write_text("hello\n\n Cat \n", encoding="utf-8")
    assert read_words(path) == ["HELLO", "CAT"]
    path.write_text("HELLO\nbad-word", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        read_words(path)
