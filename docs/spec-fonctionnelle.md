# Spec fonctionnelle — platform-cicd

## Bootstrap de la plateforme

Le bootstrap est **idempotent** et **relançable par étape** : chaque étape
vérifie si l'état cible est déjà atteint avant d'agir. `make bootstrap` exécute
dans l'ordre :

1. **`argocd-install`** — Installe ArgoCD dans le namespace `argocd`. Filtre les
   ressources `notifications` non utilisées.
2. **`argocd-trust-corporate-ca`** — Injecte le certificat CA Zscaler dans
   `argocd-repo-server` pour que les clones HTTPS soient acceptés.
3. **`argocd-trust-local-gateway-ca`** — Injecte le certificat de la Gateway
   locale dans `argocd-dex-server` pour que le callback OAuth GitLab fonctionne.
4. **`argocd-bootstrap`** — Applique `argocd/root-app.yaml`. ArgoCD se
   synchronise ensuite lui-même depuis `platform-gitops`.
5. **`flux-sops-age`** — Injecte la clé privée age nécessaire au déchiffrement
   SOPS par Flux.
6. **`argocd-ingress`** — Configure ArgoCD en mode HTTP (insecure) pour être
   exposé derrière la Gateway Traefik.
7. **`gitlab-tf-credentials`** — Attend la readiness API GitLab strictement
   nécessaire, crée/rotate le PAT GitLab
   `terraform-controller` et le stocke dans le Secret `gitlab-tf-credentials`
   du namespace `flux-system`, consommé par `Terraform/gitlab-iac`.
8. **`gitlab-dex-oauth-app`** — Crée l'application OAuth GitLab pour Dex et
   renseigne `argocd-secret`. Idempotent : ne refait rien si le secret existe.
9. **`gitlab-runner-token`** — Crée le token runner d'instance et le stocke
   dans `gitlab-gitlab-runner-secret`. Idempotent.

En cas d'échec, on ne relance pas forcément tout le bootstrap :
`make bootstrap START_AT=<étape>` reprend à l'étape indiquée et rejoue la suite.
`make bootstrap STOP_AFTER=<étape>` permet de s'arrêter volontairement après une
étape. Le raccourci `make bootstrap-from-<étape>` est équivalent à
`START_AT=<étape>`.

## Ressources applicatives

Les Applications, ApplicationSets, AppProjects, namespaces et credentials propres
aux applications ne sont plus écrits à la main. Ils sont générés par application
sous `platform-gitops/argocd/generated/apps/<app>/` à partir de
`platform-gitops/argocd/apps/<app>/app.yaml`.

`make argocd-apps-render` régénère ces manifests et l'ApplicationSet générique
`platform-gitops/argocd/managed/apps-appset.yaml`, qui pointe vers
`argocd/generated/apps/*`. `make check-generated` vérifie que les fichiers
committés sont à jour.

## SSO GitLab → ArgoCD (Dex)

L'authentification ArgoCD passe par Dex, qui délègue à GitLab OAuth2 :

1. L'utilisateur clique "Login with GitLab" sur l'UI ArgoCD.
2. Dex redirige vers `https://gitlab.<domaine>/oauth/authorize`.
3. GitLab redirige vers `https://argocd.<domaine>/api/dex/callback`.
4. Dex valide et émet un token ArgoCD.

Les credentials OAuth (client ID / secret) sont stockés dans `argocd-secret`
et renseignés par `gitlab-dex-oauth-app.py`.

## Registry Docker interne

Le registry est déployé par ArgoCD depuis `platform-gitops/argocd/platform/registry/`.
Il est accessible :
- **In-cluster** : `registry.registry.svc.cluster.local:5000` (pas de TLS).
- **Externe** : `http://registry.<domaine>` (via HTTPRoute Traefik).

Les images buildées par Kaniko sont poussées vers l'URL externe, puis tirées
par Kubernetes via l'URL interne ou externe selon la configuration des Deployments.
