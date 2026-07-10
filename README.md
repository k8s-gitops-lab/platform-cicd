# platform-bootstrap

Bootstrap technique de la plateforme applicative du POC : installe ArgoCD,
puis attend que GitLab (déployé déclarativement par ArgoCD depuis
`../platform-gitops`) soit prêt pour configurer ses credentials (PAT
Terraform, token runner). Les images applicatives sont poussées sur
GHCR, pas sur un registry interne au cluster.

Ce repo se deploie sur le contexte Kubernetes courant. Il ne cree pas de
cluster. La configuration suivie en continu par ArgoCD vit dans le repo frere
`../platform-gitops`.

## Prerequis

- Un cluster Kubernetes deja provisionne par `infra-iac` (Traefik,
  Gateway API, MetalLB actifs).
- `ansible-playbook` dans le PATH (le role de bootstrap `platform_bootstrap`
  vit dans `ansible/` de ce depot).
- `../platform-gitops` clone a cote, uniquement pour les cibles locales
  `argocd-apps-render` / `check-generated` (ArgoCD lit ce depot depuis GitHub,
  pas depuis le disque).

## Usage

```sh
make bootstrap
```

URLs par defaut (TLS termine par la Gateway avec un certificat auto-signe, a
accepter au premier acces) :

- GitLab : `https://gitlab.192.168.33.100.nip.io`
- ArgoCD : `https://argocd.192.168.33.100.nip.io`
