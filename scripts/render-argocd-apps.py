#!/usr/bin/env python3
# Génère les AppProject et l'ApplicationSet ArgoCD depuis l'inventaire
# argocd/apps.yaml + argocd/apps/*.yaml. La sortie est committée dans argocd/managed/apps-appset.yaml
# (`make argocd-apps-render`) -- ArgoCD la synchronise en continu depuis Git via
# le root Application (argocd/root-app.yaml), elle n'est plus appliquée à la main.
import os
import yaml
from pathlib import Path

from platform_inventory import default_apps_file, load_inventory, platform_constants

inventory_path = os.environ.get("APPS_FILE") or os.environ.get("ARGOCD_APPS_FILE") or str(default_apps_file())

inventory = load_inventory(Path(inventory_path))
apps = inventory["apps"]
pconst = platform_constants(inventory)

projects = [
    {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AppProject",
        "metadata": {"name": app["argocd"]["project"], "namespace": "argocd"},
        "spec": {
            "sourceRepos": app["argocd"]["sourceRepos"],
            "destinations": app["argocd"]["destinations"],
            # Sans whitelist explicite, un AppProject bloque toute ressource cluster-scope,
            # y compris le Namespace que `syncOptions: [CreateNamespace=true]` doit créer.
            "clusterResourceWhitelist": [{"group": "", "kind": "Namespace"}],
        },
    }
    for app in apps
]

elements = [
    {
        "app": app["name"],
        "project": app["argocd"]["project"],
        "env": env["name"],
        "branch": env["branch"],
        "namespace": env["namespace"],
        "repoURL": app["manifests"]["argocdRepoURL"],
        "path": app["manifests"]["path"],
    }
    for app in apps
    for env in app["environments"]
]

applicationset = {
    "apiVersion": "argoproj.io/v1alpha1",
    "kind": "ApplicationSet",
    "metadata": {"name": "apps", "namespace": "argocd"},
    "spec": {
        "goTemplate": True,
        "goTemplateOptions": ["missingkey=error"],
        "generators": [{"list": {"elements": elements}}],
        "template": {
            "metadata": {
                "name": "{{ .app }}-{{ .env }}",
                "namespace": "argocd",
                "finalizers": ["resources-finalizer.argocd.argoproj.io"],
            },
            "spec": {
                "project": "{{ .project }}",
                "source": {
                    "repoURL": "{{ .repoURL }}",
                    "targetRevision": "{{ .branch }}",
                    "path": "{{ .path }}",
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": "{{ .namespace }}",
                },
                "syncPolicy": {
                    "automated": {"prune": True, "selfHeal": True},
                    "syncOptions": ["CreateNamespace=true"],
                },
            },
        },
    },
}

print("# Généré par scripts/render-argocd-apps.py depuis argocd/apps.yaml + argocd/apps/*.yaml -- ne pas éditer à la main.")
for i, doc in enumerate(projects + [applicationset]):
    if i > 0:
        print("---")
    output = yaml.dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(output.lstrip("---\n").lstrip(), end="")
