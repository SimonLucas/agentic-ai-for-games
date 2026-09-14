"""Lesson 4: let an OpenAI-compatible model choose and call MCP tools."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent


def as_model_tools(mcp_tools: list[Any]) -> list[dict[str, Any]]:
    """Translate MCP tool descriptions to OpenAI-compatible tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def tool_result_text(result: Any) -> str:
    """Turn an MCP result into text that can be sent back to the model."""
    if result.structuredContent is not None:
        return json.dumps(result.structuredContent)
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


async def answer(prompt: str, model: str, base_url: str | None, api_key: str) -> str:
    llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
    server = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "server.py")], cwd=str(ROOT)
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            available = await mcp_session.list_tools()
            tools = as_model_tools(available.tools)
            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "Use the supplied tools for arithmetic and exact letter counting. "
                        "Do not calculate those results yourself."
                    ),
                },
                {"role": "user", "content": prompt},
            ]

            for _ in range(8):
                response = await llm.chat.completions.create(
                    model=model, messages=messages, tools=tools, tool_choice="auto"
                )
                message = response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))

                if not message.tool_calls:
                    return message.content or "(The model returned no text.)"

                for call in message.tool_calls:
                    arguments = json.loads(call.function.arguments)
                    print(f"MCP call -> {call.function.name}({arguments})")
                    result = await mcp_session.call_tool(call.function.name, arguments)
                    if result.isError:
                        raise RuntimeError(tool_result_text(result))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": tool_result_text(result),
                        }
                    )

    raise RuntimeError("The model did not finish after 8 tool-call rounds")


async def answer_without_tools(
    prompt: str, model: str, base_url: str | None, api_key: str
) -> str:
    """Ask the model directly: no MCP server and no tool definitions."""
    llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await llm.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Answer the user's question directly and concisely.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or "(The model returned no text.)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="+", help="Question for the model")
    parser.add_argument("--model", default=os.getenv("MODEL", "gpt-5-mini"))
    parser.add_argument("--base-url", default=os.getenv("BASE_URL"))
    parser.add_argument("--api-key", default=os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--no-tools",
        action="store_true",
        help="Ask the model directly without starting MCP or offering tools",
    )
    mode.add_argument(
        "--compare",
        action="store_true",
        help="Run the same prompt once without tools and once with MCP tools",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT.parents[1] / ".env")
    args = parse_args()
    if not args.api_key or args.api_key.strip().lower() in {
        "replace-me",
        "your-key-here",
        "sk-your-key-here",
    }:
        raise SystemExit(
            "No usable API key was configured. Edit the repository-root .env and replace "
            "the placeholder for your backend (OPENAI_API_KEY or OPENROUTER_API_KEY). "
            "Use the matching backend script, or configure API_KEY and BASE_URL directly."
        )
    prompt = " ".join(args.prompt)
    if args.compare:
        print("=== A: LLM only (no MCP server, no tools) ===", flush=True)
        print(
            asyncio.run(answer_without_tools(prompt, args.model, args.base_url, args.api_key)),
            flush=True,
        )
        print("\n=== B: LLM + MCP tools ===", flush=True)
        print(asyncio.run(answer(prompt, args.model, args.base_url, args.api_key)))
    elif args.no_tools:
        print(asyncio.run(answer_without_tools(prompt, args.model, args.base_url, args.api_key)))
    else:
        print(asyncio.run(answer(prompt, args.model, args.base_url, args.api_key)))


if __name__ == "__main__":
    main()
