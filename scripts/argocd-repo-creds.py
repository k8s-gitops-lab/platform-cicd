#!/usr/bin/env python3
# Crée les Secrets K8s de credentials ArgoCD pour les dépôts manifests privés
# déclarés dans argocd/apps.yaml + argocd/apps/*.yaml. Chaque Secret est labellisé
# argocd.argoproj.io/secret-type=repository et donne un accès read_repository.
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from platform_inventory import load_inventory

GITLAB_NAMESPACE = os.environ.get("GITLAB_NAMESPACE", "gitlab")
GITLAB_URL = os.environ.get("GITLAB_URL", "http://gitlab.192.168.33.100.nip.io")
ARGOCD_NAMESPACE = os.environ.get("ARGOCD_NAMESPACE", "argocd")
APPS_FILE = Path(os.environ.get(
    "APPS_FILE",
    Path(__file__).parent.parent / "argocd/apps.yaml",
))


def kube_secret_field(namespace, name, jsonpath):
    raw = subprocess.run(
        ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return base64.b64decode(raw).decode() if raw else ""


def kube_get(namespace, kind, name):
    return subprocess.run(
        ["kubectl", "-n", namespace, "get", kind, name],
        capture_output=True,
    ).returncode == 0


def http(url, method="GET", data=None, token=None):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, {}


root_password = kube_secret_field(
    GITLAB_NAMESPACE, "gitlab-gitlab-initial-root-password", "{.data.password}"
)

_, auth = http(f"{GITLAB_URL}/oauth/token", method="POST", data={
    "grant_type": "password",
    "username": "root",
    "password": root_password,
})
bearer_token = auth.get("access_token", "")
if not bearer_token or bearer_token == "null":
    print("Échec d'authentification à l'API GitLab", file=sys.stderr)
    sys.exit(1)

_, user = http(f"{GITLAB_URL}/api/v4/user", token=bearer_token)
root_user_id = user["id"]

today = date.today()
try:
    expires_at = today.replace(year=today.year + 1).strftime("%Y-%m-%d")
except ValueError:
    expires_at = today.replace(year=today.year + 1, day=28).strftime("%Y-%m-%d")

inventory = load_inventory(APPS_FILE)

for app in inventory["apps"]:
    manifests = app["manifests"]
    app_name = app["name"]
    secret_name = manifests["argocdSecretName"]
    repo_url = manifests["repoURL"]

    if kube_get(ARGOCD_NAMESPACE, "secret", secret_name):
        print(f"Secret '{secret_name}' déjà présent dans '{ARGOCD_NAMESPACE}', rien à faire.")
        continue

    _, token_data = http(
        f"{GITLAB_URL}/api/v4/users/{root_user_id}/personal_access_tokens",
        method="POST",
        token=bearer_token,
        data={
            "name": f"argocd-{app_name}-manifests",
            "scopes[]": "read_repository",
            "expires_at": expires_at,
        },
    )
    argocd_token = token_data.get("token", "")
    if not argocd_token or argocd_token == "null":
        print(f"Échec de création du token de lecture ArgoCD pour '{app_name}'", file=sys.stderr)
        sys.exit(1)

    subprocess.run([
        "kubectl", "-n", ARGOCD_NAMESPACE, "create", "secret", "generic", secret_name,
        "--from-literal=type=git",
        f"--from-literal=url={repo_url}",
        "--from-literal=username=root",
        f"--from-literal=password={argocd_token}",
    ], check=True)
    subprocess.run([
        "kubectl", "-n", ARGOCD_NAMESPACE, "label", "secret", secret_name,
        "argocd.argoproj.io/secret-type=repository",
    ], check=True)
    print(f"Secret '{secret_name}' créé pour '{repo_url}'.")
