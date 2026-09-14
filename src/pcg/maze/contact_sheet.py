"""PNG contact sheets for comparing valid and failed maze generations."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw

from .model import Cell


@dataclass(frozen=True, slots=True)
class ContactSheetEntry:
    label: str
    rows: tuple[str, ...] | None
    path: tuple[Cell, ...] = ()
    failed: bool = False


def render_contact_sheet(
    entries: list[ContactSheetEntry],
    output: Path,
    *,
    width: int,
    height: int,
    columns: int = 4,
    cell_size: int = 12,
) -> None:
    if not entries:
        raise ValueError("contact sheet needs at least one entry")
    columns = max(1, min(columns, len(entries)))
    sheet_rows = ceil(len(entries) / columns)
    margin, gutter, label_height = 20, 24, 46
    maze_width = width * cell_size
    maze_height = height * cell_size
    panel_width = maze_width + gutter
    panel_height = maze_height + label_height
    image = Image.new(
        "RGB",
        (
            margin * 2 + columns * panel_width - gutter,
            margin * 2 + sheet_rows * panel_height,
        ),
        "#f7f5ef",
    )
    draw = ImageDraw.Draw(image)
    for index, entry in enumerate(entries):
        x0 = margin + (index % columns) * panel_width
        y0 = margin + (index // columns) * panel_height
        label_colour = "#c62828" if entry.failed else "#1f2933"
        draw.text((x0, y0), entry.label, fill=label_colour)
        grid_y = y0 + 30
        if entry.rows is None:
            draw.rectangle(
                (x0, grid_y, x0 + maze_width, grid_y + maze_height),
                fill="#eceff1",
                outline="#c62828",
                width=2,
            )
            draw.text((x0 + 8, grid_y + 8), "no readable grid", fill="#c62828")
            continue
        path = set(entry.path)
        for y in range(height):
            for x in range(width):
                character = entry.rows[y][x]
                colour = {
                    "#": "#263238",
                    ".": "#fffdf5",
                    "P": "#ffd180",
                }.get(character, "#ef9a9a")
                if (x, y) in path:
                    colour = "#9bd7ff"
                box = (
                    x0 + x * cell_size,
                    grid_y + y * cell_size,
                    x0 + (x + 1) * cell_size,
                    grid_y + (y + 1) * cell_size,
                )
                draw.rectangle(box, fill=colour, outline="#b0bec5", width=1)
        for (x, y), colour in (
            ((0, 0), "#2e7d32"),
            ((width - 1, height - 1), "#c62828"),
        ):
            inset = max(1, cell_size // 6)
            draw.ellipse(
                (
                    x0 + x * cell_size + inset,
                    grid_y + y * cell_size + inset,
                    x0 + (x + 1) * cell_size - inset,
                    grid_y + (y + 1) * cell_size - inset,
                ),
                outline=colour,
                width=2,
            )
        if entry.failed:
            draw.rectangle(
                (x0, grid_y, x0 + maze_width, grid_y + maze_height),
                outline="#c62828",
                width=2,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
