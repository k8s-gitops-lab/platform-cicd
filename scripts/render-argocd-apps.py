#!/usr/bin/env python3
"""Generate ArgoCD app resources from argocd/apps/<app>.yaml."""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

from platform_inventory import default_apps_file, load_inventory, platform_constants

# Distribution des secrets entierement declarative (External Secrets Operator,
# installe par platform-gitops argocd/managed/external-secrets.yaml) :
# - le secret source GHCR (argocd/ghcr-pull-secret) est depose par Flux depuis
#   platform-gitops/flux-secrets/ (dechiffrement SOPS) ;
# - la ClusterExternalSecret ghcr-pull (argocd/platform/secrets-distribution)
#   le recopie sous le nom ghcr-pull dans tout namespace portant le label
#   ci-dessous, pose ici sur les namespaces d'environnement ;
# - un ExternalSecret par app (genere ci-dessous) fabrique le secret
#   repository ArgoCD a partir du mot de passe root GitLab.
_GHCR_PULL_LABEL = "k8s-gitops-lab.io/ghcr-pull"
_GITLAB_SECRET_STORE = "gitlab-secrets"
_GITLAB_ROOT_PASSWORD_SECRET = "gitlab-gitlab-initial-root-password"

# Les CR ExternalSecret dependent des CRD posees par l'Application
# external-secrets : les Applications reessaient jusqu'a convergence.
_SYNC_RETRY = {
    "limit": 10,
    "backoff": {"duration": "30s", "factor": 2, "maxDuration": "5m"},
}


def app_project(app: dict) -> dict:
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AppProject",
        "metadata": {"name": app["argocd"]["project"], "namespace": "argocd"},
        "spec": {
            "description": app.get("description", ""),
            "sourceRepos": app["argocd"]["sourceRepos"],
            "destinations": app["argocd"]["destinations"],
            "clusterResourceWhitelist": [{"group": "", "kind": "Namespace"}],
        },
    }


def app_data(app: dict) -> dict:
    """Donnees lues directement par app-envs-appset.yaml (git files generator) :
    pas un manifest k8s, jamais liste dans kustomization.yaml.

    Le champ est nomme manifestsPath (et non path) car le git files
    generator d'ArgoCD reserve deja la cle "path" (objet path/basename/
    filename/... decrivant l'emplacement du fichier matche) : en
    goTemplate, ".path" s'y resout donc a la place de la valeur ici
    fournie, cassant le rendu du champ source.path de l'Application."""
    return {
        "app": app["name"],
        "project": app["argocd"]["project"],
        "repoURL": app["manifests"]["argocdRepoURL"],
        "manifestsPath": app["manifests"]["path"],
        "environments": [
            {"name": env["name"], "branch": env["branch"], "namespace": env["namespace"]}
            for env in app["environments"]
        ],
    }


def is_local_gitlab_repo(app: dict, gitlab_host: str) -> bool:
    """Le repo-creds genere ci-dessous suppose le compte root du GitLab local
    (ClusterSecretStore gitlab-secrets) : ne s'applique qu'aux apps dont
    argocdRepoURL pointe encore vers l'instance in-cluster. Un app migre
    vers gitlab.com (argocdRepoURL surcharge, cf. platform_inventory.py) gère
    son credential ArgoCD manuellement via platform-gitops/flux-secrets/
    (PAT chiffre SOPS, cf. cockpit/docs/backlog.md)."""
    return app["manifests"]["argocdRepoURL"].startswith(f"http://{gitlab_host}/")


def repo_creds(app: dict) -> dict:
    secret_name = app["manifests"]["argocdSecretName"]
    repo_url = app["manifests"]["argocdRepoURL"]
    return {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {
            "name": secret_name,
            "namespace": "argocd",
            "annotations": {"argocd.argoproj.io/sync-wave": "2"},
        },
        "spec": {
            "refreshInterval": "1h",
            "secretStoreRef": {"kind": "ClusterSecretStore", "name": _GITLAB_SECRET_STORE},
            "target": {
                "name": secret_name,
                "creationPolicy": "Owner",
                "template": {
                    "metadata": {"labels": {"argocd.argoproj.io/secret-type": "repository"}},
                    "data": {
                        "type": "git",
                        "url": repo_url,
                        "username": "root",
                        "password": "{{ .password }}",
                    },
                },
            },
            "data": [
                {
                    "secretKey": "password",
                    "remoteRef": {"key": _GITLAB_ROOT_PASSWORD_SECRET, "property": "password"},
                }
            ],
        },
    }


def app_namespaces(app: dict) -> list[dict]:
    return [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": env["namespace"],
                "labels": {_GHCR_PULL_LABEL: "enabled"},
                "annotations": {"argocd.argoproj.io/sync-wave": "0"},
            },
        }
        for env in app["environments"]
    ]


def root_appset(pconst: dict) -> dict:
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {
            "name": "apps",
            "namespace": "argocd",
            # Wave apres terraform-gitlab (wave 2, cf. terraform-gitlab.yaml) :
            # les AppProject par app sont un souci applicatif, pas un
            # prerequis du bootstrap plateforme (tf-controller/flux-secrets)
            # qui doit rester syncable meme si l'onboarding d'une app echoue.
            # app-envs-appset (wave 4) depend de cette ApplicationSet pour
            # que l'AppProject de chaque app existe avant de creer ses
            # Applications par environnement.
            "annotations": {"argocd.argoproj.io/sync-wave": "3"},
        },
        "spec": {
            "goTemplate": True,
            "goTemplateOptions": ["missingkey=error"],
            "generators": [
                {
                    "git": {
                        "repoURL": pconst["repoURL"],
                        "revision": pconst["targetRevision"],
                        "directories": [{"path": "argocd/generated/apps/*"}],
                    }
                }
            ],
            "template": {
                "metadata": {
                    "name": "app-config-{{ .path.basename }}",
                    "namespace": "argocd",
                    "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                },
                "spec": {
                    "project": "default",
                    "source": {
                        "repoURL": pconst["repoURL"],
                        "targetRevision": pconst["targetRevision"],
                        "path": "{{ .path.path }}",
                    },
                    "destination": {
                        "server": "https://kubernetes.default.svc",
                        "namespace": "argocd",
                    },
                    "syncPolicy": {
                        "automated": {"prune": True, "selfHeal": True},
                        "syncOptions": ["CreateNamespace=true"],
                        "retry": _SYNC_RETRY,
                    },
                },
            },
        },
    }


def app_envs_appset(pconst: dict) -> dict:
    """Un seul ApplicationSet pour tous les environnements de toutes les apps :
    Matrix(git files sur app-data.yaml de chaque app x list derive de son champ
    environments) remplace l'ApplicationSet par app genere precedemment."""
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {
            "name": "app-envs",
            "namespace": "argocd",
            # Wave apres apps-appset (wave 3) : garantit que l'AppProject de
            # chaque app existe deja quand cette ApplicationSet cree les
            # Applications par environnement qui la referencent (sinon
            # "application references project X which does not exist" au
            # premier bootstrap, cf. cockpit/docs/backlog.md).
            "annotations": {"argocd.argoproj.io/sync-wave": "4"},
        },
        "spec": {
            "goTemplate": True,
            "goTemplateOptions": ["missingkey=error"],
            "generators": [
                {
                    "matrix": {
                        "generators": [
                            {
                                "git": {
                                    "repoURL": pconst["repoURL"],
                                    "revision": pconst["targetRevision"],
                                    "files": [{"path": "argocd/generated/apps/*/app-data.yaml"}],
                                }
                            },
                            {"list": {"elementsYaml": "{{ .environments | toJson }}"}},
                        ]
                    }
                }
            ],
            "template": {
                "metadata": {
                    "name": "{{ .app }}-{{ .name }}",
                    "namespace": "argocd",
                    "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                },
                "spec": {
                    "project": "{{ .project }}",
                    "source": {
                        "repoURL": "{{ .repoURL }}",
                        "targetRevision": "{{ .branch }}",
                        "path": "{{ .manifestsPath }}",
                    },
                    "destination": {
                        "server": "https://kubernetes.default.svc",
                        "namespace": "{{ .namespace }}",
                    },
                    "syncPolicy": {
                        "automated": {"prune": True, "selfHeal": True},
                        "syncOptions": ["CreateNamespace=true"],
                        "retry": _SYNC_RETRY,
                    },
                },
            },
        },
    }


def write_yaml(path: Path, docs: dict | list[dict]) -> None:
    documents = docs if isinstance(docs, list) else [docs]
    path.write_text(
        "\n---\n".join(
            yaml.dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
            for doc in documents
        )
        + "\n"
    )


def render(apps_file: Path, output_dir: Path, apps_appset_file: Path, app_envs_appset_file: Path) -> None:
    inventory = load_inventory(apps_file)
    pconst = platform_constants(inventory)
    gitlab_host = inventory.get("gitlab", {}).get("internalHost", "")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    (output_dir / ".gitkeep").touch()

    for app in inventory["apps"]:
        app_dir = output_dir / app["name"]
        app_dir.mkdir()
        write_yaml(app_dir / "app-project.yaml", app_project(app))
        write_yaml(app_dir / "namespaces.yaml", app_namespaces(app))
        resources = ["app-project.yaml", "namespaces.yaml"]
        if is_local_gitlab_repo(app, gitlab_host):
            write_yaml(app_dir / "repo-creds.yaml", repo_creds(app))
            resources.append("repo-creds.yaml")
        # app-data.yaml : pas un manifest, lu directement par app-envs-appset.yaml
        # (git files generator) ; volontairement absent de kustomization.yaml.
        write_yaml(app_dir / "app-data.yaml", app_data(app))
        write_yaml(
            app_dir / "kustomization.yaml",
            {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "resources": resources,
            },
        )

    apps_appset_file.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(apps_appset_file, root_appset(pconst))
    app_envs_appset_file.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(app_envs_appset_file, app_envs_appset(pconst))


def same_tree(left: Path, right: Path) -> bool:
    left_files = sorted(p.relative_to(left) for p in left.rglob("*") if p.is_file())
    right_files = sorted(p.relative_to(right) for p in right.rglob("*") if p.is_file())
    return left_files == right_files and all((left / p).read_bytes() == (right / p).read_bytes() for p in left_files)


def check(apps_file: Path, output_dir: Path, apps_appset_file: Path, app_envs_appset_file: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        tmp_output = tmp_root / "generated/apps"
        tmp_apps_appset = tmp_root / "managed/apps-appset.yaml"
        tmp_app_envs_appset = tmp_root / "managed/app-envs-appset.yaml"
        render(apps_file, tmp_output, tmp_apps_appset, tmp_app_envs_appset)
        for managed_file, tmp_managed in (
            (apps_appset_file, tmp_apps_appset),
            (app_envs_appset_file, tmp_app_envs_appset),
        ):
            if not managed_file.exists() or managed_file.read_bytes() != tmp_managed.read_bytes():
                print(f"{managed_file} n'est pas à jour. Lancez: make argocd-apps-render", file=sys.stderr)
                return 1
        if not output_dir.exists() or not same_tree(output_dir, tmp_output):
            print(f"{output_dir} n'est pas à jour. Lancez: make argocd-apps-render", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apps-file", type=Path, default=default_apps_file())
    args = parser.parse_args()

    apps_file = args.apps_file.resolve()
    gitops_root = apps_file.parents[1]
    output_dir = gitops_root / "argocd/generated/apps"
    apps_appset_file = gitops_root / "argocd/managed/apps-appset.yaml"
    app_envs_appset_file = gitops_root / "argocd/managed/app-envs-appset.yaml"

    if args.check:
        return check(apps_file, output_dir, apps_appset_file, app_envs_appset_file)
    render(apps_file, output_dir, apps_appset_file, app_envs_appset_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
