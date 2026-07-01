from __future__ import annotations

import base64
import ssl
import subprocess
import time
import urllib.error
import urllib.request


def ssl_context(insecure_tls: bool):
    if insecure_tls:
        return ssl._create_unverified_context()
    return None


def wait_for_secret_field(
    namespace: str,
    name: str,
    jsonpath: str,
    timeout_seconds: int = 600,
    interval_seconds: int = 5,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = subprocess.run(
            ["kubectl", "-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}"],
            capture_output=True,
            text=True,
        )
        raw = result.stdout.strip()
        if result.returncode == 0 and raw:
            return base64.b64decode(raw).decode()
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Secret '{name}' indisponible dans '{namespace}' apres {timeout_seconds}s")
        time.sleep(interval_seconds)


def wait_for_gitlab_ready(
    gitlab_url: str,
    context,
    timeout_seconds: int = 600,
    interval_seconds: int = 5,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "GitLab n'a pas encore repondu."
    readiness_url = f"{gitlab_url.rstrip('/')}/-/readiness"

    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(readiness_url, method="GET")
            with urllib.request.urlopen(request, context=context, timeout=10) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(interval_seconds)

    raise TimeoutError(f"GitLab n'est pas pret apres {timeout_seconds}s: {last_error}")
