#!/usr/bin/env python3
"""Initialise/update an app inventory file from local code and IaC Git repos.

Usage:
  scripts/init-project.py ../my-app ../my-app-iac

The script updates argocd/apps/<app>.yaml only. It intentionally does not render
or modify argocd/managed/apps-appset.yaml.
"""

from init_projects.cli import main


if __name__ == "__main__":
    main()
