from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import jsonschema
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "app-config.schema.json"
GENERATOR_SCRIPT = REPO_ROOT / "scripts" / "generate_app_config.py"


def run_checked(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


def render_chart(values_file: Path) -> list[dict]:
    values_rel = values_file.relative_to(REPO_ROOT).as_posix()

    if shutil.which("helm"):
        cmd = ["helm", "template", "tests", "charts/app", "-f", values_rel]
        rendered = run_checked(cmd)
    elif shutil.which("docker"):
        mount_path = REPO_ROOT.resolve().as_posix()
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{mount_path}:/work",
            "-w",
            "/work",
            "alpine/helm:3.14.4",
            "template",
            "tests",
            "charts/app",
            "-f",
            values_rel,
        ]
        rendered = run_checked(cmd)
    else:
        raise AssertionError("Neither helm nor docker is available to render the chart")

    docs = [doc for doc in yaml.safe_load_all(rendered) if doc]
    return docs


def docs_by_kind(docs: list[dict], kind: str) -> list[dict]:
    return [doc for doc in docs if doc.get("kind") == kind]


def find_doc(docs: list[dict], kind: str, name: str) -> dict | None:
    for doc in docs:
        if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name:
            return doc
    return None


def find_mount(container: dict, mount_path: str) -> dict | None:
    for mount in container.get("volumeMounts", []):
        if mount.get("mountPath") == mount_path:
            return mount
    return None


def find_csi_volume(pod_spec: dict) -> dict | None:
    for volume in pod_spec.get("volumes", []):
        if "csi" in volume:
            return volume
    return None


def find_volume_by_name(pod_spec: dict, name: str) -> dict | None:
    for volume in pod_spec.get("volumes", []):
        if volume.get("name") == name:
            return volume
    return None


def find_init_container(pod_spec: dict, name: str) -> dict | None:
    for container in pod_spec.get("initContainers", []):
        if container.get("name") == name:
            return container
    return None


class MultiWorkloadRenderingTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp_dir = REPO_ROOT / ".tmp" / "tests"
        cls.tmp_dir.mkdir(parents=True, exist_ok=True)
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def generate_config(self, payload_fixture_name: str, output_name: str) -> Path:
        payload_path = REPO_ROOT / "tests" / "fixtures" / "payloads" / payload_fixture_name
        output_path = self.tmp_dir / output_name
        cmd = [
            sys.executable,
            str(GENERATOR_SCRIPT),
            "--deployed-apps-file",
            str(payload_path),
            "--output",
            str(output_path),
            "--schema",
            str(SCHEMA_PATH),
            "--bootstrap-repo-url",
            "https://github.com/example/repo",
            "--bootstrap-env",
            "dev",
            "--bootstrap-target-revision",
            "main",
            "--bootstrap-argo-namespace",
            "argocd",
            "--base-domain",
            "example.com",
        ]
        run_checked(cmd)

        instance = yaml.safe_load(output_path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=instance, schema=self.schema)
        return output_path

    def test_web_deployment_exposed_on_http(self) -> None:
        values_file = self.generate_config("web.json", "web.generated.yaml")
        docs = render_chart(values_file)

        self.assertIsNotNone(find_doc(docs, "Deployment", "demo-web"))
        self.assertIsNotNone(find_doc(docs, "Service", "demo-web"))
        ingress = find_doc(docs, "Ingress", "demo-web")
        self.assertIsNotNone(ingress)
        self.assertEqual(ingress["spec"]["rules"][0]["host"], "demo-web.example.com")

        deployment = find_doc(docs, "Deployment", "demo-web")
        pod_spec = deployment["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        self.assertEqual(container["ports"][0]["containerPort"], 3000)
        self.assertIn("readinessProbe", container)
        self.assertIn("livenessProbe", container)
        self.assertEqual(find_mount(container, "/mnt/secrets")["name"], "demo-web-csi")
        dotenv_mount = find_mount(container, "/app/.env")
        self.assertIsNotNone(dotenv_mount)
        self.assertEqual(dotenv_mount["subPath"], ".env")
        self.assertEqual(dotenv_mount["name"], "demo-web-dotenv")

        init_container = find_init_container(pod_spec, "dotenv-writer")
        self.assertIsNotNone(init_container)
        self.assertEqual(find_mount(init_container, "/mnt/secrets")["name"], "demo-web-csi")
        self.assertEqual(find_mount(init_container, "/work")["name"], "demo-web-dotenv")
        self.assertIn("/work/.env", "\n".join(init_container["command"]))

        dotenv_volume = find_volume_by_name(pod_spec, "demo-web-dotenv")
        self.assertIsNotNone(dotenv_volume)
        self.assertEqual(dotenv_volume["emptyDir"], {})

    def test_queue_deployment_internal_without_service_or_ingress(self) -> None:
        values_file = self.generate_config("queue.json", "queue.generated.yaml")
        docs = render_chart(values_file)

        deployment = find_doc(docs, "Deployment", "demo-queue")
        self.assertIsNotNone(deployment)
        self.assertIsNone(find_doc(docs, "Service", "demo-queue"))
        self.assertIsNone(find_doc(docs, "Ingress", "demo-queue"))

        pod_spec = deployment["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        self.assertEqual(container["command"], ["sh", "-lc", "bundle exec sidekiq"])
        self.assertNotIn("ports", container)
        self.assertEqual(find_mount(container, "/mnt/secrets")["name"], "demo-queue-csi")
        dotenv_mount = find_mount(container, "/app/.env")
        self.assertIsNotNone(dotenv_mount)
        self.assertEqual(dotenv_mount["subPath"], ".env")
        self.assertEqual(dotenv_mount["name"], "demo-queue-dotenv")

        init_container = find_init_container(pod_spec, "dotenv-writer")
        self.assertIsNotNone(init_container)
        self.assertEqual(find_mount(init_container, "/mnt/secrets")["name"], "demo-queue-csi")
        self.assertEqual(find_mount(init_container, "/work")["name"], "demo-queue-dotenv")
        self.assertIn("\\n", "\n".join(init_container["command"]))

        csi_volume = find_csi_volume(pod_spec)["csi"]
        self.assertEqual(csi_volume["volumeAttributes"]["secretProviderClass"], "infisical-demo-queue")
        dotenv_volume = find_volume_by_name(pod_spec, "demo-queue-dotenv")
        self.assertIsNotNone(dotenv_volume)
        self.assertEqual(dotenv_volume["emptyDir"], {})

    def test_scheduler_cronjob_internal(self) -> None:
        values_file = self.generate_config("scheduler.json", "scheduler.generated.yaml")
        docs = render_chart(values_file)

        cronjob = find_doc(docs, "CronJob", "demo-scheduler")
        self.assertIsNotNone(cronjob)
        self.assertEqual(cronjob["spec"]["schedule"], "*/15 * * * *")
        self.assertIsNone(find_doc(docs, "Service", "demo-scheduler"))
        self.assertIsNone(find_doc(docs, "Ingress", "demo-scheduler"))

        pod_spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]
        self.assertEqual(
            container["command"], ["sh", "-lc", "python /app/run_scheduled_task.py"]
        )
        self.assertEqual(find_mount(container, "/mnt/secrets")["name"], "demo-scheduler-csi")
        dotenv_mount = find_mount(container, "/app/.env")
        self.assertIsNotNone(dotenv_mount)
        self.assertEqual(dotenv_mount["subPath"], ".env")
        self.assertEqual(dotenv_mount["name"], "demo-scheduler-dotenv")

        init_container = find_init_container(pod_spec, "dotenv-writer")
        self.assertIsNotNone(init_container)
        self.assertEqual(find_mount(init_container, "/mnt/secrets")["name"], "demo-scheduler-csi")
        self.assertEqual(find_mount(init_container, "/work")["name"], "demo-scheduler-dotenv")
        self.assertIn("multiline values are escaped as \\n", "\n".join(init_container["command"]))

        csi_volume = find_csi_volume(pod_spec)["csi"]
        self.assertEqual(
            csi_volume["volumeAttributes"]["secretProviderClass"], "infisical-demo-scheduler"
        )
        dotenv_volume = find_volume_by_name(pod_spec, "demo-scheduler-dotenv")
        self.assertIsNotNone(dotenv_volume)
        self.assertEqual(dotenv_volume["emptyDir"], {})

    def test_mixed_app_with_web_queue_scheduler(self) -> None:
        values_file = self.generate_config("mixed.json", "mixed.generated.yaml")
        docs = render_chart(values_file)

        deployment_names = {
            doc["metadata"]["name"] for doc in docs_by_kind(docs, "Deployment")
        }
        cronjob_names = {doc["metadata"]["name"] for doc in docs_by_kind(docs, "CronJob")}
        service_names = {doc["metadata"]["name"] for doc in docs_by_kind(docs, "Service")}
        ingress_names = {doc["metadata"]["name"] for doc in docs_by_kind(docs, "Ingress")}

        self.assertEqual(deployment_names, {"demo-web", "demo-queue"})
        self.assertEqual(cronjob_names, {"demo-scheduler"})
        self.assertEqual(service_names, {"demo-web"})
        self.assertEqual(ingress_names, {"demo-web"})
        self.assertNotIn("demo-demo-web", deployment_names)

        generated = yaml.safe_load(values_file.read_text(encoding="utf-8"))
        workloads = {item["name"]: item for item in generated["spec"]["workloads"]}
        self.assertEqual(workloads["demo-web"]["secretsFolder"], "demo-web")
        self.assertEqual(workloads["demo-queue"]["secretsFolder"], "demo-queue")
        self.assertEqual(workloads["demo-scheduler"]["secretsFolder"], "demo-scheduler")

        self.assertEqual(
            workloads["demo-web"]["csi"]["secretProviderClass"], "infisical-demo-web"
        )
        self.assertEqual(
            workloads["demo-queue"]["csi"]["secretProviderClass"], "infisical-demo-queue"
        )
        self.assertEqual(
            workloads["demo-scheduler"]["csi"]["secretProviderClass"],
            "infisical-demo-scheduler",
        )


if __name__ == "__main__":
    unittest.main()
