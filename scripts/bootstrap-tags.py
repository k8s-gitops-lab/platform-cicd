#!/usr/bin/env python3
"""Compute the comma-separated Ansible --tags value for `make bootstrap`.

The bootstrap sequence itself is executed by a single `ansible-playbook`
run (see ansible/playbook.yml) ; ce script se limite a selectionner le
sous-ensemble d'etapes (START_AT/STOP_AFTER) a passer en --tags.

L'ordre des etapes n'est plus recopie a la main ici : il est lu directement
depuis le tag de chaque tache de premier niveau du role platform_bootstrap
(infrastructure/ansible/roles/platform_bootstrap/tasks/main.yml), qui reste
l'unique source de verite pour l'ordre d'execution reel.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def read_role_tags(tasks_file: Path) -> list[str]:
    tasks = yaml.safe_load(tasks_file.read_text()) or []
    steps: list[str] = []
    for task in tasks:
        tags = task.get("tags") or []
        if not tags:
            sys.exit(f"Tache sans tag dans {tasks_file}: {task.get('name', '<sans nom>')}")
        steps.append(tags[0])
    return steps


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
    parser.add_argument("--tasks-file", required=True,
                         help="Chemin vers tasks/main.yml du role platform_bootstrap")
    args = parser.parse_args()

    steps = read_role_tags(Path(args.tasks_file))
    steps = selected_steps(steps, args.start_at, args.stop_after)
    print(",".join(steps))


if __name__ == "__main__":
    main()
