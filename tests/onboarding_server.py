# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hermetic helpers for executable onboarding documentation checks."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "target" / "debug" / "switchyard-server"


def _documented_server_toml(markdown: str) -> str:
    marker = "Create `routes.toml`"
    start = markdown.index(marker)
    match = re.search(r"```toml\n(.*?)\n```", markdown[start:], re.DOTALL)
    if match is None:
        raise AssertionError("Getting Started no longer contains the documented routes.toml")
    return match.group(1)


def assert_documented_config_dry_runs(markdown_path: Path, tmp_path: Path) -> None:
    """Run the guide's real TOML through the standalone server parser."""

    config = tmp_path / "documented-routes.toml"
    config.write_text(_documented_server_toml(markdown_path.read_text()))
    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = "onboarding-test-key"
    result = subprocess.run(
        [str(SERVER), "--config", str(config), "--dry-run"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=1) as response:  # noqa: S310 - loopback test server only
        return json.load(response)


@contextmanager
def _noop_server(tmp_path: Path) -> Iterator[str]:
    config = tmp_path / "noop-routes.toml"
    config.write_text(
        """schema_version = 1\ntargets = {}\n\n[routes.noop]\nid = \"switchyard\"\ntype = \"noop\"\n"""
    )
    port = _free_port()
    process = subprocess.Popen(
        [
            str(SERVER),
            "--config",
            str(config),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(f"switchyard-server exited early\n{stdout}\n{stderr}")
            try:
                with urlopen(f"{base_url}/health", timeout=0.2):  # noqa: S310
                    break
            except (URLError, TimeoutError):
                time.sleep(0.05)
        else:
            raise AssertionError("switchyard-server did not become healthy")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def assert_server_endpoints_work(tmp_path: Path) -> None:
    """Exercise the documented health, model-list, and completion endpoints."""

    with _noop_server(tmp_path) as base_url:
        with urlopen(f"{base_url}/health", timeout=1) as response:  # noqa: S310
            assert response.status == 200

        models = _get_json(f"{base_url}/v1/models")
        assert any(model.get("id") == "switchyard" for model in models["data"])

        request = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "switchyard",
                    "messages": [{"role": "user", "content": "hello"}],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=1) as response:  # noqa: S310
            payload = json.load(response)
        assert payload["choices"][0]["message"]["content"] == "OK"
