"""A seeded (1+1) evolutionary algorithm for maze generation."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .model import Maze, MazeEvaluation, evaluate_maze


class EvolutionConfig(BaseModel):
    """Parameters for a reproducible evolutionary run."""

    model_config = ConfigDict(frozen=True)

    width: int = Field(default=20, ge=2)
    height: int = Field(default=10, ge=2)
    iterations: int = Field(default=5_000, ge=0)
    expected_mutations: float = Field(default=5.0, gt=0)
    initial_wall_probability: float = Field(default=0.0, ge=0, le=1)
    seed: int = 0

    @model_validator(mode="after")
    def validate_mutation_budget(self) -> "EvolutionConfig":
        if self.expected_mutations > self.width * self.height - 2:
            raise ValueError("expected_mutations cannot exceed mutable cells")
        return self


@dataclass(frozen=True, slots=True)
class MazeSnapshot:
    iteration: int
    maze: Maze
    evaluation: MazeEvaluation


@dataclass(frozen=True, slots=True)
class EvolutionStep:
    iteration: int
    proposal: Maze
    proposal_evaluation: MazeEvaluation
    incumbent: Maze
    incumbent_evaluation: MazeEvaluation
    accepted: bool
    improved: bool


@dataclass(frozen=True, slots=True)
class EvolutionResult:
    config: EvolutionConfig
    initial: MazeSnapshot
    final: MazeSnapshot
    improvements: tuple[MazeSnapshot, ...]
    accepted_moves: int


class MazeEvolution:
    """Stateful engine used by batch runs and the live animation."""

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.random = Random(config.seed)
        self.iteration = 0
        self.accepted_moves = 0
        self.incumbent = self._initial_maze()
        self.incumbent_evaluation = evaluate_maze(self.incumbent)

    def _initial_maze(self) -> Maze:
        count = self.config.width * self.config.height
        walls = tuple(
            self.random.random() < self.config.initial_wall_probability
            for _ in range(count)
        )
        mutable = list(walls)
        mutable[0] = False
        mutable[-1] = False
        return Maze(
            width=self.config.width,
            height=self.config.height,
            walls=tuple(mutable),
        )

    def mutate(self, maze: Maze) -> Maze:
        walls = list(maze.walls)
        mutable_cells = len(walls) - 2
        probability = min(1.0, self.config.expected_mutations / mutable_cells)
        for index in range(1, len(walls) - 1):
            if self.random.random() < probability:
                walls[index] = not walls[index]
        return maze.model_copy(update={"walls": tuple(walls)})

    def step(self) -> EvolutionStep:
        self.iteration += 1
        proposal = self.mutate(self.incumbent)
        proposal_evaluation = evaluate_maze(proposal)
        old_fitness = self.incumbent_evaluation.fitness
        accepted = proposal_evaluation.fitness >= old_fitness
        improved = proposal_evaluation.fitness > old_fitness
        if accepted:
            self.incumbent = proposal
            self.incumbent_evaluation = proposal_evaluation
            self.accepted_moves += 1
        return EvolutionStep(
            iteration=self.iteration,
            proposal=proposal,
            proposal_evaluation=proposal_evaluation,
            incumbent=self.incumbent,
            incumbent_evaluation=self.incumbent_evaluation,
            accepted=accepted,
            improved=improved,
        )


def run_evolution(
    config: EvolutionConfig,
    on_step: Callable[[EvolutionStep], None] | None = None,
) -> EvolutionResult:
    """Run an experiment, retaining strict improvements for visualisation."""

    evolution = MazeEvolution(config)
    initial = MazeSnapshot(0, evolution.incumbent, evolution.incumbent_evaluation)
    improvements = [initial]

    for _ in range(config.iterations):
        step = evolution.step()
        if step.improved:
            improvements.append(
                MazeSnapshot(step.iteration, step.incumbent, step.incumbent_evaluation)
            )
        if on_step is not None:
            on_step(step)

    final = MazeSnapshot(
        evolution.iteration, evolution.incumbent, evolution.incumbent_evaluation
    )
    if improvements[-1].iteration != final.iteration:
        improvements.append(final)
    return EvolutionResult(
        config=config,
        initial=initial,
        final=final,
        improvements=tuple(improvements),
        accepted_moves=evolution.accepted_moves,
    )
