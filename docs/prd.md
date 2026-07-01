# PRD — platform-cicd

> Document de référence pour la vision et le périmètre du POC. Tous les autres
> dépôts (`cluster`, `helloworld`, `ci-templates`, `toolbox`, `helloworld-iac`,
> `platform-gitops`) pointent vers ce fichier pour la vision globale.

## Intention du projet

Ce dépôt porte le bootstrap et la maintenance d'une chaîne CI/CD complète,
autohébergée sur un cluster Kubernetes local. L'objectif est de démontrer un
pattern reproductible couvrant :

- un cluster Kubernetes local reproductible (`cluster`) ;
- une plateforme GitOps pilotée par ArgoCD, avec GitLab, un runner CI et un
  registry Docker internes ;
- un template CI partagé et versionné (`ci-templates`) utilisable sans
  duplication de logique dans chaque application ;
- une application de référence (`helloworld`) qui démontre le chemin complet
  build → registry → manifests → ArgoCD → cluster.

## Composants de la plateforme

| Composant | Rôle |
|-----------|------|
| **ArgoCD** | GitOps — synchronise le cluster depuis `platform-gitops` |
| **GitLab** | Héberge le code source et exécute les pipelines CI/CD |
| **GitLab Runner** | Exécution des jobs CI dans le cluster (Kubernetes executor) |
| **Registry Docker** | Stocke les images construites par Kaniko |
| **Traefik + Gateway API** | Exposition HTTP des services via HTTPRoutes |
| **MetalLB** | Load balancer bare-metal pour exposer Traefik |

## Pattern CI/CD applicatif

Le pattern est conçu pour être répliqué à l'identique sur n'importe quelle
application :

1. Un merge sur `main` déclenche un build Kaniko et un `deploy-dev`.
2. `semantic-release` analyse les commits conventionnels et crée un tag `vX.Y.Z`.
3. Le tag déclenche `build-rec` (retag de l'image SHA existante) et `deploy-rec`.
4. `deploy-preprod` et `deploy-prod` sont manuels, déclenchés depuis GitLab CI.
5. Chaque `deploy-*` pousse un commit sur la branche correspondante du dépôt
   manifests (`-iac`). ArgoCD synchronise automatiquement.

## Objectif de scaling

Ajouter une application se limite à une seule MR : ajouter
`argocd/apps/<app>.yaml` (name, description, services) sur le projet GitLab
`platform-gitops`. Son pipeline `.gitlab-ci.yml` se charge ensuite, au merge,
de :
- générer la configuration GitOps dédiée (`argocd/generated/apps/<app>/`) ;
- déclarer les projets GitLab correspondants dans `gitlab-projects-iac`
  (`terraform/apps.auto.tfvars.json`), appliqué par le job Terraform `gitlab-iac`
  (créés vides, sans import GitHub, sauf apps historiques) ;
- laisser les jobs CI/CD applicatifs initialiser le contenu et les variables
  nécessaires aux pipelines.

Aucune duplication de logique CI, aucune configuration ArgoCD manuelle, aucune
étape Terraform manuelle.

## Critères d'acceptation du POC

- `make bootstrap` depuis ce dépôt déploie la plateforme complète sur un
  cluster vierge, sans configuration applicative préchargée.
- GitLab est accessible sur `https://gitlab.<domaine>`.
- ArgoCD est accessible sur `https://argocd.<domaine>` avec SSO GitLab.
- Le registry est accessible sur `http://registry.<domaine>`.
- Après onboarding applicatif, un pipeline complet (build → dev → rec → prod)
  s'exécute sans intervention manuelle hormis les gates de promotion.

## Limites acceptées (non-objectifs du POC)

- **Branches manifests non protégées contre un push humain direct** (`dev`,
  `rec`, `preprod`) : seule `main` est protégée. Acceptable en contexte
  mono-opérateur ; à traiter avec une vraie équipe via comptes de service.
- **`GITLAB_PUSH_TOKEN` est un token personnel `root` à scope complet** : rayon
  d'explosion maximal en cas de fuite. Cible long terme : token de projet par
  app, scopé au strict nécessaire.
- **TLS auto-signé** : les scripts désactivent la vérification TLS par défaut
  (`GITLAB_INSECURE_TLS=true`). Non adapté à un environnement ouvert.
- **Cluster non hautement disponible** : 1 master + 1 worker, sans redondance.
  Ce POC ne vise pas la disponibilité de production.
