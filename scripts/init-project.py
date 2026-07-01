#!/usr/bin/env python3
"""Deprecated platform-gitops app onboarding entrypoint."""

import sys


sys.exit(
    "Les ressources applicatives doivent etre regroupees sous "
    "platform-gitops/argocd/apps/<app>/."
)
