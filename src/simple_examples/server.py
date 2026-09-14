"""Lesson 2: expose the ordinary functions as MCP tools over stdio."""

from mcp.server.fastmcp import FastMCP

from operations import add as add_numbers
from operations import count_letters as count_letters_in_text
from operations import multiply as multiply_numbers

mcp = FastMCP("beginner-arithmetic-and-strings")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers and return the result."""
    return add_numbers(a, b)


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers and return the result."""
    return multiply_numbers(a, b)


@mcp.tool()
def count_letters(text: str, letter: str) -> int:
    """Count occurrences of one letter in text, ignoring case."""
    return count_letters_in_text(text, letter)


if __name__ == "__main__":
    # stdio means MCP messages travel through stdin/stdout. Do not print from
    # tool functions: arbitrary stdout would corrupt the protocol stream.
    mcp.run(transport="stdio")
