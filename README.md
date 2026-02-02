# infrazero-gitops-public

Bootstrap
- Edit `config/app-config.yaml` (bootstrap repoURL/env, app name/namespace, workloads). `env` should match `dev`, `test`, or `prod`.
- Run `scripts/sync-bootstrap.ps1` to update Argo CD manifests from config.
- Apply the root app: `kubectl apply -f apps/root/application.yaml`.
- Argo CD syncs the selected `clusters/<env>` overlay and the app chart.

Validation
- `scripts/validate-config.ps1` (requires Python + `pyyaml` + `jsonschema`).

Layout
- `apps/root/application.yaml`: root Argo CD Application (app-of-apps entrypoint).
- `clusters/<env>/kustomization.yaml`: environment overlays (dev/test/prod).
- `projects/<env>/project.yaml`: Argo CD Project with repo allowlist.
- `applications/app/application.yaml`: single Argo CD Application for the app.
- `applications/platform/*.yaml`: platform add-ons (ingress-nginx, cert-manager, secrets-store CSI, Infisical provider).
- `config/app-config.yaml`: single source of truth for workloads and routing.
- `charts/app/`: Helm chart renderer for workloads.
- `platform/cert-manager/cluster-issuers.yaml`: Let's Encrypt ClusterIssuers (staging/prod).
- `schemas/app-config.schema.json`: config schema.
- `scripts/`: config validation + bootstrap sync.
