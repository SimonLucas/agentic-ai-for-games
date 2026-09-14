"""Paired, seeded agent comparisons with JSON configuration and replay records."""

import argparse
import asyncio
from contextlib import AsyncExitStack
from collections.abc import Callable
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
from typing import Annotated

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from .flat_letter_grid import GridSize
from .forward_model import ForwardModelGriddle
from .griddle_agents import GridPlayer, MCSAgent, OneStepLookAhead, RandomPlayer
from .read_words import read_words
from .trie_dict import TrieDict


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, description="Unique label for this configuration")
    kind: str = Field(min_length=1, description="Agent factory registered with the harness")
    params: dict[str, JsonValue] = Field(default_factory=dict)


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seeds: list[StrictInt] = Field(min_length=1)
    agents: list[AgentSpec] = Field(min_length=1)
    size: GridSize = 5
    agent_seed: StrictInt = 2026
    words: str | None = None

    @model_validator(mode="after")
    def unique_entries(self) -> "BenchmarkConfig":
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("game seeds must be unique")
        names = [agent.name for agent in self.agents]
        if len(set(names)) != len(names):
            raise ValueError("agent names must be unique")
        return self


class MCSParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rollouts_per_square: Annotated[StrictInt, Field(ge=1)] = 10


AgentFactory = Callable[[dict[str, JsonValue], int], GridPlayer]


def _random_factory(params: dict[str, JsonValue], seed: int) -> GridPlayer:
    if params:
        raise ValueError("random does not accept parameters; use the benchmark agent_seed")
    return RandomPlayer(seed=seed)


def _greedy_factory(params: dict[str, JsonValue], seed: int) -> GridPlayer:
    if params:
        raise ValueError("greedy does not accept parameters")
    return OneStepLookAhead()


def _mcs_factory(params: dict[str, JsonValue], seed: int) -> GridPlayer:
    return MCSAgent(**MCSParams.model_validate(params).model_dump(), seed=seed)


def _llm_factory(params: dict[str, JsonValue], seed: int) -> GridPlayer:
    from .llm_agent import LLMAgent, LLMAgentParams
    return LLMAgent(LLMAgentParams.model_validate(params), seed)


AGENT_FACTORIES: dict[str, AgentFactory] = {
    "random": _random_factory,
    "greedy": _greedy_factory,
    "mcs": _mcs_factory,
    "llm": _llm_factory,
}


def derived_seed(base_seed: int, game_seed: int, name: str) -> int:
    """Stable across processes and independent of agent/seed iteration order."""
    payload = json.dumps([base_seed, game_seed, name], separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def summarize(records: list[dict]) -> list[dict]:
    summaries = []
    for name in dict.fromkeys(record["agent"] for record in records):
        games = [record for record in records if record["agent"] == name]
        scores = [record["score"] for record in games]
        row = {
            "agent": name, "games": len(games), "mean_score": statistics.mean(scores),
            "stdev_score": statistics.stdev(scores) if len(scores) > 1 else 0.0,
            "min_score": min(scores), "max_score": max(scores),
            "mean_seconds": statistics.mean(record["elapsed_seconds"] for record in games),
        }
        metrics = [game["agent_metrics"] for game in games if "agent_metrics" in game]
        if metrics:
            row.update({
                "total_model_calls": sum(m.get("model_calls", 0) for m in metrics),
                "total_tool_calls": sum(m.get("tool_calls", 0) for m in metrics),
                "total_tool_errors": sum(m.get("tool_errors", 0) for m in metrics),
                "total_invalid_moves": sum(m.get("invalid_moves", 0) for m in metrics),
                "total_prompt_tokens": sum(m.get("prompt_tokens", 0) for m in metrics),
                "total_completion_tokens": sum(m.get("completion_tokens", 0) for m in metrics),
                "total_reported_cost_usd": (None if any(m.get("cost_missing_calls", 1) for m in metrics)
                                            else sum(m.get("reported_cost_usd", 0) for m in metrics)),
            })
        summaries.append(row)
    return summaries


def run_benchmark(config: BenchmarkConfig, *, factories: dict[str, AgentFactory] | None = None,
                  progress: Callable[[str], None] | None = None,
                  on_update: Callable[[dict], None] | None = None) -> dict:
    """Run every agent on every seed, with a fresh agent instance per game.

    Custom factories receive (params, derived_agent_seed). They may interpret
    params such as an LLM model ID without requiring changes to this harness.
    Agents receive a simulation model with the current board, remaining deck,
    and current letter, but never the live game's RNG or future deal sequence.
    """
    registry = dict(AGENT_FACTORIES)
    registry.update(factories or {})
    for spec in config.agents:
        if spec.kind not in registry:
            raise ValueError(f"unknown agent kind: {spec.kind}")
    # Validate every factory/parameter set before starting any games.
    players = {}
    for game_seed in config.seeds:
        for spec in config.agents:
            seed = derived_seed(config.agent_seed, game_seed, spec.name)
            players[game_seed, spec.name] = registry[spec.kind](copy.deepcopy(spec.params), seed)

    words = read_words(config.words)
    trie = TrieDict(words)
    records = []
    report = {
        "schema_version": 2, "complete": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config.model_dump(mode="json"),
        "dictionary_sha256": hashlib.sha256("\n".join(words).encode()).hexdigest(),
        "results": records, "summary": [],
    }
    if on_update:
        on_update(report)
    expected_deals: dict[int, list[str]] = {}
    for game_seed in config.seeds:
        for spec in config.agents:
            if progress:
                progress(f"Starting {spec.name}, deal seed {game_seed}")
            model = ForwardModelGriddle.new_game(config.size, seed=game_seed, trie_dict=trie)
            player = players.pop((game_seed, spec.name))
            seed = derived_seed(config.agent_seed, game_seed, spec.name)
            observation_rng = random.Random(derived_seed(seed, game_seed, "simulation"))
            moves, deal = [], []
            start = time.perf_counter()
            async def play():
                persistent = hasattr(player, "game_session") and hasattr(player, "get_action_async")
                async with AsyncExitStack() as stack:
                    if persistent:
                        await stack.enter_async_context(player.game_session())
                    while not model.is_terminal():
                        letter = model.state.current_letter
                        free = model.state.grid.get_free_indices()
                        observation = model.sample_future(observation_rng.getrandbits(64))
                        action = (await player.get_action_async(observation) if persistent
                                  else player.get_action(observation))
                        if type(action) is not int or not 0 <= action < len(free):
                            raise ValueError(f"{spec.name} returned invalid action {action!r} on seed {game_seed}")
                        index = free[action]
                        model.act(action)
                        deal.append(letter)
                        moves.append({"letter": letter, "action": action, "index": index})
                        if progress and spec.kind == "llm" and len(moves) % 5 == 0:
                            progress(f"{spec.name}, seed {game_seed}: {len(moves)}/{config.size**2} moves")
            try:
                asyncio.run(play())
            except Exception as error:
                report["failure"] = {"agent": spec.name, "game_seed": game_seed,
                                     "completed_moves": len(moves), "error": str(error)}
                if hasattr(player, "get_metrics"):
                    report["failure"]["agent_metrics"] = player.get_metrics()
                if on_update:
                    on_update(report)
                raise
            elapsed = time.perf_counter() - start
            if game_seed in expected_deals and deal != expected_deals[game_seed]:
                raise RuntimeError(f"agents received different deals for seed {game_seed}")
            expected_deals[game_seed] = deal
            record = {
                "agent": spec.name, "kind": spec.kind, "params": spec.params,
                "game_seed": game_seed, "agent_seed": seed,
                "score": model.score(), "elapsed_seconds": elapsed,
                "deal": "".join(deal), "moves": moves,
                "final_grid": "".join(model.state.grid.letters),
            }
            if hasattr(player, "get_metrics"):
                record["agent_metrics"] = player.get_metrics()
            records.append(record)
            report["summary"] = summarize(records)
            if on_update:
                on_update(report)
            if progress:
                progress(f"Finished {spec.name}, seed {game_seed}: score {record['score']}, {elapsed:.2f}s")
    report["complete"] = True
    if on_update:
        on_update(report)
    return report


def print_summary(report: dict) -> None:
    print(f"{'Agent':<24} {'Games':>5} {'Mean':>8} {'Std dev':>8} {'Min':>5} {'Max':>5} {'Seconds/game':>13}")
    for row in report["summary"]:
        print(f"{row['agent']:<24} {row['games']:>5} {row['mean_score']:>8.2f} "
              f"{row['stdev_score']:>8.2f} {row['min_score']:>5} {row['max_score']:>5} "
              f"{row['mean_seconds']:>13.2f}")
    for row in report["summary"]:
        if "total_model_calls" in row:
            cost = row["total_reported_cost_usd"]
            cost_text = "not fully reported" if cost is None else f"${cost:.6f}"
            print(f"{row['agent']}: {row['total_model_calls']} model requests, "
                  f"{row['total_tool_calls']} search attempts, "
                  f"{row['total_tool_errors']} tool errors/rejections, "
                  f"{row['total_invalid_moves']} invalid moves; API cost {cost_text}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Benchmark JSON configuration")
    parser.add_argument("--output", type=Path, required=True, help="Write complete JSON results here")
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env")

    def checkpoint(report):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)

    try:
        config = BenchmarkConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        # Dictionary paths in config files are relative to the configuration file.
        if config.words is not None:
            config = config.model_copy(update={"words": str((args.config.parent / config.words).resolve())})
        report = run_benchmark(config, progress=lambda message: print(message, flush=True), on_update=checkpoint)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Benchmark failed: {error}\n")
    print_summary(report)
    print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
