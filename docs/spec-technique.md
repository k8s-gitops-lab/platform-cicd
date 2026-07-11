# Spec technique — platform-bootstrap

## Structure du dépôt

```
argocd/
  root-app.yaml              Application racine ArgoCD (template Jinja2, rendue puis appliquée une fois à la main)
  repo-server-ca-patch.yaml  Patch strategic merge pour le CA corporate
scripts/
  platform_inventory.py      Modèle historique d'inventaire apps
  render-argocd-apps.py      Génère les manifests ArgoCD depuis argocd/apps/<app>.yaml
  bootstrap-tags.py          Calcule le sous-ensemble d'étapes (--tags) a passer a ansible-playbook selon START_AT/STOP_AFTER
  filter-argocd-install.py   Filtre le manifest ArgoCD (retire notifications)
  gitlab-runner-token-com.py Crée le token runner gitlab.com (group_type, via le PAT) et le Secret K8s
ansible/
  playbook-platform.yml      Étapes ArgoCD/Flux/GitLab du bootstrap, sélectionnées via --tags
  ansible.cfg, inventory.ini Config minimale (hosts: local)
  roles/
    platform_bootstrap/      Séquence de bootstrap (une tâche/tag par étape)
    argocd_trust_ca/         Rôle paramétré, utilisé par argocd-trust-corporate-ca
Makefile
requirements.txt             pyyaml
```

## Ressources applicatives

Les ressources propres aux applications sont décrites sous
`platform-gitops/argocd/apps/<app>.yaml`. `render-argocd-apps.py` lit ces
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

## Séquence de bootstrap (Ansible, dans `ansible/`)

Toute la séquence de bootstrap (ArgoCD, Flux, runner gitlab.com) est portée par un seul
playbook `ansible/playbook-platform.yml` de ce dépôt, dans l'ordre déclaré
par `BOOTSTRAP_STEPS` du Makefile — cf. la règle d'ordre de préférence dans
`AGENTS.md` (TF/K8s déclaratif, puis Ansible pour l'orchestration
multi-étapes, Make en dernier recours comme point d'entrée).
`make bootstrap` ne fait que calculer le sous-ensemble d'étapes à exécuter
puis lance **un seul** `ansible-playbook playbook-platform.yml --tags <étapes>` :

- `scripts/bootstrap-tags.py` calcule la liste `--tags` (comma-séparée) selon
  `START_AT`/`STOP_AFTER`, sans exécuter quoi que ce soit lui-même — c'est
  `ansible-playbook` qui séquence réellement les tâches, dans l'ordre où
  elles apparaissent dans `playbook-platform.yml` (indépendant de l'ordre des
  tags passés en `--tags`).
- `make bootstrap-from-<étape>` reste le raccourci `START_AT=<étape>`.

Chaque cible Makefile individuelle (`argocd-install`, `argocd-bootstrap`,
`argocd-trust-corporate-ca`, `flux-sops-age`,
`argocd-ingress`, `gitlab-runner-token-com`) reste utilisable seule et
n'est qu'un appel à `ansible-playbook playbook-platform.yml --tags <étape>` :

- `argocd-install` : namespace ArgoCD + manifest filtré (`server-side apply`).
- `argocd-trust-corporate-ca` : instance du rôle `argocd_trust_ca`, paramétrée
  pour `argocd-repo-server`, le fichier de patch et la commande shell qui
  produit le certificat additionnel (trousseau macOS pour le CA corporate).
  Le rôle attend le rollout, extrait le bundle CA du pod, fusionne avec le
  certificat additionnel, recrée le ConfigMap, patche le déploiement puis
  attend de nouveau le rollout.
- `argocd-bootstrap` : attente du CRD `Application`, rendu de
  `argocd/root-app.yaml` (`ansible.builtin.template`, `repoURL` paramétré par
  `gitops_repo_url`) puis application.
- `flux-sops-age` : vérifie la clé age locale, crée le namespace `flux-system`
  et le Secret `sops-age`.
- `argocd-ingress` : bascule `server.insecure=true` et redémarrage conditionnel.
- `gitlab-runner-token-com` : invoque le script Python correspondant (variables
  d'env via `environment:` sur la tâche) — le script gère déjà son propre
  idempotence contre l'API gitlab.com, seule son invocation est dans le
  playbook.

## `gitlab-runner-token-com.py` — token runner gitlab.com

1. Vérifie l'idempotence : le Secret `gitlab-runner/gitlabcom-gitlab-runner-secret`
   existe-t-il avec un token ?
2. Lit le PAT depuis le Secret K8s `flux-system/gitlabcom-credentials`
   (`gitlab_token`).
3. Résout l'id du groupe `k8s-gitops-lab` par chemin (`GET /api/v4/groups/
   <path>`) — l'id numérique n'est pas stable : ce groupe top-level ne peut
   pas être recréé via l'API (403 anti-abus), donc après un rebuild complet
   du cluster il est recréé manuellement via l'UI et change d'id à chaque
   fois (cf. `cockpit/scripts/gitlab-tf-state-seed.py`, même approche). Crée
   ensuite un runner `group_type` scopé à cet id via
   `POST /api/v4/user/runners` — `instance_type` échoue sur gitlab.com (pas
   admin d'instance SaaS).
4. Applique le Secret K8s `gitlabcom-gitlab-runner-secret` dans le namespace
   `gitlab-runner` via `kubectl apply` (dry-run + pipe).

## Dépendances

- `kubectl` avec kubeconfig valide (cluster-admin pour le bootstrap).
- `python3` avec `pyyaml` (`pip install -r requirements.txt`).
- `ansible-playbook` (collection `ansible.builtin` uniquement, aucune
  collection externe requise).
- `security` (macOS) pour extraire le CA Zscaler du trousseau système, appelé
  depuis le rôle Ansible `argocd_trust_ca`.
- Accès réseau au cluster Kubernetes.
