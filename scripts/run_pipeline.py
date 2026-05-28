"""Run the full pipeline end to end: generate -> forecast -> erlang -> anomaly -> validate."""

from __future__ import annotations

import subprocess
import sys

STEPS = [
    [sys.executable, "scripts/generate_data.py"],
    [sys.executable, "scripts/forecast.py"],
    [sys.executable, "scripts/erlang.py"],
    [sys.executable, "scripts/anomaly.py"],
    [sys.executable, "scripts/validate.py"],
    [sys.executable, "scripts/verify_measures.py"],
    [sys.executable, "scripts/build_dashboard.py"],
]


def main() -> None:
    for step in STEPS:
        print(f"\n=== {' '.join(step)} ===")
        subprocess.run(step, check=True)


if __name__ == "__main__":
    main()
