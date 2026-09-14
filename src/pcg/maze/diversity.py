"""Set-level diversity measures for fixed-size text mazes."""

from __future__ import annotations

import gzip
import itertools
import statistics


def diversity_metrics(maze_texts: list[str]) -> dict:
    """Measure compressibility and structural difference across a maze set."""

    if not maze_texts:
        return {
            "valid_maze_count": 0,
            "unique_maze_count": 0,
            "gzip_bytes": 0,
            "uncompressed_bytes": 0,
            "gzip_ratio": None,
            "mean_pairwise_hamming": None,
        }
    encoded = "\n\n".join(maze_texts).encode("ascii")
    compressed = gzip.compress(encoded, compresslevel=9, mtime=0)
    flattened = [text.replace("\n", "") for text in maze_texts]
    distances = [
        sum(left != right for left, right in zip(first, second, strict=True))
        / len(first)
        for first, second in itertools.combinations(flattened, 2)
    ]
    return {
        "valid_maze_count": len(maze_texts),
        "unique_maze_count": len(set(maze_texts)),
        "gzip_bytes": len(compressed),
        "uncompressed_bytes": len(encoded),
        "gzip_ratio": len(compressed) / len(encoded),
        "mean_pairwise_hamming": statistics.mean(distances) if distances else 0.0,
    }
