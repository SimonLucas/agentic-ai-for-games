"""Prefix tree for case-insensitive dictionary lookup."""

from collections.abc import Iterable
from pathlib import Path

from .read_words import read_words


class TrieNode:
    def __init__(self) -> None:
        self.is_word = False
        self.nodes: dict[str, TrieNode] = {}


class TrieDict:
    def __init__(self, words: Iterable[str] = ()) -> None:
        self.root = TrieNode()
        for word in words:
            self.add_word(word)

    def add_word(self, word: str) -> None:
        word = word.strip().upper()
        if not word or not word.isascii() or not word.isalpha():
            raise ValueError("words must contain ASCII letters only")
        node = self.root
        for ch in word:
            if ch not in node.nodes:
                node.nodes[ch] = TrieNode()
            node = node.nodes[ch]
        node.is_word = True

    def check_word(self, word: str) -> bool:
        node = self.root
        for ch in word.strip().upper():
            node = node.nodes.get(ch)
            if node is None:
                return False
        return node.is_word


def trie_real_words(filename: str | Path | None = None) -> TrieDict:
    return TrieDict(read_words(filename))
