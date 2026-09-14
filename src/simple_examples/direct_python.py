"""Lesson 1: call the functions without MCP or a language model."""

from operations import add, count_letters, multiply


def main() -> None:
    print(f"12 + 30 = {add(12, 30)}")
    print(f"6 × 7 = {multiply(6, 7)}")
    print(f"'a' in 'Banana' = {count_letters('Banana', 'a')}")


if __name__ == "__main__":
    main()
