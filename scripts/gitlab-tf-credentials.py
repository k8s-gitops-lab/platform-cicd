#!/usr/bin/env python3
"""Create the GitLab PAT secret consumed by tofu-controller."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from gitlab_bootstrap import ssl_context, wait_for_gitlab_ready, wait_for_secret_field

GITLAB_NAMESPACE = os.environ.get("GITLAB_NAMESPACE", "gitlab")
FLUX_NAMESPACE = os.environ.get("FLUX_NAMESPACE", "flux-system")
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.192.168.33.100.nip.io").rstrip("/")
GITLAB_INSECURE_TLS = os.environ.get("GITLAB_INSECURE_TLS", "true").lower() not in ("0", "false", "no")
GITLAB_READY_TIMEOUT = int(os.environ.get("GITLAB_READY_TIMEOUT", "600"))
SECRET_NAME = os.environ.get("SECRET_NAME", "gitlab-tf-credentials")
PAT_NAME = os.environ.get("PAT_NAME", "terraform-controller")
PAT_SCOPES = ["api", "read_repository", "write_repository"]


def kube_secret_field(namespace: str, name: str, jsonpath: str) -> str:
    raw = subprocess.run(
        ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return base64.b64decode(raw).decode() if raw else ""


def secret_exists(namespace: str, name: str) -> bool:
    return subprocess.run(
        ["kubectl", "-n", namespace, "get", "secret", name],
        capture_output=True,
    ).returncode == 0


def http_json(path: str, method: str = "GET", data: dict | None = None, token: str = "", private_token: str = ""):
    headers: dict[str, str] = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if private_token:
        headers["PRIVATE-TOKEN"] = private_token
    if data is not None:
        body = urllib.parse.urlencode(data, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(f"{GITLAB_URL}{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, context=ssl_context(GITLAB_INSECURE_TLS), timeout=30) as response:
        payload = response.read()
        if not payload:
            return None
        return json.loads(payload)


def existing_token_is_valid() -> bool:
    if not secret_exists(FLUX_NAMESPACE, SECRET_NAME):
        return False
    token = kube_secret_field(FLUX_NAMESPACE, SECRET_NAME, "{.data.gitlab_token}")
    if not token:
        return False
    try:
        http_json("/api/v4/user", private_token=token)
        return True
    except urllib.error.HTTPError:
        return False


def root_bearer_token() -> str:
    root_password = wait_for_secret_field(
        GITLAB_NAMESPACE,
        "gitlab-gitlab-initial-root-password",
        "{.data.password}",
        timeout_seconds=GITLAB_READY_TIMEOUT,
    )
    auth = http_json(
        "/oauth/token",
        method="POST",
        data={"grant_type": "password", "username": "root", "password": root_password},
    )
    token = auth.get("access_token", "")
    if not token or token == "null":
        print("Échec d'authentification root GitLab pour créer le PAT Terraform.", file=sys.stderr)
        sys.exit(1)
    return token


def revoke_existing_named_pat(bearer_token: str, user_id: int) -> None:
    try:
        pats = http_json(f"/api/v4/personal_access_tokens?user_id={user_id}&state=active", token=bearer_token)
    except urllib.error.HTTPError:
        return
    for pat in pats if isinstance(pats, list) else []:
        if pat.get("name") == PAT_NAME:
            try:
                http_json(f"/api/v4/personal_access_tokens/{pat['id']}", method="DELETE", token=bearer_token)
            except urllib.error.HTTPError:
                pass


def create_pat(bearer_token: str) -> str:
    user = http_json("/api/v4/user", token=bearer_token)
    user_id = int(user["id"])
    revoke_existing_named_pat(bearer_token, user_id)
    expires_at = (date.today() + timedelta(days=365)).isoformat()
    result = http_json(
        f"/api/v4/users/{user_id}/personal_access_tokens",
        method="POST",
        token=bearer_token,
        data={"name": PAT_NAME, "scopes[]": PAT_SCOPES, "expires_at": expires_at},
    )
    token = result.get("token", "")
    if not token:
        print(f"Échec de création du PAT Terraform GitLab: {result}", file=sys.stderr)
        sys.exit(1)
    return token


def apply_secret(token: str) -> None:
    namespace = subprocess.run(
        ["kubectl", "create", "namespace", FLUX_NAMESPACE, "--dry-run=client", "-o", "yaml"],
        check=True,
        stdout=subprocess.PIPE,
    )
    subprocess.run(["kubectl", "apply", "-f", "-"], input=namespace.stdout, check=True)
    create = subprocess.run(
        [
            "kubectl",
            "-n",
            FLUX_NAMESPACE,
            "create",
            "secret",
            "generic",
            SECRET_NAME,
            f"--from-literal=gitlab_token={token}",
            "--from-literal=username=oauth2",
            f"--from-literal=password={token}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    subprocess.run(["kubectl", "apply", "-f", "-"], input=create.stdout, check=True)


def main() -> None:
    wait_for_gitlab_ready(GITLAB_URL, ssl_context(GITLAB_INSECURE_TLS), GITLAB_READY_TIMEOUT)
    if existing_token_is_valid():
        print(f"Secret '{SECRET_NAME}' déjà présent dans '{FLUX_NAMESPACE}' avec un token GitLab valide.")
        return
    token = create_pat(root_bearer_token())
    apply_secret(token)
    print(f"Secret '{SECRET_NAME}' créé dans '{FLUX_NAMESPACE}' pour Terraform.")


if __name__ == "__main__":
    main()
