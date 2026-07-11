#!/usr/bin/env python3
# Cree un token de runner scope au groupe gitlab.com k8s-gitops-lab (via le
# PAT deja stocke dans flux-system/gitlabcom-credentials) et le stocke dans
# le Secret K8s consomme par le chart gitlab-runner-com standalone.
#
# Contrairement a gitlab-runner-token.py (instance locale, runner_type=
# instance_type via le compte root) : sur gitlab.com il n'existe pas de
# runner d'instance accessible a un compte non-admin SaaS -- seul
# runner_type=group_type, scope au groupe dont le PAT est proprietaire,
# fonctionne (verifie le 2026-07-10 par un aller-retour creation/suppression
# manuel via l'API).
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
# Chemin du groupe racine k8s-gitops-lab sur gitlab.com -- l'id numerique
# n'est PAS stable : ce groupe top-level ne peut pas etre recree via l'API
# (403 anti-abus, cf. scripts/gitlab-tf-state-seed.py dans cockpit) et doit
# etre recree manuellement via l'UI apres un rebuild complet du cluster,
# ce qui lui donne un nouvel id a chaque fois. Resolu dynamiquement par
# chemin plutot que fige en dur (meme approche que gitlab-tf-state-seed.py).
GROUP_PATH = os.environ.get("GITLAB_COM_GROUP", "k8s-gitops-lab")
PAT_NAMESPACE = os.environ.get("PAT_NAMESPACE", "flux-system")
PAT_SECRET = os.environ.get("PAT_SECRET", "gitlabcom-credentials")
RUNNER_NAMESPACE = os.environ.get("RUNNER_NAMESPACE", "gitlab-runner")
SECRET_NAME = os.environ.get("SECRET_NAME", "gitlabcom-gitlab-runner-secret")
DESCRIPTION = os.environ.get("RUNNER_DESCRIPTION", "k3d-poc-devops-com")


def kube_secret_field(namespace: str, name: str, jsonpath: str) -> str:
    raw = subprocess.run(
        ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return base64.b64decode(raw).decode() if raw else ""


def secret_exists(namespace: str, name: str) -> bool:
    return subprocess.run(["kubectl", "-n", namespace, "get", "secret", name], capture_output=True).returncode == 0


def gitlab_get(path: str, token: str):
    req = urllib.request.Request(f"{GITLAB_URL}{path}", headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def gitlab_post(path: str, data: dict, token: str):
    req = urllib.request.Request(
        f"{GITLAB_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def kube_apply(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, check=True)
    subprocess.run(["kubectl", "apply", "-f", "-"], input=proc.stdout, check=True)


def main() -> None:
    if secret_exists(RUNNER_NAMESPACE, SECRET_NAME):
        existing_token = kube_secret_field(RUNNER_NAMESPACE, SECRET_NAME, "{.data.runner-token}")
        if existing_token:
            print(f"Secret '{SECRET_NAME}' déjà présent dans '{RUNNER_NAMESPACE}' avec un runner-token, rien à faire.")
            return

    pat = kube_secret_field(PAT_NAMESPACE, PAT_SECRET, "{.data.gitlab_token}")
    if not pat:
        print(f"PAT introuvable dans {PAT_NAMESPACE}/{PAT_SECRET}", file=sys.stderr)
        sys.exit(1)

    try:
        group = gitlab_get(f"/api/v4/groups/{urllib.parse.quote(GROUP_PATH, safe='')}", pat)
    except urllib.error.HTTPError as e:
        print(f"Groupe '{GROUP_PATH}' introuvable sur {GITLAB_URL} ({e.code}): {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    group_id = group["id"]

    runner = gitlab_post("/api/v4/user/runners", {
        "runner_type": "group_type",
        "group_id": group_id,
        "description": DESCRIPTION,
    }, pat)
    runner_token = runner.get("token", "")
    if not runner_token:
        print(f"Échec de création du runner gitlab.com: {runner}", file=sys.stderr)
        sys.exit(1)

    kube_apply(["kubectl", "create", "namespace", RUNNER_NAMESPACE, "--dry-run=client", "-o", "yaml"])
    kube_apply([
        "kubectl", "-n", RUNNER_NAMESPACE, "create", "secret", "generic", SECRET_NAME,
        "--from-literal=runner-registration-token=",
        f"--from-literal=runner-token={runner_token}",
        "--dry-run=client", "-o", "yaml",
    ])
    print(f"Secret '{SECRET_NAME}' créé dans '{RUNNER_NAMESPACE}' avec un nouveau token runner gitlab.com (group {GROUP_PATH}, id {group_id}).")


if __name__ == "__main__":
    main()
