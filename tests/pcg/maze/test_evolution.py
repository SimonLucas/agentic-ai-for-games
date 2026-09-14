from pcg.maze import EvolutionConfig, run_evolution
from pcg.maze.evolution import MazeEvolution
from pcg.maze.svg import render_evolution_svg, select_snapshots


def test_seed_reproduces_the_same_run() -> None:
    config = EvolutionConfig(width=8, height=6, iterations=150, seed=42)

    first = run_evolution(config)
    second = run_evolution(config)

    assert first.final == second.final
    assert first.accepted_moves == second.accepted_moves
    assert first.improvements == second.improvements


def test_evolution_preserves_endpoints_and_never_loses_fitness() -> None:
    config = EvolutionConfig(width=8, height=6, iterations=200, seed=7)
    observed_fitness: list[int] = []

    result = run_evolution(
        config,
        on_step=lambda step: observed_fitness.append(step.incumbent_evaluation.fitness),
    )

    assert observed_fitness == sorted(observed_fitness)
    assert result.final.evaluation.fitness >= result.initial.evaluation.fitness
    assert not result.final.maze.is_wall(result.final.maze.start)
    assert not result.final.maze.is_wall(result.final.maze.goal)


def test_mutation_flips_selected_cells_and_keeps_endpoints_open() -> None:
    config = EvolutionConfig(
        width=3,
        height=2,
        iterations=1,
        expected_mutations=4,
        seed=1,
    )
    evolution = MazeEvolution(config)

    mutated = evolution.mutate(evolution.incumbent)

    assert mutated.walls == (False, True, True, True, True, False)


def test_svg_shows_a_sampled_history_and_fitness() -> None:
    result = run_evolution(EvolutionConfig(width=6, height=4, iterations=100, seed=3))

    selected = select_snapshots(result.improvements, max_frames=4)
    svg = render_evolution_svg(result, max_frames=4, columns=2)

    assert selected[0] == result.improvements[0]
    assert selected[-1] == result.improvements[-1]
    assert "fitness" in svg
    assert "iteration" in svg
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in svg
    assert ">S</text>" in svg
    assert ">G</text>" in svg
