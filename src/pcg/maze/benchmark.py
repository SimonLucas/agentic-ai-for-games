"""Compare maze generators on fixed generation briefs."""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from random import Random
import statistics
import time
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from .contact_sheet import ContactSheetEntry, render_contact_sheet
from .diversity import diversity_metrics
from .evolution import EvolutionConfig, run_evolution
from .agentic_generator import AgenticMazeError, AgenticMazeGenerator, AgenticMazeParams
from .llm_generator import (
    LLMMazeGenerator,
    LLMMazeOutputError,
    LLMMazeParams,
    displayable_rows,
    maze_text,
)
from .model import Maze, evaluate_maze


class GeneratorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    kind: Literal["random", "evolution", "llm", "agentic_llm"]
    params: dict[str, JsonValue] = Field(default_factory=dict)


class MazeBenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width: int = Field(default=12, ge=2)
    height: int = Field(default=8, ge=2)
    seeds: list[StrictInt] = Field(min_length=2)
    agents: list[GeneratorSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_values(self) -> "MazeBenchmarkConfig":
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("generation seeds must be unique")
        names = [agent.name for agent in self.agents]
        if len(set(names)) != len(names):
            raise ValueError("agent names must be unique")
        return self


class RandomMazeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_probability: float = Field(default=0.25, ge=0, le=1)


class EvolutionMazeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iterations: Annotated[StrictInt, Field(ge=0)] = 2_000
    expected_mutations: float = Field(default=5.0, gt=0)
    initial_wall_probability: float = Field(default=0.0, ge=0, le=1)


def random_maze(width: int, height: int, seed: int, params: RandomMazeParams) -> Maze:
    random = Random(seed)
    walls = [random.random() < params.wall_probability for _ in range(width * height)]
    walls[0] = walls[-1] = False
    return Maze(width=width, height=height, walls=tuple(walls))


def summarize(records: list[dict], agents: list[GeneratorSpec]) -> list[dict]:
    rows = []
    for agent in agents:
        generated = [record for record in records if record["agent"] == agent.name]
        valid = [record for record in generated if record["status"] == "ok"]
        fitnesses = [record["fitness"] for record in valid]
        row = {
            "agent": agent.name,
            "kind": agent.kind,
            "attempted": len(generated),
            "failed": len(generated) - len(valid),
            "mean_fitness": statistics.mean(fitnesses) if fitnesses else None,
            "max_fitness": max(fitnesses) if fitnesses else None,
            "mean_wall_fraction": (
                statistics.mean(record["wall_fraction"] for record in valid)
                if valid else None
            ),
            "mean_seconds": (
                statistics.mean(record["elapsed_seconds"] for record in generated)
                if generated else None
            ),
            **diversity_metrics([record["maze_text"] for record in valid]),
        }
        model_metrics = [record.get("model_metrics") for record in generated]
        model_metrics = [metrics for metrics in model_metrics if metrics]
        if model_metrics:
            row["total_model_calls"] = sum(metrics["model_calls"] for metrics in model_metrics)
            row["total_tool_calls"] = sum(
                metrics.get("tool_calls", 0) for metrics in model_metrics
            )
            row["total_tool_errors"] = sum(
                metrics.get("tool_errors", 0) for metrics in model_metrics
            )
            row["total_mcp_process_starts"] = sum(
                metrics.get("mcp_process_starts", 0) for metrics in model_metrics
            )
            row["total_http_client_starts"] = sum(
                metrics.get("http_client_starts", 0) for metrics in model_metrics
            )
            row["total_prompt_tokens"] = sum(
                metrics["prompt_tokens"] or 0 for metrics in model_metrics
            )
            row["total_completion_tokens"] = sum(
                metrics["completion_tokens"] or 0 for metrics in model_metrics
            )
        rows.append(row)
    return rows


def _record(
    agent: GeneratorSpec,
    seed: int,
    elapsed: float,
    maze: Maze | None,
    *,
    model_metrics: dict | None = None,
    error: str | None = None,
    candidate_rows: list[str] | None = None,
) -> dict:
    record = {
        "agent": agent.name,
        "kind": agent.kind,
        "params": agent.params,
        "seed": seed,
        "elapsed_seconds": elapsed,
    }
    if maze is not None:
        text = maze_text(maze)
        evaluation = evaluate_maze(maze)
        record.update({
            "maze_text": text,
            "rows": text.splitlines(),
            "fitness": evaluation.fitness,
            "path": [list(cell) for cell in evaluation.path],
            "wall_fraction": sum(maze.walls) / len(maze.walls),
        })
        if evaluation.connected and error is None:
            record["status"] = "ok"
        else:
            record["status"] = "failed"
            record["error"] = error or "maze has no route from start to goal"
    else:
        record.update({"status": "failed", "error": error or "generation failed"})
        if candidate_rows is not None:
            record["rows"] = candidate_rows
            record["maze_text"] = "\n".join(candidate_rows)
    if model_metrics is not None:
        record["model_metrics"] = model_metrics
    return record


async def run_benchmark(
    config: MazeBenchmarkConfig,
    *,
    progress=None,
    on_update=None,
) -> dict:
    records: list[dict] = []
    report = {
        "schema_version": 1,
        "complete": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config.model_dump(mode="json"),
        "results": records,
        "summary": [],
        "diversity_note": (
            "gzip measures the valid mazes in fixed seed order; compare bytes only "
            "between sets with equal dimensions, encoding and valid counts"
        ),
    }
    if on_update:
        on_update(report)

    for agent in config.agents:
        previous_maze_texts: list[str] = []
        llm = LLMMazeGenerator(LLMMazeParams.model_validate(agent.params)) \
            if agent.kind == "llm" else None
        agentic = AgenticMazeGenerator(AgenticMazeParams.model_validate(agent.params)) \
            if agent.kind == "agentic_llm" else None
        if llm is not None:
            client_context = llm.client()
        elif agentic is not None:
            client_context = agentic.generation_session()
        else:
            client_context = _NullAsyncContext()
        async with client_context as client:
            for seed in config.seeds:
                if progress:
                    progress(f"Starting {agent.name}, seed {seed}")
                start = time.perf_counter()
                maze = None
                model_metrics = None
                candidate_rows = None
                error = None
                try:
                    if agent.kind == "random":
                        params = RandomMazeParams.model_validate(agent.params)
                        maze = random_maze(config.width, config.height, seed, params)
                    elif agent.kind == "evolution":
                        params = EvolutionMazeParams.model_validate(agent.params)
                        evolution = run_evolution(EvolutionConfig(
                            width=config.width,
                            height=config.height,
                            iterations=params.iterations,
                            expected_mutations=params.expected_mutations,
                            initial_wall_probability=params.initial_wall_probability,
                            seed=seed,
                        ))
                        maze = evolution.final.maze
                    elif agent.kind == "llm":
                        maze, model_metrics = await llm.generate(
                            client,
                            width=config.width,
                            height=config.height,
                            seed=seed,
                            previous_maze_texts=previous_maze_texts,
                        )
                    else:
                        maze, model_metrics = await agentic.generate(
                            width=config.width,
                            height=config.height,
                            seed=seed,
                            previous_maze_texts=previous_maze_texts,
                        )
                except LLMMazeOutputError as exception:
                    error = str(exception)
                    model_metrics = exception.metrics
                    candidate_rows = exception.rows
                except AgenticMazeError as exception:
                    error = str(exception)
                    model_metrics = exception.metrics
                    candidate_rows = exception.rows
                except Exception as exception:
                    error = str(exception)
                elapsed = time.perf_counter() - start
                record = _record(
                    agent,
                    seed,
                    elapsed,
                    maze,
                    model_metrics=model_metrics,
                    error=error,
                    candidate_rows=candidate_rows,
                )
                records.append(record)
                if record["status"] == "ok":
                    previous_maze_texts.append(record["maze_text"])
                report["summary"] = summarize(records, config.agents)
                if on_update:
                    on_update(report)
                if progress:
                    outcome = (
                        f"fitness {record['fitness']}" if record["status"] == "ok"
                        else f"failed: {record['error']}"
                    )
                    progress(f"Finished {agent.name}, seed {seed}: {outcome}")
    report["complete"] = True
    if on_update:
        on_update(report)
    return report


class _NullAsyncContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def write_summary_csv(summary: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in summary for key in row))
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)


def write_contact_sheet(report: dict, output: Path, columns: int = 4) -> None:
    entries = []
    width = report["config"]["width"]
    height = report["config"]["height"]
    for record in report["results"]:
        rows = record.get("rows")
        if rows is None and record.get("model_metrics", {}).get("raw_response"):
            rows = displayable_rows(
                record["model_metrics"]["raw_response"], width, height
            )
        label = f"{record['agent']}\nseed {record['seed']}"
        if record["status"] == "ok":
            label += f" · fitness {record['fitness']}"
        else:
            label += " · FAILED"
        entries.append(ContactSheetEntry(
            label=label,
            rows=tuple(rows) if rows is not None else None,
            path=tuple(tuple(cell) for cell in record.get("path", [])),
            failed=record["status"] != "ok",
        ))
    render_contact_sheet(
        entries,
        output,
        width=width,
        height=height,
        columns=columns,
    )


def print_summary(report: dict) -> None:
    print(
        f"{'Agent':<22} {'Valid':>7} {'Mean fit':>9} {'Max':>5} "
        f"{'Gzip B':>8} {'Ratio':>7} {'Hamming':>8} {'Sec/maze':>9}"
    )
    for row in report["summary"]:
        valid = f"{row['valid_maze_count']}/{row['attempted']}"
        values = {
            "mean": "—" if row["mean_fitness"] is None else f"{row['mean_fitness']:.1f}",
            "max": "—" if row["max_fitness"] is None else str(row["max_fitness"]),
            "ratio": "—" if row["gzip_ratio"] is None else f"{row['gzip_ratio']:.3f}",
            "hamming": (
                "—" if row["mean_pairwise_hamming"] is None
                else f"{row['mean_pairwise_hamming']:.3f}"
            ),
        }
        print(
            f"{row['agent']:<22} {valid:>7} {values['mean']:>9} "
            f"{values['max']:>5} {row['gzip_bytes']:>8} {values['ratio']:>7} "
            f"{values['hamming']:>8} {row['mean_seconds']:>9.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path)
    parser.add_argument("--sheet", type=Path)
    parser.add_argument("--sheet-columns", type=int, default=4)
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env")

    def checkpoint(report):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)

    try:
        config = MazeBenchmarkConfig.model_validate_json(
            args.config.read_text(encoding="utf-8")
        )
        report = asyncio.run(run_benchmark(
            config,
            progress=lambda message: print(message, flush=True),
            on_update=checkpoint,
        ))
        if args.summary_csv:
            write_summary_csv(report["summary"], args.summary_csv)
        if args.sheet:
            write_contact_sheet(report, args.sheet, args.sheet_columns)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Benchmark failed: {error}\n")
    print_summary(report)
    print(f"Results written to {args.output}")
    if args.sheet:
        print(f"Contact sheet written to {args.sheet}")


if __name__ == "__main__":
    main()
