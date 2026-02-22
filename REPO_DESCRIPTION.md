# infrazero-gitops-public - Repository Description

## Purpose
`infrazero-gitops-public` is the cluster desired-state repository. Argo CD applies environment overlays and the app Helm chart to deploy workloads and platform add-ons, including Infisical integrations used for runtime secret delivery.

## What This Repo Owns
- Argo CD app-of-apps structure (`apps/root/application.yaml`).
- Environment overlays (`clusters/dev|test|prod`).
- Application chart templating (`charts/app`) from normalized config.
- Platform add-on manifests:
  - ingress-nginx
  - cert-manager
  - secrets-store-csi-driver
  - infisical-csi-provider
  - infisical-secrets-operator
- Infisical Kubernetes-auth bootstrap job and RBAC.

## Deployment Model
1. Infra pipeline patches/generates app config and commits it here.
2. Argo CD syncs environment overlay + applications.
3. App workloads are rendered from `config/app-config.yaml` (or generated equivalent).
4. Workloads can mount secrets through CSI and generate `/app/.env` from mounted secret files.

## Infisical Integration
- Bootstrap job (`clusters/<env>/bootstrap/infisical-k8s-auth`) expects kube-system secrets:
  - `infisical-admin-token` (`host`, `token`)
  - `infisical-organization`
  - `infisical-project-name`
- Job creates/updates Infisical machine identity, configures Kubernetes auth, and writes result to:
  - `kube-system/infisical-bootstrap-result`
- `platform/infisical/secretproviderclass.yaml` is patched with identity/project details.
- Apps consume secrets via:
  - Secrets Store CSI provider
  - optional Infisical Secrets Operator CRDs

## Key Files
- `clusters/<env>/kustomization.yaml`: overlay entry points.
- `clusters/<env>/applications/*`: Argo CD applications.
- `clusters/<env>/bootstrap/infisical-k8s-auth/*`: one-time cluster auth bootstrap.
- `charts/app/templates/*.yaml`: workload renderers with CSI/.env behavior.
- `platform/infisical/secretproviderclass.yaml`: cluster-wide secret provider template.
- `scripts/generate_app_config.py`, `scripts/validate_app_config.py`: app config generation/validation.

## Contract With Other Repos
- Receives generated app/workload config from UI + infra automation.
- Depends on infra bootstrap outputs for Infisical admin token sync and SecretProviderClass patching.
- Exposes stable GitOps surfaces for application teams to define workloads and secret folders.

## Current Risks / Constraints
- Bootstrap relies on admin-level token material during initial cluster wiring.
- SecretProviderClass values are patched by imperative bootstrap logic and committed back to git.
- Runtime secret path is strong (CSI/provider), but initial trust bootstrap still depends on privileged secrets from infra automation.
