# AGENTS.md — platform-bootstrap

## Rôle du dépôt

`platform-bootstrap` installe ArgoCD sur le cluster Kubernetes, puis applique le
root Application "app of apps" qui délègue à ArgoCD le déploiement
déclaratif de GitLab et des autres add-ons depuis `platform-gitops`. Ce
dépôt attend ensuite que GitLab soit prêt pour configurer ses credentials
(PAT Terraform, token runner) — il ne déploie pas GitLab lui-même. Pas de
SSO : ArgoCD s'utilise en login local `admin` (décommissionné le
2026-07-10, cf. `cockpit/docs/backlog.md`).
Une fois le bootstrap effectué, ArgoCD gère la plateforme en continu depuis
`platform-gitops`.

## Prérequis

- `kubectl` dans le PATH avec un kubeconfig valide pointant sur le cluster cible.
- `ansible-playbook` dans le PATH (collection `ansible.builtin` uniquement,
  aucune collection externe requise). Les étapes ArgoCD/Flux/GitLab du
  bootstrap vivent dans le rôle `platform_bootstrap` de `ansible/roles/` de
  ce dépôt.
- Le cluster doit avoir été provisionné par `infra-iac` (Traefik,
  Gateway API, MetalLB actifs).

## Commandes principales

```bash
make bootstrap              # Bootstrap complet (ArgoCD, puis attente GitLab + credentials)
make bootstrap START_AT=gitlab-tf-credentials # Reprendre le bootstrap à une étape
make argocd-install         # Installer ArgoCD seul
make argocd-password        # Afficher le mot de passe admin initial
make gitlab-password        # Afficher le mot de passe root initial
make gitlab-tf-credentials  # Créer le PAT/Secret GitLab consommé par Terraform
make gitlab-runner-token    # Créer le token runner GitLab
make argocd-apps-render     # Générer argocd/generated/apps/* depuis app.yaml
make check-generated        # Vérifier que les manifests apps générés sont à jour
make status                 # État des Applications ArgoCD
```

## Fichiers importants

| Fichier | Rôle |
|---------|------|
| `argocd/root-app.yaml` | Application racine ArgoCD (template : `repoURL` rendu depuis `gitops_repo_url` ; appliquée une seule fois à la main) |
| `argocd/repo-server-ca-patch.yaml` | Patch CA corporate pour argocd-repo-server |
| `scripts/platform_inventory.py` | Modèle de données historique partagé avec `toolbox` |
| `scripts/render-argocd-apps.py` | Génère `platform-gitops/argocd/generated/apps/*` depuis `argocd/apps/<app>.yaml` (propage aussi `description` dans `AppProject.spec.description`). Rejoué automatiquement par le pipeline `.gitlab-ci.yml` du projet GitLab `platform-gitops` — `make argocd-apps-render` reste utile en local |
| `scripts/filter-argocd-install.py` | Filtre le manifest ArgoCD (retire les notifications) |
| `scripts/gitlab-tf-credentials.py` | Crée le PAT GitLab et le Secret K8s consommés par Terraform |
| `scripts/gitlab-runner-token.py` | Crée le Secret K8s du token runner |
| `scripts/bootstrap-tags.py` | Calcule le sous-ensemble d'étapes (`--tags`) à passer à `ansible-playbook` selon `START_AT`/`STOP_AFTER` — ne séquence rien lui-même |

Le code Ansible (playbook `ansible/playbook-platform.yml`, rôles
`platform_bootstrap` et `argocd_trust_ca` sous `ansible/roles/`) vit dans ce
dépôt, au même titre que les scripts et manifests qu'il invoque
(`scripts/*.py`, `argocd/*.yaml`), référencés via la variable
`platform_cicd_root` (par défaut la racine de ce dépôt ; le `Makefile` la
fixe explicitement à `$(CURDIR)`).

## Ordre de préférence pour le déploiement

Cf. la règle générale dans `cockpit/AGENTS.md` : ressource TF/Kubernetes
déclarative d'abord, sinon Ansible, et Make seulement en dernier recours comme
point d'entrée/enchaînement — y compris pour l'orchestration de plusieurs
étapes (séquence, reprise après échec), qui doit rester dans Ansible plutôt
que dans un enchaînement de cibles Make. C'est pourquoi les étapes de
bootstrap ArgoCD/Flux/GitLab (autrefois du shell brut dans le Makefile, puis
séquencées par `scripts/run-bootstrap.py` en appelant `make <étape>` en
boucle) vivent dans le rôle `platform_bootstrap` de `ansible/roles/` : `make
bootstrap` ne calcule plus qu'un `--tags` et délègue tout le séquencement à
un seul `ansible-playbook`.

## Règles critiques

- **`argocd/root-app.yaml` est appliqué une seule fois** via `make argocd-bootstrap`.
  ArgoCD se synchronise ensuite en continu depuis `platform-gitops/argocd/managed/`.
- **Les applications sont décrites par `argocd/apps/<app>.yaml`**. Les
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

## Gouvernance du développement

Ce repo fait partie de la plateforme poc-devops : toute contribution suit
les trois axes de maîtrise (produit, code, architecture) définis dans
`cockpit/AGENTS.md`, section « Gouvernance du développement » — PRD et
backlog dans `cockpit/docs/`.
