"""Stateful MCP server for agent-directed maze editing."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field, StrictInt

from .workshop import MazeWorkshop

BatchSize = Annotated[StrictInt, Field(ge=1, le=64)]
BlockSize = Annotated[StrictInt, Field(ge=1, le=20)]


def create_server() -> FastMCP:
    server = FastMCP("maze-workshop", log_level="WARNING")
    workshop = MazeWorkshop()

    @server.tool()
    def configure(
        initial: dict,
        library: list[dict],
        seed: int,
        max_batch_size: BatchSize = 32,
    ) -> dict:
        """Host-only setup. Never offered to the language model."""
        return workshop.configure(initial, library, seed, max_batch_size)

    @server.tool()
    def export() -> dict:
        """Host-only final-state export. Never offered to the language model."""
        return workshop.export()

    @server.tool()
    def status() -> dict:
        """Inspect the current maze, including its grid, fitness and connectivity."""
        return workshop.status()

    @server.tool()
    def mutate_batch(
        batch_size: BatchSize = 12,
        expected_mutations: float = 5.0,
    ) -> dict:
        """Create and score local bit-flip mutations of the current maze.

        Returns up to eight best candidates with IDs. It does not adopt one.
        """
        return workshop.mutate_batch(batch_size, expected_mutations)

    @server.tool()
    def macro_mutation_batch(
        batch_size: BatchSize = 12,
        min_block_size: BlockSize = 2,
        max_block_size: BlockSize = 5,
    ) -> dict:
        """Copy rectangular blocks from evolved library mazes into candidates.

        Random source and target rectangles create large structural changes.
        Returns scored candidate IDs and does not adopt one.
        """
        return workshop.macro_mutation_batch(
            batch_size, min_block_size, max_block_size
        )

    @server.tool()
    def repair(candidate_id: str = "current") -> dict:
        """Carve the fewest walls needed to connect one candidate's endpoints.

        Returns a new scored candidate ID and does not adopt it.
        """
        return workshop.repair(candidate_id)

    @server.tool()
    def adopt(candidate_id: str) -> dict:
        """Replace the current maze with a candidate chosen by ID."""
        return workshop.adopt(candidate_id)

    return server


if __name__ == "__main__":
    create_server().run(transport="stdio")
