#!/usr/bin/env python3
"""Compute the comma-separated Ansible --tags value for `make bootstrap`.

The bootstrap sequence itself is executed by a single `ansible-playbook`
run (see ansible/playbook.yml) ; ce script se limite a selectionner le
sous-ensemble d'etapes (START_AT/STOP_AFTER) a passer en --tags.
"""
from __future__ import annotations

import argparse
import sys


def selected_steps(steps: list[str], start_at: str, stop_after: str) -> list[str]:
    if start_at:
        if start_at not in steps:
            sys.exit(f"START_AT invalide: {start_at}. Etapes valides: {', '.join(steps)}")
        steps = steps[steps.index(start_at):]
    if stop_after:
        if stop_after not in steps:
            sys.exit(f"STOP_AFTER invalide: {stop_after}. Etapes valides: {', '.join(steps)}")
        steps = steps[: steps.index(stop_after) + 1]
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-at", default="")
    parser.add_argument("--stop-after", default="")
    parser.add_argument("steps", nargs="+")
    args = parser.parse_args()

    steps = selected_steps(args.steps, args.start_at, args.stop_after)
    print(",".join(steps))


if __name__ == "__main__":
    main()
