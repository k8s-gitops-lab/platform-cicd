#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def selected_steps(steps: list[str], start_at: str, stop_after: str) -> list[str]:
    if start_at:
        if start_at not in steps:
            sys.exit(f"START_AT invalide: {start_at}. Etapes valides: {', '.join(steps)}")
        steps = steps[steps.index(start_at) :]
    if stop_after:
        if stop_after not in steps:
            sys.exit(f"STOP_AFTER invalide: {stop_after}. Etapes valides: {', '.join(steps)}")
        steps = steps[: steps.index(stop_after) + 1]
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bootstrap steps with resume support.")
    parser.add_argument("--make", default="make")
    parser.add_argument("--start-at", default="")
    parser.add_argument("--stop-after", default="")
    parser.add_argument("steps", nargs="+")
    args = parser.parse_args()

    steps = selected_steps(args.steps, args.start_at, args.stop_after)
    print("Bootstrap steps:", " -> ".join(steps))
    for step in steps:
        print(f"==> bootstrap-step: {step}")
        subprocess.run([args.make, step], check=True)


if __name__ == "__main__":
    main()
