# PRD: Public GitOps Template for k3s + Argo CD

## Summary
Create a public, reusable GitOps repository template that deploys any web app onto k3s using Argo CD. The template must keep all app workloads in a single Argo CD Application and a single Kubernetes namespace, and provide one main config file where operators define pods, replicas, resources, domains, TLS, and image tags. The template must not include any in-cluster secret manager; secrets come from an external system (for example an externally hosted Infisical instance) via CSI.

## Background and context
The current repo uses an app-of-apps Argo CD structure, Kustomize overlays, pinned Helm charts for platform add-ons, and multiple namespaces for app components. It also deploys a self-hosted secret manager in-cluster. The new template should keep the proven GitOps structure and k3s compatibility while simplifying app delivery into a single namespace and a single app definition controlled from one config file. It must be safe to publish and generic for any organization.

## Goals
- Provide a public GitOps template for k3s + Argo CD that is generic and reusable.
- Keep all app workloads in one Kubernetes namespace and one Argo CD Application.
- Provide a single main config file as the source of truth for:
  - Workload definitions (pods/services), images, tags
  - Replica counts, resources, probes
  - Domain names and TLS/Let's Encrypt settings
  - Optional secret mounts using CSI
- Support external secret management (no in-cluster secret manager).
- Keep platform add-ons (ingress-nginx, cert-manager, secrets-store CSI) pinned and GitOps-managed.

## Non-goals
- Running a self-hosted secret manager inside the cluster.
- Multi-namespace app layouts in the template.
- Multi-cluster or multi-tenant orchestration.
- Shipping opinionated monitoring or logging stacks (can be added later).

## Users and personas
- Platform operator: bootstraps clusters, configures ingress/TLS, manages Argo CD.
- Application developer: defines services and images in the main config file.
- CI system: updates image tags in the main config file on each build.

## Scope and requirements

### Repository structure (template)
- apps/root/application.yaml: Argo CD app-of-apps bootstrap.
- clusters/<env>/kustomization.yaml: environment roots (dev/test/prod).
- projects/<env>/project.yaml: Argo CD projects and repo allowlist.
- platform/: cluster add-ons (ingress-nginx, cert-manager, secrets-store CSI, optional sealed-secrets, namespaces, network policies).
- applications/app/: single Argo CD Application for the entire web app.
- config/app-config.yaml: the single source of truth for app workloads and routing.
- charts/app/: custom Helm chart (preferred) or a Kustomize-based renderer that consumes config/app-config.yaml.
- docs/: quickstart and operations guides.

### Main config file (single source of truth)
The template must include a single YAML config file with a clear, versioned schema. It should support:
- Global settings:
  - app name and namespace
  - base domain, TLS enabled flag, and default ClusterIssuer
  - external secret manager URL and auth mode (if using CSI)
  - default resource presets (optional)
- Workloads list (multiple services in one namespace):
  - type: Deployment or CronJob (optionally Job)
  - image repository and tag
  - replica count (for Deployments)
  - container ports and service ports
  - health probes (readiness/liveness)
  - resource requests/limits
  - environment variables (plain and from CSI)
  - volume mounts (including CSI secret volume)
  - ingress rules per workload (hostnames, paths, TLS secret name)
- Image update fields designed for CI to edit (for example services[].image.tag).
- Optional toggles for:
  - creating Services and Ingresses
  - enabling TLS (Let's Encrypt prod/staging)
  - network policies

### App rendering and delivery
- Prefer a custom Helm chart in-repo that renders all workloads from the single config file.
- Argo CD should deploy the app via a single Application resource pointing to the chart and values file.
- All resources should be labeled consistently and confined to the configured namespace.
- The repo should ship a JSON Schema (or similar) for config/app-config.yaml and a validation script.

### Platform components (k3s-compatible)
- ingress-nginx: NodePort configuration suitable for k3s without CCM.
- cert-manager: ClusterIssuers for Let's Encrypt staging and production.
- secrets-store CSI driver + external provider (Infisical or similar) configured without in-cluster secret manager.
- optional sealed-secrets for small bootstrap secrets (disabled by default in the template).
- namespaces and baseline network policies (default deny with ingress-nginx exceptions).

### CI/CD integration
- CI updates image tags in config/app-config.yaml on each build.
- Renovate (or similar) updates pinned chart versions for platform add-ons.
- A lightweight validation step verifies config schema and kustomize/helm render.

### Documentation
- Quickstart: clone template, edit config/app-config.yaml, apply root app.
- Operations: Argo CD access, ingress/TLS setup, image tag update flow.
- Secrets: how to connect to an external secret manager and define secret mounts.

## User journeys
1) New project bootstrap
- Clone template.
- Edit config/app-config.yaml (namespaces, domains, workloads, images).
- Apply apps/root/application.yaml in the cluster.
- Argo CD syncs platform and app.

2) Add a new service
- Add a new workload entry in config/app-config.yaml.
- Commit and push; Argo CD renders and deploys the new Deployment/Service/Ingress.

3) Update image tags
- CI pipeline updates services[].image.tag in config/app-config.yaml.
- Argo CD syncs and rolls out updated images.

## Success metrics
- Time from clone to first successful deploy <= 30 minutes on a fresh k3s cluster.
- All app changes captured by a single config file and rendered by Argo CD.
- Zero secrets stored in the repo.

## Risks and mitigations
- External secret manager dependency: document outage behavior and use CSI retries.
- Single namespace blast radius: enforce labels, network policies, and resource quotas.
- Ingress/TLS complexity: ship clear defaults and staging/prod issuer toggles.

## Epics and stories

### Epic 1: Template repo skeleton and bootstrap
Stories:
- As an operator, I can apply a root Argo CD Application that bootstraps the cluster.
- As an operator, I can target different environments using clusters/<env> overlays.
- As an operator, I can control allowed source repos via an Argo CD Project.

### Epic 2: Single config file and app renderer
Stories:
- As a developer, I can define multiple workloads in one config/app-config.yaml file.
- As a developer, I can set replicas, resources, probes, and ports per workload.
- As a developer, I can define Ingress rules and TLS per workload.
- As a developer, I can mount external secrets via CSI by configuring the workload.
- As an operator, I can validate the config file with a schema and fail fast on errors.

### Epic 3: Platform add-ons for k3s
Stories:
- As an operator, I can install ingress-nginx with NodePort defaults for k3s.
- As an operator, I can install cert-manager with staging and prod ClusterIssuers.
- As an operator, I can install secrets-store CSI and an external provider without in-cluster secret manager.
- As an operator, I can enable baseline network policies and namespaces via GitOps.

### Epic 4: TLS and domain management
Stories:
- As an operator, I can set base domains and per-service hosts in one config file.
- As an operator, I can switch between Let's Encrypt staging and prod issuers per environment.
- As an operator, I can disable TLS for internal-only services.

### Epic 5: CI-driven image updates
Stories:
- As a CI system, I can update image tags in config/app-config.yaml and open a PR.
- As an operator, I can auto-sync Argo CD to roll out the new images safely.
- As an operator, I can audit image tag changes via Git history.

### Epic 6: Documentation and onboarding
Stories:
- As a new user, I can follow a quickstart to deploy my app on k3s.
- As an operator, I can find clear instructions for Argo CD access and troubleshooting.
- As a developer, I can understand how to add services and secrets from docs.

## Open questions
- Should the app renderer be Helm-first (preferred) or a Kustomize generator with committed output?
- Do we need optional HPA configuration in the main config file from day one?
- Should the template include resource quotas/limit ranges by default?

