#!/usr/bin/env python
"""Generate config/app-config.yaml from deployed_apps_json payloads.

Supports the new payload shape:
{
  "app_name": "my-app",
  "ghcr_image": "ghcr.io/org/app:tag",
  "secrets_folder": "my-app",
  "workloads": [ ... ]
}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    import jsonschema
except ImportError:  # pragma: no cover - validated in CI
    jsonschema = None


DEFAULT_REPO_URL = "https://github.com/your-org/your-repo"
DEFAULT_ENV = "dev"
DEFAULT_TARGET_REVISION = "main"
DEFAULT_ARGO_NAMESPACE = "argocd"
DEFAULT_BASE_DOMAIN = "example.com"
DEFAULT_INGRESS_CLASS_NAME = "traefik"
DEFAULT_CLUSTER_ISSUER = "letsencrypt-prod"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AppConfig from deployed_apps_json.")
    parser.add_argument("--deployed-apps-json", help="Raw deployed_apps_json payload.")
    parser.add_argument("--deployed-apps-file", help="Path to a JSON file with payload.")
    parser.add_argument("--output", required=True, help="Path to write generated AppConfig YAML.")
    parser.add_argument("--schema", help="Optional schema path for post-generation validation.")
    parser.add_argument("--bootstrap-repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--bootstrap-env", default=DEFAULT_ENV)
    parser.add_argument("--bootstrap-target-revision", default=DEFAULT_TARGET_REVISION)
    parser.add_argument("--bootstrap-argo-namespace", default=DEFAULT_ARGO_NAMESPACE)
    parser.add_argument("--namespace", help="Override Kubernetes namespace; defaults to app_name.")
    parser.add_argument("--base-domain", default=DEFAULT_BASE_DOMAIN)
    parser.add_argument("--ingress-class-name", default=DEFAULT_INGRESS_CLASS_NAME)
    parser.add_argument(
        "--tls-enabled",
        choices=["true", "false"],
        default="true",
        help="Enable ingress TLS defaults (true/false).",
    )
    parser.add_argument("--tls-cluster-issuer", default=DEFAULT_CLUSTER_ISSUER)
    parser.add_argument("--default-container-port", type=int, default=8080)
    parser.add_argument("--default-service-port", type=int, default=80)
    return parser.parse_args()


def load_payload(args: argparse.Namespace) -> Any:
    raw = None
    if args.deployed_apps_json:
        raw = args.deployed_apps_json
    elif args.deployed_apps_file:
        raw = Path(args.deployed_apps_file).read_text(encoding="utf-8")
    else:
        env_value = os.environ.get("DEPLOYED_APPS_JSON")
        if env_value:
            raw = env_value

    if raw is None:
        raise ValueError(
            "Missing payload: provide --deployed-apps-json, --deployed-apps-file, "
            "or DEPLOYED_APPS_JSON."
        )

    parsed = json.loads(raw)
    # Some secret stores provide a JSON-encoded string inside JSON.
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    return parsed


def split_image(image: str) -> tuple[str, str]:
    if not image or not isinstance(image, str):
        raise ValueError("ghcr_image must be a non-empty string")
    if "@sha256:" in image:
        raise ValueError("Digest-style images are not supported in this generator")

    # Split on the final colon only when it is part of tag syntax.
    match = re.match(r"^(?P<repo>.+?)(?::(?P<tag>[^:/]+))?$", image)
    if not match:
        raise ValueError(f"Invalid image reference: {image}")
    repo = match.group("repo")
    tag = match.group("tag") or "latest"
    return repo, tag


def to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def pick(dct: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in dct and dct[key] is not None:
            return dct[key]
    return default


def normalize_kind(kind: Any, preset: Any) -> str:
    if kind:
        normalized = str(kind).strip().lower()
    else:
        normalized = ""

    if not normalized and preset:
        preset_normalized = str(preset).strip().lower()
        if preset_normalized == "scheduler":
            normalized = "cronjob"
        else:
            normalized = "deployment"

    if normalized in {"deployment", "deploy"}:
        return "Deployment"
    if normalized in {"cronjob", "cron"}:
        return "CronJob"
    if normalized == "job":
        return "Job"
    if not normalized:
        return "Deployment"
    raise ValueError(f"Unsupported workload kind: {kind}")


def normalize_ports(ports: Any) -> list[dict[str, Any]]:
    if not ports:
        return []
    if not isinstance(ports, list):
        raise ValueError("workload ports must be a list")

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(ports):
        if isinstance(entry, int):
            container_port = entry
            service_port = entry
            name = f"port-{container_port}"
            protocol = "TCP"
        elif isinstance(entry, dict):
            container_port = pick(
                entry,
                ["containerPort", "container_port", "container", "port"],
            )
            if container_port is None:
                raise ValueError("Port entries require containerPort/container_port/port")
            service_port = pick(
                entry,
                ["servicePort", "service_port", "service"],
                default=container_port,
            )
            name = pick(entry, ["name"], default=f"port-{container_port}")
            protocol = pick(entry, ["protocol"], default="TCP")
        else:
            raise ValueError("Port entries must be int or object")

        normalized.append(
            {
                "name": str(name),
                "containerPort": int(container_port),
                "servicePort": int(service_port),
                "protocol": str(protocol),
            }
        )
    return normalized


def build_secret_provider_class_name(workload_name: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]+", "-", workload_name.lower()).strip("-")
    return f"infisical-{sanitized}"


def normalize_workload(
    app_payload: dict[str, Any],
    workload_payload: dict[str, Any],
    args: argparse.Namespace,
    image_repository: str,
    image_tag: str,
    tls_enabled: bool,
) -> dict[str, Any]:
    workload_name = pick(workload_payload, ["workload_name", "name", "id"])
    if not workload_name:
        raise ValueError("workload_name is required for every workload")
    workload_name = str(workload_name)

    preset = pick(workload_payload, ["preset"])
    workload_kind = normalize_kind(pick(workload_payload, ["kind", "type"]), preset)

    item: dict[str, Any] = {
        "name": workload_name,
        "type": workload_kind,
        "image": {
            "repository": image_repository,
            "tag": image_tag,
            "pullPolicy": "IfNotPresent",
        },
    }

    command = pick(workload_payload, ["command"])
    if command is not None and command != "":
        item["command"] = command

    probes = pick(workload_payload, ["probes"])
    if isinstance(probes, dict) and probes:
        item["probes"] = probes

    memory_limit = pick(workload_payload, ["memory_limit", "memoryLimit"])
    cpu_limit = pick(workload_payload, ["cpu_limit", "cpuLimit"])
    limits: dict[str, Any] = {}
    if memory_limit:
        limits["memory"] = str(memory_limit)
    if cpu_limit:
        limits["cpu"] = str(cpu_limit)
    if limits:
        item["resources"] = {"limits": limits}

    secrets_folder = pick(
        workload_payload,
        ["secrets_folder", "secretsFolder"],
        default=pick(app_payload, ["secrets_folder", "secretsFolder"]),
    )
    if secrets_folder:
        item["secretsFolder"] = str(secrets_folder)
        item["csi"] = {
            "enabled": True,
            "driver": "secrets-store.csi.k8s.io",
            "secretProviderClass": build_secret_provider_class_name(workload_name),
            "readOnly": True,
            "mountPath": "/mnt/secrets",
            "volumeAttributes": {},
        }

    if workload_kind in {"CronJob", "Job"}:
        if workload_kind == "CronJob":
            schedule = pick(workload_payload, ["schedule"])
            if not schedule:
                raise ValueError(f"CronJob workload '{workload_name}' is missing schedule")
            item["schedule"] = str(schedule)
        return item

    replicas = pick(workload_payload, ["replica_count", "replicas"])
    item["replicas"] = int(replicas) if replicas is not None else 1

    fqdn = pick(workload_payload, ["fqdn", "host"])
    expose = to_bool(
        pick(workload_payload, ["expose"], default=None),
        default=bool(fqdn) or str(preset).strip().lower() == "web",
    )

    ports = normalize_ports(pick(workload_payload, ["ports"], default=[]))
    if expose and not ports:
        ports = [
            {
                "name": "http",
                "containerPort": int(args.default_container_port),
                "servicePort": int(args.default_service_port),
                "protocol": "TCP",
            }
        ]
    if ports:
        item["ports"] = ports

    item["service"] = {
        "enabled": expose,
        "type": "ClusterIP",
        "annotations": {},
    }

    ingress: dict[str, Any] = {"enabled": expose}
    if expose:
        host = str(fqdn) if fqdn else f"{workload_name}.{args.base_domain}"
        default_service_port = (
            ports[0]["servicePort"] if ports else int(args.default_service_port)
        )
        ingress.update(
            {
                "className": "",
                "annotations": {},
                "hosts": [
                    {
                        "host": host,
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "servicePort": default_service_port,
                            }
                        ],
                    }
                ],
                "tls": {"enabled": tls_enabled, "secretName": ""},
            }
        )
    item["ingress"] = ingress

    return item


def normalize_apps_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "app_name" in payload and "workloads" in payload:
            return [payload]
        if "apps" in payload and isinstance(payload["apps"], list):
            return payload["apps"]
        if "deployed_apps" in payload and isinstance(payload["deployed_apps"], list):
            # Legacy shape support.
            return [
                {
                    "app_name": payload.get("app_name", "app"),
                    "ghcr_image": payload.get("ghcr_image", ""),
                    "secrets_folder": payload.get("secrets_folder", ""),
                    "workloads": [
                        {
                            "workload_name": app.get("id"),
                            "kind": "Deployment",
                            "fqdn": app.get("fqdn"),
                            "replica_count": app.get("replica_count"),
                            "memory_limit": app.get("memory_limit"),
                            "cpu_limit": app.get("cpu_limit"),
                            "ports": app.get("ports", []),
                            "expose": bool(app.get("fqdn")),
                            "command": app.get("command"),
                        }
                        for app in payload["deployed_apps"]
                    ],
                }
            ]

    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "workloads" in payload[0]:
            return payload
        # Legacy list of deployment-only entries.
        return [
            {
                "app_name": "app",
                "ghcr_image": "",
                "secrets_folder": "",
                "workloads": [
                    {
                        "workload_name": app.get("id"),
                        "kind": "Deployment",
                        "fqdn": app.get("fqdn"),
                        "replica_count": app.get("replica_count"),
                        "memory_limit": app.get("memory_limit"),
                        "cpu_limit": app.get("cpu_limit"),
                        "ports": app.get("ports", []),
                        "expose": bool(app.get("fqdn")),
                        "command": app.get("command"),
                    }
                    for app in payload
                ],
            }
        ]

    raise ValueError("Unsupported payload shape")


def build_app_config(app_payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    app_name = pick(app_payload, ["app_name", "name"])
    if not app_name:
        raise ValueError("app_name is required in deployed_apps_json")
    app_name = str(app_name)
    namespace = args.namespace or app_name
    tls_enabled = to_bool(args.tls_enabled, default=True)

    image_value = pick(app_payload, ["ghcr_image"])
    if not image_value:
        raise ValueError("ghcr_image is required in deployed_apps_json")
    image_repository, image_tag = split_image(str(image_value))

    workloads = pick(app_payload, ["workloads"])
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("workloads must be a non-empty list")

    normalized_workloads = [
        normalize_workload(
            app_payload=app_payload,
            workload_payload=workload,
            args=args,
            image_repository=image_repository,
            image_tag=image_tag,
            tls_enabled=tls_enabled,
        )
        for workload in workloads
    ]

    return {
        "apiVersion": "infrazero.app/v1alpha1",
        "kind": "AppConfig",
        "metadata": {"name": app_name},
        "spec": {
            "schemaVersion": 1,
            "bootstrap": {
                "repoURL": args.bootstrap_repo_url,
                "env": args.bootstrap_env,
                "targetRevision": args.bootstrap_target_revision,
                "argoNamespace": args.bootstrap_argo_namespace,
            },
            "global": {
                "name": app_name,
                "namespace": namespace,
                "labels": {},
                "annotations": {},
                "baseDomain": args.base_domain,
                "ingressClassName": args.ingress_class_name,
                "tls": {
                    "enabled": tls_enabled,
                    "clusterIssuer": args.tls_cluster_issuer,
                    "secretName": "",
                },
                "imagePullSecrets": [],
                "serviceAccount": {
                    "create": False,
                    "name": "",
                    "annotations": {},
                },
                "resourcePresets": {},
                "networkPolicy": {
                    "enabled": False,
                    "ingress": [],
                    "egress": [],
                },
            },
            "workloads": normalized_workloads,
        },
    }


def validate_schema(config: dict[str, Any], schema_path: str) -> None:
    if jsonschema is None:
        raise RuntimeError("jsonschema is required for --schema validation")
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    jsonschema.validate(instance=config, schema=schema)


def main() -> int:
    args = parse_args()
    payload = load_payload(args)
    apps = normalize_apps_payload(payload)
    if len(apps) != 1:
        raise ValueError(
            "This GitOps repo supports one app per AppConfig; payload resolved to "
            f"{len(apps)} apps."
        )

    app_config = build_app_config(app_payload=apps[0], args=args)
    if args.schema:
        validate_schema(app_config, args.schema)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(app_config, sort_keys=False)
    output_path.write_text(yaml_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
