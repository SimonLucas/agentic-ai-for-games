import asyncio
from types import SimpleNamespace

import pytest

from pcg.maze.llm_generator import (
    LLMMazeGenerator,
    LLMMazeParams,
    displayable_rows,
    generation_prompt,
    parse_maze_response,
)


def test_parse_maze_response_accepts_json_and_code_fence() -> None:
    response = '{"rows":["PPP","#.P"]}'
    plain = parse_maze_response(response, 3, 2)
    fenced = parse_maze_response(f"```json\n{response}\n```", 3, 2)

    assert plain == fenced
    assert plain.walls == (False, False, False, True, False, False)


@pytest.mark.parametrize(
    "response",
    [
        '{"rows":["PPP","..P"]}',
        '{"rows":["PPx","..P","..P"]}',
        '{"rows":["#PP","..P","..P"]}',
        '{"rows":["P..","...","..P"]}',
    ],
)
def test_parse_maze_response_rejects_wrong_shape_or_contract(response: str) -> None:
    with pytest.raises(ValueError):
        parse_maze_response(response, 3, 3)


def test_generation_prompt_includes_previous_set_members() -> None:
    prompt = generation_prompt(3, 2, 17, ["...\n..."])

    assert "Diversity seed: 17" in prompt
    assert "Previous maze 1:\n...\n..." in prompt


def test_failed_candidate_grid_can_still_be_displayed() -> None:
    response = '{"rows":["###","###"]}'

    assert displayable_rows(response, 3, 2) == ["###", "###"]
    assert displayable_rows(response, 4, 2) is None


def test_generator_makes_exactly_one_model_request(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = []

    class Completions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            message = SimpleNamespace(
                content=(
                    '{"rows":["PPP","..P"]}'
                )
            )
            choice = SimpleNamespace(message=message, finish_reason="stop")
            usage = SimpleNamespace(prompt_tokens=20, completion_tokens=10)
            return SimpleNamespace(
                choices=[choice], usage=usage, id="response-1", model="fake-model"
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    generator = LLMMazeGenerator(LLMMazeParams(
        backend="openrouter", model="fake-model", max_output_tokens=64
    ))

    maze, metrics = asyncio.run(
        generator.generate(
            client,
            width=3,
            height=2,
            seed=4,
            previous_maze_texts=[],
        )
    )

    assert len(calls) == 1
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert maze.width == 3
    assert metrics["model_calls"] == 1
