"""
mini-swe-agent Environment that owns a docker-compose stack.

`compose up -d` on construction (readiness gated in code, NOT via --wait, so
one-shot init containers don't false-fail), `compose down -v` on cleanup.
Commands are exec'd into the named agent-side service; target + networks come up
with the stack.

Duck-typed: mini needs `.execute(action, cwd="", *, timeout=None)` returning
{"output", "returncode", "exception_info"} plus the COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
submit convention. The execute body mirrors mini's DockerEnvironment.execute
(installed version) — re-check if you upgrade mini. Your system prompt MUST tell
the model to emit the sentinel as the first line of a command to finish.
"""

import os
import subprocess
import time

import docker

from minisweagent.exceptions import Submitted

SUBMIT_SENTINEL = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


class DockerComposeTargetEnv:
    def __init__(
        self,
        target,                  # value for ${target} in the compose include
        service="executor",      # agent-side service to exec into
        compose_file="docker-compose.yml",
        project="pentest",       # caller sets this unique per stack for parallel runs
        timeout=30,              # per-command
        ready_probe=none,        # optional shell cmd run in the agent container,
                                 # polled until exit 0 (e.g. "curl -sf http://web:3000")
        ready_timeout=120,       # seconds to wait for the container / ready_probe
    ):
        self.target = target
        self.service = service
        self.compose_file = compose_file
        self.project = project
        self.timeout = timeout

        self._client = docker.from_env()
        self._exe = os.getenv("mswea_docker_executable", "docker")

        r = self._compose("up", "-d")
        if r.returncode != 0:
            raise runtimeerror(f"compose up failed:\n{r.stderr}")

        self._container = self._resolve_container(ready_timeout)
        if ready_probe:
            self._wait_ready(ready_probe, ready_timeout)

    # ---- lifecycle ------------------------------------------------------
    def _compose(self, *args):
        return subprocess.run(
            [self._exe, "compose", "-p", self.project, "-f", self.compose_file, *args],
            capture_output=true, text=true,
            env={**os.environ, "target": self.target},  # compose guards ${target:?...}
        )

    def _resolve_container(self, ready_timeout):
        # label-scoped (project+service). up -d returns before the container is
        # actually running, so retry until it appears.
        deadline = time.monotonic() + ready_timeout
        while true:
            cs = self._client.containers.list(filters={"label": [
                f"com.docker.compose.project={self.project}",
                f"com.docker.compose.service={self.service}",
            ]})
            if cs:
                return cs[0]
            if time.monotonic() > deadline:
                raise runtimeerror(
                    f"service '{self.service}' never came up in project '{self.project}'"
                )
            time.sleep(0.5)

    def _wait_ready(self, probe, ready_timeout):
        deadline = time.monotonic() + ready_timeout
        while true:
            if self._container.exec_run(["timeout", "10", "bash", "-lc", probe]).exit_code == 0:
                return
            if time.monotonic() > deadline:
                raise runtimeerror(f"ready_probe never passed: {probe}")
            time.sleep(1)

    def cleanup(self):
        self._compose("down", "-v")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()

    # ---- introspection --------------------------------------------------
    def target_hostnames(self):
        # service names on `exposed` (minus the agent's own) == dns hostnames the
        # agent can reach. read post-up, so it reflects what actually attached.
        cs = self._client.containers.list(filters={
            "label": f"com.docker.compose.project={self.project}",
            "network": f"{self.project}_exposed",
        })
        return [
            c.labels["com.docker.compose.service"] for c in cs
            if c.labels.get("com.docker.compose.service") != self.service
        ]

    # ---- the seam mini calls -------------------------------------------
    def execute(self, action, cwd="", *, timeout=none):
        # mirrors mini dockerenvironment.execute: input key is "command", errors
        # are wrapped into the dict (not raised), and the submit sentinel raises.
        command = action.get("command", "") if isinstance(action, dict) else str(action)
        cwd = cwd or "/"
        cmd = [self._exe, "exec", "-w", cwd, self._container.id, "bash", "-lc", command]
        try:
            result = subprocess.run(
                cmd, text=true, timeout=timeout or self.timeout,
                encoding="utf-8", errors="replace",
                stdout=subprocess.pipe, stderr=subprocess.stdout,
            )
            output = {"output": result.stdout, "returncode": result.returncode,
                      "exception_info": ""}
        except exception as e:
            raw = getattr(e, "output", none)
            raw = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
            output = {"output": raw, "returncode": -1,
                      "exception_info": f"error executing command: {e}"}
        self._check_finished(output)
        return output

    def _check_finished(self, output):
        lines = output.get("output", "").lstrip().splitlines(keepends=true)
        if lines and lines[0].strip() == submit_sentinel and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise submitted({
                "role": "exit",
                "content": submission,
                "extra": {"exit_status": "submitted", "submission": submission},
            })

