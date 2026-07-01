# Spec technique — platform-cicd

## Structure du dépôt

```
argocd/
  root-app.yaml              Application racine ArgoCD (appliquée une fois à la main)
  repo-server-ca-patch.yaml  Patch strategic merge pour le CA corporate
  dex-ca-patch.yaml          Patch strategic merge pour le CA Gateway
scripts/
  platform_inventory.py      Modèle historique d'inventaire apps
  render-argocd-apps.py      Génère les manifests ArgoCD depuis argocd/apps/<app>/app.yaml
  filter-argocd-install.py   Filtre le manifest ArgoCD (retire notifications)
  gitlab-dex-oauth-app.py    Crée l'app OAuth GitLab pour Dex
  gitlab-runner-token.py     Crée le token runner et le Secret K8s
  init-project.py            Déprécié : onboarding app manuel sous argocd/apps/<app>/
Makefile
requirements.txt             pyyaml
```

## Ressources applicatives

Les ressources propres aux applications sont décrites sous
`platform-gitops/argocd/apps/<app>/app.yaml`. `render-argocd-apps.py` lit ces
descriptions, normalise les conventions via `platform_inventory.py`, puis écrit :

- `platform-gitops/argocd/generated/apps/<app>/app-project.yaml` ;
- `platform-gitops/argocd/generated/apps/<app>/applicationset.yaml` ;
- `platform-gitops/argocd/generated/apps/<app>/repo-creds.yaml` ;
- `platform-gitops/argocd/generated/apps/<app>/kustomization.yaml` ;
- `platform-gitops/argocd/managed/apps-appset.yaml`.

`make check-generated` exécute le générateur en mode comparaison et échoue si
les fichiers committés ne correspondent plus aux descriptions `app.yaml`.

## `filter-argocd-install.py` — filtre ArgoCD

Télécharge ou lit le manifest d'installation ArgoCD et filtre les ressources
`argocd-notifications-*` non utilisées dans ce POC. Accepte une URL ou un
chemin local.

## `gitlab-dex-oauth-app.py` — OAuth GitLab → Dex

1. Vérifie l'idempotence : `argocd-secret` contient-il déjà `dex.gitlab.clientID` ?
2. Récupère le mot de passe root GitLab depuis le Secret K8s.
3. S'authentifie via l'API GitLab (password grant OAuth2).
4. Crée l'application OAuth avec `trusted: true` et `confidential: true`.
5. Patch `argocd-secret` avec `dex.gitlab.clientID` et `dex.gitlab.clientSecret`.

## `gitlab-runner-token.py` — token runner

1. Vérifie l'idempotence : le Secret `gitlab-gitlab-runner-secret` existe-t-il avec un token ?
2. S'authentifie via l'API GitLab.
3. Crée un runner d'instance via `/api/v4/user/runners`.
4. Applique un Secret K8s via `kubectl apply` (dry-run + pipe).

## Dépendances

- `kubectl` avec kubeconfig valide (cluster-admin pour le bootstrap).
- `python3` avec `pyyaml` (`pip install -r requirements.txt`).
- `security` (macOS) pour extraire le CA Zscaler du trousseau système.
- Accès réseau au cluster Kubernetes.
