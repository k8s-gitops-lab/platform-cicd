# Spec fonctionnelle — platform-cicd

## Bootstrap de la plateforme

Le bootstrap est **idempotent** : chaque étape vérifie si l'état cible est déjà
atteint avant d'agir. `make bootstrap` exécute dans l'ordre :

1. **`argocd-install`** — Installe ArgoCD dans le namespace `argocd`. Filtre les
   ressources `notifications` non utilisées.
2. **`argocd-wait`** — Attend que tous les déploiements ArgoCD soient `Available`.
3. **`argocd-trust-corporate-ca`** — Injecte le certificat CA Zscaler dans
   `argocd-repo-server` pour que les clones HTTPS soient acceptés.
4. **`argocd-trust-local-gateway-ca`** — Injecte le certificat de la Gateway
   locale dans `argocd-dex-server` pour que le callback OAuth GitLab fonctionne.
5. **`argocd-bootstrap`** — Applique `argocd/root-app.yaml`. ArgoCD se
   synchronise ensuite lui-même depuis `platform-gitops`.
6. **`argocd-ingress`** — Configure ArgoCD en mode HTTP (insecure) pour être
   exposé derrière la Gateway Traefik.
7. **`gitlab-wait`** — Attend que tous les pods GitLab soient `Ready`.
8. **`gitlab-dex-oauth-app`** — Crée l'application OAuth GitLab pour Dex et
   renseigne `argocd-secret`. Idempotent : ne refait rien si le secret existe.
9. **`gitlab-runner-token`** — Crée le token runner d'instance et le stocke
   dans `gitlab-gitlab-runner-secret`. Idempotent.
10. **`registry-wait`** — Attend que le déploiement `registry` soit `Available`.

## Ressources applicatives

Les Applications, ApplicationSets, AppProjects, namespaces et credentials propres
aux applications ne sont plus générés dans `argocd/managed/`. Ils sont regroupés
par application sous `platform-gitops/argocd/apps/<app>/`.

`make check-generated` vérifie que l'ApplicationSet générique
`platform-gitops/argocd/managed/apps-appset.yaml` existe pour pointer vers
`argocd/apps/*`. Les cibles historiques `argocd-apps-render` et `init-project`
échouent explicitement pour éviter de recréer l'ancien inventaire plat.

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
