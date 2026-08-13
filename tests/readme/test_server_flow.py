# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executable coverage for the README standalone-server commands."""

import subprocess
from pathlib import Path

from tests.onboarding_server import (
    ROOT,
    assert_documented_config_dry_runs,
    assert_server_endpoints_work,
)

GUIDE = ROOT / "docs" / "getting_started.md"


def test_readme_server_flow(tmp_path: Path) -> None:
    subprocess.run(
        ["cargo", "build", "--locked", "-p", "switchyard-server"],
        cwd=ROOT,
        check=True,
    )
    # README explicitly delegates the complete routes.toml and request example
    # to Getting Started, so exercise that linked configuration here as well.
    assert_documented_config_dry_runs(GUIDE, tmp_path)
    assert_server_endpoints_work(tmp_path)
