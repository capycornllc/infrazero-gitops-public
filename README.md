# infrazero-gitops-public

Bootstrap
- Edit `config/app-config.yaml` (bootstrap repoURL/env, app name/namespace, workloads, optional `secretsFolder`). `env` should match `dev`, `test`, or `prod`.
- Apply the root app: `kubectl apply -f apps/root/application.yaml`.
- Argo CD syncs the selected `clusters/<env>` overlay and the app chart.
- Validate config locally: `python scripts/validate_app_config.py --config config/app-config.yaml --schema schemas/app-config.schema.json`.

Payload-driven generation
- Generate `AppConfig` from `deployed_apps_json` (new shape: app-level fields + workload array):
  - `python scripts/generate_app_config.py --deployed-apps-json "$DEPLOYED_APPS_JSON" --output .tmp/generated.app-config.yaml --schema schemas/app-config.schema.json --base-domain example.com`
- The chart accepts workload `command` as either string (rendered via `sh -lc`) or string array.
- When `spec.workloads[].csi.enabled=true`, the chart automatically creates `/app/.env` from mounted secret files (default mount path `/mnt/secrets`) using an init container.
- Multiline secret values are written as escaped `\n` sequences in `.env`; updates are applied on pod restart.

Infisical Kubernetes auth bootstrap
- Create required kube-system secrets:
  - `infisical-admin-token` with keys `host` and `token` (Infisical admin bearer token)
  - `infisical-organization` containing the organization name or ID
  - `infisical-project-name` containing the project name
- Secret data key can be `value` or the legacy key name (infisical_organization / infisical_project_name).
- Run once per cluster: `kubectl apply -k clusters/<env>/bootstrap/infisical-k8s-auth`
- Re-run by deleting the Job: `kubectl -n infisical-bootstrap delete job infisical-k8s-auth-bootstrap`
- Cloud-init trigger: after k3s is Ready, apply the kustomization and skip if the Job already succeeded.

Infisical secrets operator
- Argo CD Application: `clusters/<env>/applications/platform/infisical-secrets-operator.yaml`
- Example InfisicalSecret CRD: `docs/examples/infisicalsecret.yaml`
- Helm alternative (if you do not use Argo CD): `helm repo add infisical-helm-charts https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts` then `helm install secrets-operator infisical-helm-charts/secrets-operator -n infisical-operator --create-namespace`
- The example CRD is not applied by default; add it via overlays when needed.

Infisical/Kubernetes auth requirements
- Infisical: admin API token for bootstrap, organization ID, and project name; the Job creates a machine identity and configures Kubernetes Auth for it.
- Kubernetes: the Job creates a token reviewer service account bound to `system:auth-delegator` and uses the cluster CA from `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt`.
- The Job computes allowed namespaces and service account names from the cluster and applies them to the identity (rerun after changes).
- Token reviewer JWT is sourced from a long-lived service account token secret created by the Job.
- The Job writes a kube-system Secret named `infisical-bootstrap-result` containing identityId and projectId for automation.
- The Job sets Kubernetes Auth `allowedAudience` from `INFISICAL_ALLOWED_AUDIENCE` (defaults to `infisical`).
- The Job uses `KUBE_HOST` from the bootstrap ConfigMap; patch it to a URL reachable by the Infisical VM (for example `https://k3s.aw.torrf.com:6443`).
- If your Infisical instance uses a private CA, set `caCertificate` in SecretProviderClass and ensure the bootstrap Job can trust the Infisical host.

Layout
- `apps/root/application.yaml`: root Argo CD Application (app-of-apps entrypoint).
- `clusters/<env>/kustomization.yaml`: environment overlays (dev/test/prod).
- `clusters/<env>/bootstrap/infisical-k8s-auth`: Job for Infisical Kubernetes Auth bootstrap.
- `clusters/<env>/project.yaml`: Argo CD Project with repo allowlist.
- `clusters/<env>/applications/app/application.yaml`: single Argo CD Application for the app.
- `clusters/<env>/applications/platform/*.yaml`: platform add-ons (ingress-nginx, cert-manager, secrets-store CSI, Infisical provider).
- `config/app-config.yaml`: single source of truth for workloads and routing.
- `charts/app/`: Helm chart renderer for workloads.
- `platform/cert-manager/cluster-issuers.yaml`: Let's Encrypt ClusterIssuers (staging/prod).
- `platform/infisical/secretproviderclass.yaml`: Infisical SecretProviderClass template (Kubernetes auth parameters).
- `docs/examples/infisicalsecret.yaml`: InfisicalSecret CRD example for the secrets operator.
- `schemas/app-config.schema.json`: config schema.
