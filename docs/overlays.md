# Overlays and customizations for app-specific deployments

This repository is the public GitOps base. The infra pipeline clones it into a private GitOps repo and applies overlays or patches to make it specific to one customer deployment. This document lists the required customizations and the files they target.

## Required inputs
- Private GitOps repo URL and target revision.
- Environment name (dev, test, prod) and Argo CD namespace.
- App name and Kubernetes namespace.
- Base domain, ingress class name, and TLS issuer settings.
- deployed_apps array from the UI (id, ghcr_image, fqdn, replica_count, memory_limit, cpu_limit).
- Optional: per-app ports, image tag, image pull secrets, Infisical connection info, secret mappings.

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
- spec.parameters.projectSlug, envSlug, secretsPath, and objects should match the app's Infisical setup.
- spec.parameters.authSecretName is fixed to `infisical-readonly-token`.
- spec.parameters.authSecretNamespace is fixed to `kube-system`.
- The auth secret should contain `client-id` and `client-secret` keys for Universal Auth.

## Additions expected from infra overlay
These files may be added by the infra overlay when generating the private repo.
- Additional SecretProviderClass manifests in the app namespace for Infisical, referenced by spec.workloads[].csi.secretProviderClass.
- Optional image pull secret resources if images are private, and reference them in spec.global.imagePullSecrets.

## Notes
- scripts/sync-bootstrap.ps1 can update apps/root/application.yaml, applications/app/application.yaml, applications/platform/*.yaml, and projects/*/project.yaml from spec.bootstrap and spec.global values.
- scripts/validate-config.ps1 validates config/app-config.yaml against schemas/app-config.schema.json.
