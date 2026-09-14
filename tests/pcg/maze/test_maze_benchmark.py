import asyncio

from PIL import Image

from pcg.maze.benchmark import (
    MazeBenchmarkConfig,
    run_benchmark,
    write_contact_sheet,
    write_summary_csv,
)
from pcg.maze.diversity import diversity_metrics


def test_gzip_and_hamming_distinguish_repetition_from_variety() -> None:
    repeated = ["........\n........"] * 20
    varied = [
        f"{number:016b}".replace("0", ".").replace("1", "#")[:8]
        + "\n"
        + f"{number:016b}".replace("0", ".").replace("1", "#")[8:]
        for number in range(20)
    ]

    repeated_metrics = diversity_metrics(repeated)
    varied_metrics = diversity_metrics(varied)

    assert repeated_metrics["unique_maze_count"] == 1
    assert varied_metrics["unique_maze_count"] == 20
    assert repeated_metrics["gzip_bytes"] < varied_metrics["gzip_bytes"]
    assert repeated_metrics["mean_pairwise_hamming"] == 0
    assert varied_metrics["mean_pairwise_hamming"] > 0


def test_local_benchmark_writes_summary_and_contact_sheet(tmp_path) -> None:
    config = MazeBenchmarkConfig.model_validate({
        "width": 6,
        "height": 4,
        "seeds": [0, 1],
        "agents": [{
            "name": "evolution",
            "kind": "evolution",
            "params": {"iterations": 100, "expected_mutations": 3},
        }],
    })

    report = asyncio.run(run_benchmark(config))
    csv_path = tmp_path / "summary.csv"
    png_path = tmp_path / "sheet.png"
    write_summary_csv(report["summary"], csv_path)
    write_contact_sheet(report, png_path, columns=2)

    assert report["complete"]
    assert len(report["results"]) == 2
    assert report["summary"][0]["valid_maze_count"] == 2
    assert csv_path.read_text().startswith("agent,kind")
    with Image.open(png_path) as image:
        assert image.format == "PNG"
        assert image.width > image.height
