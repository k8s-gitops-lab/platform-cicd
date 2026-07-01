# AGENTS.md — platform-cicd

## Rôle du dépôt

`platform-cicd` bootstrappe et maintient la plateforme sur le cluster Kubernetes :
ArgoCD, GitLab (chart Helm), registry Docker interne. Une fois le bootstrap
effectué, ArgoCD gère la plateforme en continu depuis `platform-gitops`.

## Prérequis

- `kubectl` dans le PATH avec un kubeconfig valide pointant sur le cluster cible.
- Le cluster doit avoir été provisionné par `cluster` (Traefik, Gateway API,
  MetalLB actifs).

## Commandes principales

```bash
make bootstrap              # Bootstrap complet (ArgoCD + GitLab + registry)
make bootstrap START_AT=gitlab-tf-credentials # Reprendre le bootstrap à une étape
make argocd-install         # Installer ArgoCD seul
make argocd-password        # Afficher le mot de passe admin initial
make gitlab-password        # Afficher le mot de passe root initial
make gitlab-tf-credentials  # Créer le PAT/Secret GitLab consommé par Terraform
make gitlab-dex-oauth-app   # Créer l'app OAuth GitLab pour Dex (SSO ArgoCD)
make gitlab-runner-token    # Créer le token runner GitLab
make argocd-apps-render     # Générer argocd/generated/apps/* depuis app.yaml
make check-generated        # Vérifier que les manifests apps générés sont à jour
make status                 # État des Applications ArgoCD
```

## Fichiers importants

| Fichier | Rôle |
|---------|------|
| `argocd/root-app.yaml` | Application racine ArgoCD (appliquée une seule fois à la main) |
| `argocd/repo-server-ca-patch.yaml` | Patch CA corporate pour argocd-repo-server |
| `argocd/dex-ca-patch.yaml` | Patch CA pour argocd-dex-server |
| `scripts/platform_inventory.py` | Modèle de données historique partagé avec `toolbox` |
| `scripts/render-argocd-apps.py` | Génère `platform-gitops/argocd/generated/apps/*` depuis `argocd/apps/<app>.yaml` (propage aussi `description` dans `AppProject.spec.description`). Rejoué automatiquement par le pipeline `.gitlab-ci.yml` du projet GitLab `platform-gitops` — `make argocd-apps-render` reste utile en local |
| `scripts/filter-argocd-install.py` | Filtre le manifest ArgoCD (retire les notifications) |
| `scripts/gitlab-tf-credentials.py` | Crée le PAT GitLab et le Secret K8s consommés par Terraform |
| `scripts/gitlab-dex-oauth-app.py` | Configure SSO GitLab → Dex → ArgoCD |
| `scripts/gitlab-runner-token.py` | Crée le Secret K8s du token runner |

## Règles critiques

- **`argocd/root-app.yaml` est appliqué une seule fois** via `make argocd-bootstrap`.
  ArgoCD se synchronise ensuite en continu depuis `platform-gitops/argocd/managed/`.
- **Les applications sont décrites par `argocd/apps/<app>/app.yaml`**. Les
  manifests ArgoCD dédiés sont générés dans `argocd/generated/apps/<app>/`.
- **`argocd/managed/` dans `platform-gitops` est réservé aux points d'entrée
  ArgoCD génériques**.
- **TLS auto-signé** : les scripts Python utilisent `GITLAB_INSECURE_TLS=true`
  par défaut. En production réelle, fournir les CA via `GITLAB_TLS_VERIFY=true`.
- Les scripts nécessitent un contexte kubectl actif avec droits suffisants
  (`cluster-admin` pour le bootstrap).

## Ce qu'il ne faut pas faire

- Ne pas éditer manuellement `argocd/generated/apps/<app>/` : modifier
  `app.yaml`, lancer `make argocd-apps-render`, puis committer.
- Ne pas exécuter `make bootstrap` sur un cluster déjà bootstrappé sans
  vérifier l'idempotence de chaque étape.
- Ne pas committer de tokens ou mots de passe dans ce dépôt.
