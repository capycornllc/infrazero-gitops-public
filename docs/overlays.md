# Overlays and customizations for app-specific deployments

This repository is the public GitOps base. The infra pipeline clones it into a private GitOps repo and applies overlays or patches to make it specific to one customer deployment. This document lists the required customizations and the files they target.

## Required inputs
- Private GitOps repo URL and target revision.
- Environment name (dev, test, prod) and Argo CD namespace.
- App name and Kubernetes namespace.
- Base domain, ingress class name, and TLS issuer settings.
- deployed_apps_json payload from the UI using the new shape:
  - app-level: app_name, ghcr_image, secrets_folder, workloads[]
  - workload-level: workload_name, preset, kind, command, schedule, expose, fqdn, ports, probes, replica_count, memory_limit, cpu_limit
- Optional: per-app ports, image tag, image pull secrets, Infisical connection info (infisicalUrl, identityId, projectId, envSlug, caCertificate), secret mappings.

## Overlay targets (patch or regenerate)

### config/app-config.yaml
Replace the file with a generated config derived from deployed_apps_json and global settings.

Required fields to set:
- spec.bootstrap.repoURL, spec.bootstrap.env, spec.bootstrap.targetRevision, spec.bootstrap.argoNamespace
- spec.global.name, spec.global.namespace, spec.global.baseDomain
- spec.global.ingressClassName, spec.global.tls.enabled, spec.global.tls.clusterIssuer
- spec.global.imagePullSecrets (if needed for private images)
- spec.workloads[] generated from deployed_apps_json.workloads

Mapping guidance for deployed_apps_json to spec.workloads[]:
| deployed_apps_json field | app-config path | notes |
| --- | --- | --- |
| app_name | metadata.name / spec.global.name | Single app per AppConfig. |
| ghcr_image | spec.workloads[].image.repository + image.tag | Split image tag if present. |
| secrets_folder (app-level) | spec.workloads[].secretsFolder | Use as default; allow per-workload override. |
| workloads[].workload_name | spec.workloads[].name | Keep passthrough. |
| workloads[].kind | spec.workloads[].type | `Deployment` or `CronJob`. |
| workloads[].replica_count | spec.workloads[].replicas | Deployment workloads only. |
| workloads[].schedule | spec.workloads[].schedule | CronJob workloads only. |
| workloads[].memory_limit | spec.workloads[].resources.limits.memory | |
| workloads[].cpu_limit | spec.workloads[].resources.limits.cpu | |
| workloads[].ports[] | spec.workloads[].ports[] | Deployment workloads that expose HTTP/TCP. |
| workloads[].expose | spec.workloads[].service.enabled + ingress.enabled | Exposed workloads create Service/Ingress. |
| workloads[].fqdn | spec.workloads[].ingress.hosts[0].host | Used when ingress is enabled. |
| workloads[].probes | spec.workloads[].probes | Supports readiness/liveness probes. |
| workloads[].command | spec.workloads[].command | String command is rendered as `sh -lc "<command>"`. |

Additional workload guidance:
- web workloads should be `type: Deployment` with service/ingress enabled and at least one port.
- queue/internal worker workloads can be `type: Deployment` with service/ingress disabled and zero ports.
- scheduler workloads should be `type: CronJob` with a schedule and no service/ingress.
- spec.workloads[].csi should be enabled when secrets are required, with secretProviderClass set to the name of a SecretProviderClass manifest created by the overlay.
Optional workload fields:
- spec.workloads[].secretsFolder: name of the Infisical folder whose secrets should be mounted as files for the workload.
- When ingress TLS is enabled, the chart mounts the TLS secret into the pod at `/mnt/tls` with `tls.crt` and `tls.key`.
- When ingress TLS is enabled and a cluster issuer is set, the chart creates a cert-manager `Certificate` per workload using `ingress.tls.secretName` (or the default `<app>-<workload>-tls`).

### clusters/<env>/applications/app/application.yaml
Patch the Argo CD Application for the app:
- metadata.name should match the app name.
- metadata.namespace should be the Argo CD namespace.
- spec.project should be cluster-<env>.
- spec.source.repoURL and spec.source.targetRevision should point to the private GitOps repo.
- spec.destination.namespace should match the app namespace.

### apps/root/application.yaml
Patch the root Argo CD Application:
- spec.source.repoURL and spec.source.targetRevision should point to the private GitOps repo.
- spec.source.path should be clusters/<env>.
- spec.destination.namespace should be the Argo CD namespace.

### clusters/<env>/project.yaml
Patch the Argo CD Project for the selected environment:
- metadata.name should be cluster-<env>.
- spec.sourceRepos must include the private GitOps repo URL.

### clusters/<env>/kustomization.yaml
Ensure the environment overlay references the app Application and any platform add-ons.
- Platform add-ons are already included; remove or replace entries only if you change the ingress or secrets stack.
- Keep the env label in the `labels` list (pairs.env) with `includeSelectors: true`.

### platform/infisical/secretproviderclass.yaml
Patch the Infisical SecretProviderClass used by workloads:
- metadata.namespace should match the app namespace.
- spec.parameters should be set for Kubernetes auth with the official Infisical CSI provider:
  - infisicalUrl, authMethod, identityId, projectId, envSlug, useDefaultAudience, secrets.

### clusters/<env>/bootstrap/infisical-k8s-auth
Run once per cluster to connect k3s to Infisical via Kubernetes Auth.
- Requires kube-system secrets: infisical-admin-token (host + token), infisical-organization (name or ID), infisical-project-name.
- Secret data key can be `value` or the legacy key name (infisical_organization / infisical_project_name).
- Creates a token reviewer service account and ClusterRoleBinding to system:auth-delegator.
- Creates/updates the Infisical project, machine identity, and Kubernetes auth config.
- Writes a kube-system Secret named `infisical-bootstrap-result` with identityId and projectId for automation.
- Kubernetes Auth `allowedAudience` defaults to `infisical` and can be overridden with `INFISICAL_ALLOWED_AUDIENCE`.
- Kubernetes Auth `kubernetesHost` is taken from the bootstrap ConfigMap `KUBE_HOST`. Patch it to a URL reachable by the Infisical VM (for example `https://k3s.aw.torrf.com:6443`).

### Kubernetes auth requirements (Infisical)
- Create a machine identity in Infisical using Kubernetes Auth and record its identityId for the SecretProviderClass.
- Configure allowed service account names/namespaces (and optional audience) on the identity so only your app workloads can authenticate.
- Decide on Token Reviewer JWT:
  - If you provide a Token Reviewer JWT to Infisical, create a service account, bind it to the `system:auth-delegator` ClusterRole, and generate a long-lived token for the TokenReview API.
  - If you leave Token Reviewer JWT empty, Infisical uses the client's own JWT and that client service account must be bound to `system:auth-delegator`.
- If you use a private/self-signed TLS cert for your Infisical instance, set `caCertificate` in the SecretProviderClass.

### Kubernetes auth requirements (cluster)
- Secrets Store CSI driver should be installed with `tokenRequests[0].audience=infisical` for clusters that support custom audiences.
- For clusters that reject custom audiences, do not set a custom audience and set `useDefaultAudience: "true"` in the SecretProviderClass.
- SecretProviderClass must be created in the same namespace as the pod that mounts it.

### Notes on the infisical-readonly-token secret
- Kubernetes auth does not use the `infisical-readonly-token` secret. If you keep this secret for other tooling, it will be ignored by the CSI provider.
- If you want to store the Infisical host URL in that secret, your infra automation should read it and set `spec.parameters.infisicalUrl` when generating the SecretProviderClass.
- If you choose to use universal auth instead of Kubernetes auth, store `clientId`, `clientSecret`, and `host` in this secret and update SecretProviderClass parameters accordingly.

## Additions expected from infra overlay
These files may be added by the infra overlay when generating the private repo.
- Additional SecretProviderClass manifests in the app namespace for Infisical, referenced by spec.workloads[].csi.secretProviderClass.
- InfisicalSecret CRDs (if using the Infisical Secrets Operator) to sync secrets into app namespaces.
- Optional image pull secret resources if images are private, and reference them in spec.global.imagePullSecrets.

## Notes
- Keep bootstrap metadata (repoURL/env/namespace) consistent across Argo CD Applications and Projects.
