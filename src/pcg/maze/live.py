"""Tkinter animation for watching mutation and selection."""

from __future__ import annotations

from .evolution import EvolutionConfig, EvolutionStep, MazeEvolution
from .model import Maze, MazeEvaluation


def run_live(
    config: EvolutionConfig,
    *,
    steps_per_frame: int = 10,
    delay_ms: int = 40,
    cell_size: int = 24,
) -> None:
    """Open a window showing the latest proposal and accepted incumbent."""

    import tkinter as tk

    evolution = MazeEvolution(config)
    pad = 20
    maze_width = config.width * cell_size
    maze_height = config.height * cell_size
    canvas = tk.Canvas(
        width=maze_width * 2 + pad * 3,
        height=maze_height + 100,
        bg="#f7f5ef",
        highlightthickness=0,
    )
    canvas.pack()
    root = canvas.winfo_toplevel()
    root.title("Evolutionary maze — live run")

    def draw_maze(maze: Maze, evaluation: MazeEvaluation, x0: int, y0: int) -> None:
        path = set(evaluation.path)
        for y in range(maze.height):
            for x in range(maze.width):
                cell = (x, y)
                colour = "#263238" if maze.is_wall(cell) else "#fffdf5"
                if cell in path:
                    colour = "#9bd7ff"
                canvas.create_rectangle(
                    x0 + x * cell_size,
                    y0 + y * cell_size,
                    x0 + (x + 1) * cell_size,
                    y0 + (y + 1) * cell_size,
                    fill=colour,
                    outline="#b0bec5",
                )
        for cell, colour, label in (
            (maze.start, "#2e7d32", "S"),
            (maze.goal, "#c62828", "G"),
        ):
            x, y = cell
            cx = x0 + (x + 0.5) * cell_size
            cy = y0 + (y + 0.5) * cell_size
            radius = cell_size * 0.34
            canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius,
                fill=colour, outline="",
            )
            canvas.create_text(
                cx, cy, text=label, fill="white", font=("Arial", 10, "bold")
            )

    def redraw(last_step: EvolutionStep | None = None) -> None:
        canvas.delete("all")
        if last_step is None:
            proposal = evolution.incumbent
            proposal_eval = evolution.incumbent_evaluation
            status = "initial maze"
        else:
            proposal = last_step.proposal
            proposal_eval = last_step.proposal_evaluation
            status = "accepted" if last_step.accepted else "rejected"
        canvas.create_text(
            pad,
            18,
            anchor="w",
            text="Latest mutation",
            font=("Arial", 15, "bold"),
        )
        canvas.create_text(
            maze_width + pad * 2, 18, anchor="w", text="Current incumbent",
            font=("Arial", 15, "bold"),
        )
        draw_maze(proposal, proposal_eval, pad, 38)
        draw_maze(
            evolution.incumbent,
            evolution.incumbent_evaluation,
            maze_width + pad * 2,
            38,
        )
        canvas.create_text(
            pad,
            maze_height + 62,
            anchor="w",
            text=(
                f"iteration {evolution.iteration:,} · proposal fitness "
                f"{proposal_eval.fitness} · {status}"
            ),
            fill="#37474f",
        )
        canvas.create_text(
            maze_width + pad * 2,
            maze_height + 62,
            anchor="w",
            text=(
                f"fitness {evolution.incumbent_evaluation.fitness} · "
                f"accepted {evolution.accepted_moves}"
            ),
            fill="#37474f",
        )

    def advance() -> None:
        last_step = None
        for _ in range(steps_per_frame):
            if evolution.iteration >= config.iterations:
                break
            last_step = evolution.step()
        redraw(last_step)
        if evolution.iteration < config.iterations:
            root.after(delay_ms, advance)

    redraw()
    root.after(delay_ms, advance)
    root.mainloop()
