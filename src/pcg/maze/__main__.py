"""Command-line entry point for the evolutionary maze example."""

from __future__ import annotations

import argparse
from pathlib import Path

from .evolution import EvolutionConfig, run_evolution
from .svg import render_evolution_svg


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("mode", nargs="?", choices=("render", "live"), default="render")
    command.add_argument("--width", type=int, default=20)
    command.add_argument("--height", type=int, default=10)
    command.add_argument("--iterations", type=int, default=5_000)
    command.add_argument("--expected-mutations", type=float, default=5.0)
    command.add_argument("--initial-wall-probability", type=float, default=0.0)
    command.add_argument("--seed", type=int, default=0)
    command.add_argument("--frames", type=int, default=8)
    command.add_argument("--columns", type=int, default=4)
    command.add_argument("--output", type=Path, default=Path("results/pcg/maze_evolution.svg"))
    command.add_argument("--steps-per-frame", type=int, default=10)
    command.add_argument("--delay-ms", type=int, default=40)
    return command


def main() -> None:
    args = parser().parse_args()
    config = EvolutionConfig(
        width=args.width,
        height=args.height,
        iterations=args.iterations,
        expected_mutations=args.expected_mutations,
        initial_wall_probability=args.initial_wall_probability,
        seed=args.seed,
    )
    if args.mode == "live":
        from .live import run_live

        run_live(
            config,
            steps_per_frame=args.steps_per_frame,
            delay_ms=args.delay_ms,
        )
        return

    result = run_evolution(config)
    svg = render_evolution_svg(result, max_frames=args.frames, columns=args.columns)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(
        f"fitness {result.initial.evaluation.fitness} -> "
        f"{result.final.evaluation.fitness}; {result.accepted_moves} accepted moves"
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
