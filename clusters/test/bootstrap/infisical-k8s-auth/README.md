# Infisical Kubernetes Auth Bootstrap (test)

This kustomization runs a one-time Job that configures Kubernetes Auth for a machine identity in Infisical and links it to a project.

## Required secrets (kube-system)
- `infisical-admin-token` with keys `host` and `token` (Infisical admin bearer token)
- `infisical-organization` containing the organization name or ID
- `infisical-project-name` containing the project name
- Secret data key can be `value` or the legacy key name (infisical_organization / infisical_project_name).

## Run
```bash
kubectl apply -k clusters/test/bootstrap/infisical-k8s-auth
```

## Cloud-init trigger
```bash
if [ "$(kubectl -n infisical-bootstrap get job infisical-k8s-auth-bootstrap -o jsonpath='{.status.succeeded}' 2>/dev/null)" != "1" ]; then
  kubectl apply -k clusters/test/bootstrap/infisical-k8s-auth
fi
```

## Re-run
```bash
kubectl -n infisical-bootstrap delete job infisical-k8s-auth-bootstrap
kubectl apply -k clusters/test/bootstrap/infisical-k8s-auth
```

## Inspect
```bash
kubectl -n infisical-bootstrap get jobs
kubectl -n infisical-bootstrap get pods
kubectl -n infisical-bootstrap logs job/infisical-k8s-auth-bootstrap
```

## What it does
- Creates a token reviewer service account in `kube-system` and binds it to `system:auth-delegator` (cluster-scoped ClusterRoleBinding) via kustomization.
- Computes allowed namespaces and service account names dynamically (excludes kube-system, argocd, kube-public, kube-node-lease).
- Creates/updates an Infisical machine identity named `k3s-test-operator` and attaches it to the project.
- Configures Kubernetes Auth with the cluster API host, CA cert, token reviewer JWT, and allowed lists (expects the token reviewer binding to exist).
- Writes a result Secret in kube-system named `infisical-bootstrap-result` with identityId and projectId.

## Notes
- Re-run this Job when new namespaces or service accounts are added to update allowlists.
- If Infisical uses a private CA, ensure the Job can trust the Infisical host and set `caCertificate` in SecretProviderClass.
