# Overlays and customizations for app-specific deployments

This repository is the public GitOps base. The infra pipeline clones it into a private GitOps repo and applies overlays or patches to make it specific to one customer deployment. This document lists the required customizations and the files they target.

## Required inputs
- Private GitOps repo URL and target revision.
- Environment name (dev, test, prod) and Argo CD namespace.
- App name and Kubernetes namespace.
- Base domain, ingress class name, and TLS issuer settings.
- deployed_apps array from the UI (id, ghcr_image, fqdn, replica_count, memory_limit, cpu_limit).
- Optional: per-app ports, image tag, image pull secrets, Infisical connection info (infisicalUrl, identityId, projectId, envSlug, caCertificate), secret mappings.

## Overlay targets (patch or regenerate)

### config/app-config.yaml
Replace the file with a generated config derived from deployed_apps and global settings.

Required fields to set:
- spec.bootstrap.repoURL, spec.bootstrap.env, spec.bootstrap.targetRevision, spec.bootstrap.argoNamespace
- spec.global.name, spec.global.namespace, spec.global.baseDomain
- spec.global.ingressClassName, spec.global.tls.enabled, spec.global.tls.clusterIssuer
- spec.global.imagePullSecrets (if needed for private images)
- spec.workloads[] generated from deployed_apps

Mapping guidance for deployed_apps to spec.workloads[]:
| deployed_apps field | app-config path | notes |
| --- | --- | --- |
| id | spec.workloads[].name | Must be DNS-1123; sanitize if needed. |
| ghcr_image | spec.workloads[].image.repository | Split tag if present; set image.tag separately. |
| replica_count | spec.workloads[].replicas | Only for Deployment workloads. |
| memory_limit | spec.workloads[].resources.limits.memory | Consider setting requests equal to limits if no requests are provided. |
| cpu_limit | spec.workloads[].resources.limits.cpu | Consider setting requests equal to limits if no requests are provided. |
| fqdn | spec.workloads[].ingress.hosts[0].host | Enable ingress and TLS for public apps. |

Additional required workload fields that are not in deployed_apps:
- spec.workloads[].type should be Deployment for web apps.
- spec.workloads[].ports must include containerPort and servicePort.
- spec.workloads[].service.enabled and spec.workloads[].ingress.enabled should be true for public apps.
- spec.workloads[].csi should be enabled when secrets are required, with secretProviderClass set to the name of a SecretProviderClass manifest created by the overlay.

### applications/app/application.yaml
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

### projects/<env>/project.yaml
Patch the Argo CD Project for the selected environment:
- metadata.name should be cluster-<env>.
- spec.sourceRepos must include the private GitOps repo URL.

### clusters/<env>/kustomization.yaml
Ensure the environment overlay references the app Application and any platform add-ons.
- Platform add-ons are already included; remove or replace entries only if you change the ingress or secrets stack.
- Keep the env label in commonLabels.

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
- Kubernetes Auth `kubernetesHost` defaults to the in-cluster API server URL; override with `INFISICAL_KUBERNETES_HOST` for external Infisical.

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
- scripts/sync-bootstrap.ps1 can update apps/root/application.yaml, applications/app/application.yaml, applications/platform/*.yaml, and projects/*/project.yaml from spec.bootstrap and spec.global values.
- scripts/validate-config.ps1 validates config/app-config.yaml against schemas/app-config.schema.json.
