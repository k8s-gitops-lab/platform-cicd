# Spec fonctionnelle — platform-bootstrap

## Bootstrap de la plateforme

Le bootstrap est **idempotent** et **relançable par étape** : chaque étape
vérifie si l'état cible est déjà atteint avant d'agir. `make bootstrap` exécute
dans l'ordre :

1. **`argocd-install`** — Installe ArgoCD dans le namespace `argocd`. Filtre les
   ressources `notifications` non utilisées.
2. **`argocd-trust-corporate-ca`** — Injecte le certificat CA Zscaler dans
   `argocd-repo-server` pour que les clones HTTPS soient acceptés.
3. **`argocd-bootstrap`** — Rend `argocd/root-app.yaml` (template : `repoURL`
   vient de la variable `gitops_repo_url`) puis l'applique. ArgoCD se
   synchronise ensuite lui-même depuis `platform-gitops`.
4. **`flux-sops-age`** — Injecte la clé privée age nécessaire au déchiffrement
   SOPS par Flux.
5. **`argocd-ingress`** — Configure ArgoCD en mode HTTP (insecure) pour être
   exposé derrière la Gateway Traefik.
6. **`gitlab-runner-token-com`** — Crée un runner `group_type` sur le groupe
   gitlab.com `k8s-gitops-lab` via le PAT (`flux-system/gitlabcom-credentials`)
   et stocke le token dans `gitlabcom-gitlab-runner-secret` du namespace
   `gitlab-runner`, consommé par l'Application `gitlab-runner-com`.
   Idempotent.

En cas d'échec, on ne relance pas forcément tout le bootstrap :
`make bootstrap START_AT=<étape>` reprend à l'étape indiquée et rejoue la suite.
`make bootstrap STOP_AFTER=<étape>` permet de s'arrêter volontairement après une
étape. Le raccourci `make bootstrap-from-<étape>` est équivalent à
`START_AT=<étape>`.

## Ressources applicatives

Les Applications, ApplicationSets, AppProjects, namespaces et credentials propres
aux applications ne sont plus écrits à la main. Ils sont générés par application
sous `platform-gitops/argocd/generated/apps/<app>/` à partir de
`platform-gitops/argocd/apps/<app>.yaml`.

`make argocd-apps-render` régénère ces manifests et l'ApplicationSet générique
`platform-gitops/argocd/managed/apps-appset.yaml`, qui pointe vers
`argocd/generated/apps/*`. `make check-generated` vérifie que les fichiers
committés sont à jour.

## Authentification ArgoCD

Pas de SSO : login local `admin` uniquement (mot de passe initial via
`make argocd-password`). Le connecteur Dex↔GitLab a été décommissionné le
2026-07-10 (cf. `cockpit/docs/backlog.md`, migration GitLab → gitlab.com) —
pas de besoin avéré pour ce lab mono-opérateur.

## Registre d'images (GHCR)

Il n'y a pas de registry Docker interne au cluster. Les images buildées par
Kaniko sont poussées vers GHCR (`ghcr.io/k8s-gitops-lab/<app>`, voir
`cockpit/platform.yml`). Les Deployments applicatifs tirent l'image
directement depuis GHCR ; le secret de pull source (`ghcr-pull-secret`,
chiffré SOPS dans `platform-gitops/flux-secrets/` et déposé par Flux) est
distribué sous le nom `ghcr-pull` par External Secrets Operator dans chaque
namespace applicatif labellisé (`render-argocd-apps.py` pose le label), où il
est consommé par les `Deployment` générés.
