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
make argocd-install         # Installer ArgoCD seul
make argocd-password        # Afficher le mot de passe admin initial
make gitlab-password        # Afficher le mot de passe root initial
make gitlab-dex-oauth-app   # Créer l'app OAuth GitLab pour Dex (SSO ArgoCD)
make gitlab-runner-token    # Créer le token runner GitLab
make check-generated        # Vérifier que l'ApplicationSet générique apps existe
make status                 # État des Applications ArgoCD
```

## Fichiers importants

| Fichier | Rôle |
|---------|------|
| `argocd/root-app.yaml` | Application racine ArgoCD (appliquée une seule fois à la main) |
| `argocd/repo-server-ca-patch.yaml` | Patch CA corporate pour argocd-repo-server |
| `argocd/dex-ca-patch.yaml` | Patch CA pour argocd-dex-server |
| `scripts/platform_inventory.py` | Modèle de données historique partagé avec `toolbox` |
| `scripts/render-argocd-apps.py` | Déprécié : les apps sont maintenues sous `platform-gitops/argocd/apps/<app>/` |
| `scripts/filter-argocd-install.py` | Filtre le manifest ArgoCD (retire les notifications) |
| `scripts/gitlab-dex-oauth-app.py` | Configure SSO GitLab → Dex → ArgoCD |
| `scripts/gitlab-runner-token.py` | Crée le Secret K8s du token runner |

## Règles critiques

- **`argocd/root-app.yaml` est appliqué une seule fois** via `make argocd-bootstrap`.
  ArgoCD se synchronise ensuite en continu depuis `platform-gitops/argocd/managed/`.
- **Les ressources applicatives sont regroupées par dossier** sous
  `platform-gitops/argocd/apps/<app>/`. Ne pas les mélanger à la plateforme.
- **`argocd/managed/` dans `platform-gitops` est réservé aux points d'entrée
  ArgoCD génériques**.
- **TLS auto-signé** : les scripts Python utilisent `GITLAB_INSECURE_TLS=true`
  par défaut. En production réelle, fournir les CA via `GITLAB_TLS_VERIFY=true`.
- Les scripts nécessitent un contexte kubectl actif avec droits suffisants
  (`cluster-admin` pour le bootstrap).

## Ce qu'il ne faut pas faire

- Ne pas ajouter de ressources applicatives dans `argocd/platform/` ni de détail
  applicatif directement dans `argocd/managed/`.
- Ne pas exécuter `make bootstrap` sur un cluster déjà bootstrappé sans
  vérifier l'idempotence de chaque étape.
- Ne pas committer de tokens ou mots de passe dans ce dépôt.
