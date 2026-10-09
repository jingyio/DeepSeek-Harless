"""Single portability boundary for the pinned DSH Python SDK and Node runtime."""
from pathlib import Path
import os
import shutil


def launch_args(root: Path, patches: tuple[str, ...]) -> tuple[str, ...]:
    cli = root / "node_modules/@deepseek-ai/dsh/lib/bin.js"
    if not cli.is_file():
        raise FileNotFoundError("Install the pinned runtime with npm ci first")
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("Node.js is required")
    return (node, str(cli), "--profile", "sdk",
            *(argument for patch in patches for argument in ("--patch", str(Path(patch).resolve()))))


def create_harness(*, root: Path, patches: tuple[str, ...], env=None, **kwargs):
    from deepseek_harness import DeepSeekHarness
    # SDK 0.1.5rc1's private launch seam is intentionally confined here. Launching
    # Node directly avoids Unix .bin scripts and Windows .cmd executable handling.
    child_env = {"DSH_HOME": str(root / ".local/dsh"),
                 "SSS_PURE_CODE_PYTHON": os.sys.executable, **(env or {})}
    return DeepSeekHarness(_launch_args=launch_args(root, patches),
                          env=child_env, reasoning_effort="off", **kwargs)
