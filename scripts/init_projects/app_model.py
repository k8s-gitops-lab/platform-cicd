from __future__ import annotations

from .config import InitProjectConfig


def build_app(config: InitProjectConfig) -> dict:
    return {
        "name": config.app_name,
        "hasPreprod": config.has_preprod,
        "services": config.services,
        "manifests": {
            "path": config.kustomize_path,
        },
    }
