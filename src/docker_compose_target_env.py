"""
mini-swe-agent Environment that owns a docker-compose stack.

docker compose up / down on init / cleanup

coupled to docker compose config layout via args:
    'target' (target subfolder name)
    'agent' name of agent service in docker/compose.yaml
"""

import os
import subprocess
import time
import uuid
from pathlib import Path

import docker

from minisweagent.exceptions import Submitted

SUBMIT_SENTINEL = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
COMPOSE_FILE = Path(__file__).resolve().parent.parent / "docker" / "compose.yaml"

class DockerComposeTargetEnv:
    def __init__(
        self,
        target="juiceshop",             # value for ${TARGET} in the compose include
        agent="threat-modeler",       # value for ${AGENT} in the compose include
        timeout=30,                     # per-command
        ready_probe=None,               # optional shell cmd run in the agent container,
                                        # polled until exit 0 (e.g. "curl -sf http://web:3000")
                                        # ideally keep this at None and rely on docker healthchecks
                                        # to block the --wait flag on construction istead
        ready_timeout=120,              # seconds to wait for the container / ready_probe
    ):
        self.target = target
        self.agent = agent
        self.timeout = timeout
        self.project = f"{target}-{agent}-{uuid.uuid4().hex[:8]}"

        self._client = docker.from_env()
        self._exe = os.getenv("MSWEA_DOCKER_EXECUTABLE", "docker")
        
        r = self._compose("up", "-d", "--wait")
        if r.returncode != 0:
            raise RuntimeError(f"compose up failed:\n{r.stderr}")

        self._container = self._resolve_container()
        if ready_probe:
            self._wait_ready(ready_probe, ready_timeout)

    def _compose(self, *args):
        return subprocess.run(
            [self._exe, "compose", "-p", self.project, "-f", COMPOSE_FILE, *args],
            capture_output=True, text=True,
            env={**os.environ, "TARGET": self.target, "AGENT": self.agent},
        )

    def _resolve_container(self):
        cs = self._client.containers.list(filters={"label": [
            f"com.docker.compose.project={self.project}",
            "com.docker.compose.service=agent",
        ]})
        if not cs:
            raise RuntimeError(f"agent container not found in project '{self.project}' after --wait")
        return cs[0]

    def _wait_ready(self, probe, ready_timeout):
        deadline = time.monotonic() + ready_timeout
        while True:
            if self._container.exec_run(["timeout", "10", "bash", "-lc", probe]).exit_code == 0:
                return
            if time.monotonic() > deadline:
                raise RuntimeError(f"ready_probe never passed: {probe}")
            time.sleep(1)

    def cleanup(self):
        self._compose("down", "-v")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    def get_template_vars(self) -> dict:
        return {
            "target": self.target,
            "agent": self.agent,
            "project": self.project,
            "cwd": "/",
        }

    def serialize(self) -> dict:
        return {"info": {"config": {
            "environment_type": f"{type(self).__module__}.{type(self).__name__}",
            "target": self.target,
            "agent": self.agent,
            "project": self.project,
        }}}

    def target_hostnames(self):
        # service names on `exposed` (minus the agent's own) == dns hostnames the
        # agent can reach. read post-up, so it reflects what actually attached.
        cs = self._client.containers.list(filters={
            "label": f"com.docker.compose.project={self.project}",
            "network": f"{self.project}_exposed",
        })
        return [
            c.labels["com.docker.compose.service"] for c in cs
            if c.labels.get("com.docker.compose.service") != "agent"
        ]

    def execute(self, action, cwd="", *, timeout=None):
        command = action.get("command", "") if isinstance(action, dict) else str(action)
        cwd = cwd or "/"
        cmd = [self._exe, "exec", "-w", cwd, self._container.id, "bash", "-lc", command]
        try:
            result = subprocess.run(
                cmd, text=True, timeout=timeout or self.timeout,
                encoding="utf-8", errors="replace",
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            output = {"output": result.stdout, "returncode": result.returncode,
                      "exception_info": ""}
        except Exception as e:
            raw = getattr(e, "output", None)
            raw = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
            output = {"output": raw, "returncode": -1,
                      "exception_info": f"error executing command: {e}"}
        self._check_finished(output)
        return output

    def _check_finished(self, output):
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == SUBMIT_SENTINEL and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted({
                "role": "exit",
                "content": submission,
                "extra": {"exit_status": "submitted", "submission": submission},
            })
