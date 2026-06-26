from __future__ import annotations

import sys

from .app_model import build_app
from .config import load_config
from .inventory import write_app_file


def main() -> None:
    config = load_config(sys.argv)
    app = build_app(config)

    action = write_app_file(config.apps_dir, config.app_name, app)
    print(f"Application '{config.app_name}' {action} dans {config.apps_dir / (config.app_name + '.yaml')}")
    print(f"Services: {', '.join(config.services)}")
    print(f"Code:      {config.code_ref}")
    print(f"Manifests: {config.iac_ref}:{config.kustomize_path}")
