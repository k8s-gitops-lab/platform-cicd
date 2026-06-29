# Spec technique — platform-cicd

## Structure du dépôt

```
argocd/
  root-app.yaml              Application racine ArgoCD (appliquée une fois à la main)
  repo-server-ca-patch.yaml  Patch strategic merge pour le CA corporate
  dex-ca-patch.yaml          Patch strategic merge pour le CA Gateway
scripts/
  platform_inventory.py      Chargement et normalisation de l'inventaire apps
  render-argocd-apps.py      Génère AppProject + ApplicationSet depuis l'inventaire
  filter-argocd-install.py   Filtre le manifest ArgoCD (retire notifications)
  gitlab-dex-oauth-app.py    Crée l'app OAuth GitLab pour Dex
  gitlab-runner-token.py     Crée le token runner et le Secret K8s
  init-project.py            Onboarding d'une app (délègue à init_projects/)
Makefile
requirements.txt             pyyaml
```

## `platform_inventory.py` — modèle de données

Ce module est **partagé** avec `toolbox/scripts/platform_inventory.py`. Les deux
copies doivent rester synchronisées.

`load_inventory(apps_file)` :
1. Charge `argocd/apps.yaml` (métadonnées plateforme + `appsDir`).
2. Si `apps:` est absent, charge chaque `argocd/apps/*.yaml`.
3. Normalise chaque app via `_normalize_app()` : dérive par convention
   `manifests.projectPath`, `manifests.argocdRepoURL`, `manifests.path` (défaut: `k8s`),
   `code.projectPath`, `environments`, `showcaseService`, `argocd`.

## `render-argocd-apps.py` — générateur ApplicationSet

Lit l'inventaire et produit un document YAML multi-documents :
- Un `AppProject` par app (whitelist `Namespace` pour `CreateNamespace=true`).
- Un `ApplicationSet` unique avec un générateur `list` contenant toutes les
  combinaisons `<app>/<env>`.

La sortie est écrite dans `platform-gitops/argocd/managed/apps-appset.yaml` via
une redirection shell (`make argocd-apps-render`).

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
