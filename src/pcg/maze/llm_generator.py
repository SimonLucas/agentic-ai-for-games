"""One-shot LLM maze generation without tools."""

from __future__ import annotations

import json
import time
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from game_agent.llm_backend import LLMBackendParams, connection, generation_options

from .model import Maze


SYSTEM_PROMPT = """You are a procedural level designer. Generate one playable binary maze.

The start is the top-left cell and the goal is the bottom-right cell. A valid
maze has a four-directional route between them. Its quality is the length of a
shortest route: longer is better. Create deliberate corridors, branches and
barriers rather than random noise. Seek a different topology from every maze
listed in the request.

First draw one continuous solution route using P cells, then place walls around
it. Check that adjacent P cells connect the top-left corner to the bottom-right
corner before answering. Return only a JSON object such as
{"rows":["PPP", "##P", "..P"]}. Use exactly the requested dimensions. Each
character must be P for the demonstrated route, "." for another passage, or
"#" for a wall. Both corner endpoints must be P. Do not include markdown,
commentary, S, G, spaces, or any other characters. P is only a route annotation;
the harness converts it to an ordinary passage after validation."""


class LLMMazeParams(LLMBackendParams):
    prompt_version: Literal["diverse-v1"] = "diverse-v1"
    structured_output: bool = True


class MazeRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[str] = Field(min_length=2)


class LLMMazeOutputError(ValueError):
    def __init__(self, message: str, metrics: dict, rows: list[str] | None = None):
        super().__init__(message)
        self.metrics = metrics
        self.rows = rows


def maze_response_format(width: int, height: int) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "binary_maze",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "minItems": height,
                        "maxItems": height,
                        "items": {"type": "string", "pattern": f"^[.#P]{{{width}}}$"},
                    },
                },
                "required": ["rows"],
                "additionalProperties": False,
            },
        },
    }


def generation_prompt(
    width: int,
    height: int,
    seed: int,
    previous_maze_texts: list[str],
) -> str:
    previous = "\n\n".join(
        f"Previous maze {index + 1}:\n{text}"
        for index, text in enumerate(previous_maze_texts)
    )
    if not previous:
        previous = "No earlier mazes have been generated in this set."
    return (
        f"Generate maze {len(previous_maze_texts) + 1} in this set.\n"
        f"Dimensions: {width} columns by {height} rows.\n"
        f"Diversity seed: {seed}. Use it as inspiration for a distinct design.\n"
        "Maximise shortest-path fitness while keeping the result visibly and "
        "structurally different from the earlier mazes.\n\n"
        f"{previous}"
    )


def parse_maze_response(text: str | None, width: int, height: int) -> Maze:
    content = (text or "").strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if content.startswith("json"):
            content = content[4:].lstrip()
    response = MazeRows.model_validate_json(content)
    if len(response.rows) != height:
        raise ValueError(f"expected {height} rows, received {len(response.rows)}")
    if any(len(row) != width for row in response.rows):
        raise ValueError(f"every row must contain exactly {width} characters")
    invalid = sorted(set("".join(response.rows)) - {".", "#", "P"})
    if invalid:
        raise ValueError(f"rows contain invalid characters: {invalid}")
    if response.rows[0][0] != "P" or response.rows[-1][-1] != "P":
        raise ValueError("both corner endpoints must be marked P")
    maze = Maze(
        width=width,
        height=height,
        walls=tuple(cell == "#" for row in response.rows for cell in row),
    )
    certificate = Maze(
        width=width,
        height=height,
        walls=tuple(cell != "P" for row in response.rows for cell in row),
    )
    from .model import shortest_path

    if shortest_path(certificate) is None:
        raise ValueError("P cells do not connect start to goal")
    return maze


def displayable_rows(text: str | None, width: int, height: int) -> list[str] | None:
    """Recover a rectangular grid for diagnostics without declaring it valid."""

    try:
        value = json.loads((text or "").strip())
        rows = value.get("rows") if isinstance(value, dict) else None
    except (json.JSONDecodeError, AttributeError):
        return None
    if (
        not isinstance(rows, list)
        or len(rows) != height
        or not all(isinstance(row, str) and len(row) == width for row in rows)
    ):
        return None
    return rows


class LLMMazeGenerator:
    """Own one reusable HTTP client and make one request per maze."""

    def __init__(self, params: LLMMazeParams):
        self.params = params
        self._connection = connection(params)

    async def generate(
        self,
        client: AsyncOpenAI,
        *,
        width: int,
        height: int,
        seed: int,
        previous_maze_texts: list[str],
    ) -> tuple[Maze, dict]:
        prompt = generation_prompt(width, height, seed, previous_maze_texts)
        options = generation_options(self.params)
        if self.params.structured_output:
            options["response_format"] = maze_response_format(width, height)
        start = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                **options,
            )
        except Exception as error:
            message = str(error).replace(self._connection["api_key"], "[REDACTED]")
            raise RuntimeError(f"{self.params.backend} request failed: {message}") from None
        elapsed = time.perf_counter() - start
        if not response.choices:
            raise ValueError("LLM returned no choices")
        message = response.choices[0].message.content
        usage = response.usage
        metrics = {
            "model_calls": 1,
            "prompt_version": self.params.prompt_version,
            "system_prompt": SYSTEM_PROMPT,
            "elapsed_seconds": elapsed,
            "response_id": response.id,
            "response_model": response.model,
            "finish_reason": response.choices[0].finish_reason,
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "raw_response": message,
            "prompt": prompt,
        }
        try:
            maze = parse_maze_response(message, width, height)
        except ValueError as error:
            rows = displayable_rows(message, width, height)
            raise LLMMazeOutputError(
                f"{error}; finish_reason={response.choices[0].finish_reason}",
                metrics,
                rows,
            ) from None
        return maze, metrics

    def client(self) -> AsyncOpenAI:
        return AsyncOpenAI(**self._connection)


def maze_text(maze: Maze) -> str:
    return "\n".join(
        "".join(
            "#" if maze.walls[x + y * maze.width] else "."
            for x in range(maze.width)
        )
        for y in range(maze.height)
    )
