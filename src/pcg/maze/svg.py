"""Dependency-free SVG rendering for evolutionary runs."""

from __future__ import annotations

from html import escape
from math import ceil

from .evolution import EvolutionResult, MazeSnapshot
from .model import Maze, MazeEvaluation


def select_snapshots(
    snapshots: tuple[MazeSnapshot, ...], max_frames: int
) -> tuple[MazeSnapshot, ...]:
    """Evenly sample milestones while retaining the first and final states."""

    if max_frames < 2:
        raise ValueError("max_frames must be at least 2")
    if len(snapshots) <= max_frames:
        return snapshots
    indexes = {
        round(index * (len(snapshots) - 1) / (max_frames - 1))
        for index in range(max_frames)
    }
    return tuple(snapshots[index] for index in sorted(indexes))


def maze_svg_elements(
    maze: Maze,
    evaluation: MazeEvaluation,
    origin_x: float,
    origin_y: float,
    cell_size: float,
) -> str:
    parts: list[str] = []
    path_cells = set(evaluation.path)
    for y in range(maze.height):
        for x in range(maze.width):
            cell = (x, y)
            fill = "#263238" if maze.is_wall(cell) else "#fffdf5"
            if cell in path_cells:
                fill = "#9bd7ff"
            parts.append(
                f'<rect x="{origin_x + x * cell_size:g}" '
                f'y="{origin_y + y * cell_size:g}" width="{cell_size:g}" '
                f'height="{cell_size:g}" fill="{fill}" stroke="#b0bec5" '
                'stroke-width="0.6"/>'
            )
    if evaluation.path:
        points = " ".join(
            f"{origin_x + (x + 0.5) * cell_size:g},"
            f"{origin_y + (y + 0.5) * cell_size:g}"
            for x, y in evaluation.path
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#1565c0" '
            f'stroke-width="{max(1.5, cell_size * 0.22):g}" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    for cell, colour, label in (
        (maze.start, "#2e7d32", "S"),
        (maze.goal, "#c62828", "G"),
    ):
        x, y = cell
        cx = origin_x + (x + 0.5) * cell_size
        cy = origin_y + (y + 0.5) * cell_size
        parts.append(
            f'<circle cx="{cx:g}" cy="{cy:g}" r="{cell_size * 0.34:g}" '
            f'fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{cx:g}" y="{cy:g}" text-anchor="middle" '
            f'dominant-baseline="central" fill="white" font-size="{cell_size * 0.5:g}" '
            f'font-weight="700">{label}</text>'
        )
    return "\n".join(parts)


def render_evolution_svg(
    result: EvolutionResult,
    *,
    max_frames: int = 8,
    columns: int = 4,
    cell_size: int = 16,
    title: str = "Evolution of a longest-shortest-path maze",
) -> str:
    snapshots = select_snapshots(result.improvements, max_frames)
    columns = max(1, min(columns, len(snapshots)))
    rows = ceil(len(snapshots) / columns)
    maze_width = result.config.width * cell_size
    maze_height = result.config.height * cell_size
    gutter = 28
    label_height = 42
    margin = 24
    header = 60
    panel_width = maze_width + gutter
    panel_height = maze_height + label_height
    width = margin * 2 + columns * panel_width - gutter
    height = header + margin + rows * panel_height
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f5ef"/>',
        f'<text x="{margin}" y="28" font-family="sans-serif" font-size="20" '
        f'font-weight="700" fill="#1f2933">{escape(title)}</text>',
        f'<text x="{margin}" y="49" font-family="sans-serif" font-size="12" '
        f'fill="#52606d">seed {result.config.seed} · {result.config.iterations} attempts · '
        f'{result.accepted_moves} accepted moves · blue shows one shortest path</text>',
    ]
    for index, snapshot in enumerate(snapshots):
        column = index % columns
        row = index // columns
        x = margin + column * panel_width
        y = header + row * panel_height
        parts.append(
            maze_svg_elements(snapshot.maze, snapshot.evaluation, x, y, cell_size)
        )
        parts.append(
            f'<text x="{x:g}" y="{y + maze_height + 20:g}" '
            'font-family="sans-serif" font-size="13" fill="#1f2933">'
            f'iteration {snapshot.iteration:,} · fitness {snapshot.evaluation.fitness}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
