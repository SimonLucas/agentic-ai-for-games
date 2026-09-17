"""Lesson 3: discover and call tools through MCP, with no LLM involved."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent


async def main(schema_name: str | None = None) -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "server.py")],
        cwd=str(ROOT),
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Discovered tools:", ", ".join(tool.name for tool in tools.tools))

            if schema_name is not None:
                matching = [tool for tool in tools.tools if tool.name == schema_name]
                if not matching:
                    available = ", ".join(tool.name for tool in tools.tools)
                    raise SystemExit(
                        f"Unknown tool {schema_name!r}. Available tools: {available}"
                    )
                tool = matching[0]
                print(json.dumps({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }, indent=2))
                return

            arithmetic = await session.call_tool("multiply", {"a": 6, "b": 7})
            letters = await session.call_tool(
                "count_letters", {"text": "Mississippi Missouri", "letter": "s"}
            )
            print("multiply(6, 7):", arithmetic.content[0].text)
            print("count_letters(...):", letters.content[0].text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schema",
        metavar="TOOL",
        help="Print one discovered tool's name, description and input schema",
    )
    asyncio.run(main(parser.parse_args().schema))
