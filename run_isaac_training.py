"""Launch Isaac-based training for Unitree A1.

This script provides a practical migration path from this repository's PyBullet
training pipeline to Isaac Lab training. It does not require changing the legacy
PyBullet environment and can be used immediately once Isaac Lab is installed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_TASK = "Isaac-Velocity-Flat-Unitree-A1-v0"


def _resolve_isaaclab_train_script(explicit_path: str | None) -> Path:
    """Resolve Isaac Lab's RSL-RL train.py script location."""
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
    else:
        env_path = os.environ.get("ISAACLAB_PATH")
        if not env_path:
            raise FileNotFoundError(
                "Isaac Lab path is not set. Pass --isaaclab-path or set ISAACLAB_PATH."
            )
        candidate = Path(env_path).expanduser().resolve()

    train_script = candidate / "scripts" / "reinforcement_learning" / "rsl_rl" / "train.py"
    if not train_script.exists():
        raise FileNotFoundError(
            f"Could not find Isaac Lab training entrypoint: {train_script}"
        )
    return train_script


def build_command(args: argparse.Namespace) -> list[str]:
    train_script = _resolve_isaaclab_train_script(args.isaaclab_path)
    cmd = [
        sys.executable,
        str(train_script),
        "--task",
        args.task,
        "--num_envs",
        str(args.num_envs),
    ]

    if args.headless:
        cmd += ["--headless"]

    if args.max_iterations is not None:
        cmd += ["--max_iterations", str(args.max_iterations)]

    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]

    if args.experiment_name:
        cmd += ["--experiment_name", args.experiment_name]

    if args.run_name:
        cmd += ["--run_name", args.run_name]

    if args.checkpoint:
        cmd += ["--checkpoint", args.checkpoint]

    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Unitree A1 in Isaac Lab.")
    parser.add_argument(
        "--isaaclab-path",
        type=str,
        default=None,
        help="Path to Isaac Lab repository root. Can also be provided by ISAACLAB_PATH.",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=DEFAULT_TASK,
        help="Isaac Lab task name. Default is Unitree A1 flat velocity task.",
    )
    parser.add_argument("--num-envs", type=int, default=2048, help="Parallel env count.")
    parser.add_argument("--max-iterations", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--experiment-name", type=str, default="cpg_rl1_isaac")
    parser.add_argument("--run-name", type=str, default="a1_velocity")
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without viewer. This is recommended on training servers.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        cmd = build_command(args)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        print(
            "[HINT] Install Isaac Lab and set ISAACLAB_PATH. Example:\n"
            "       export ISAACLAB_PATH=/path/to/IsaacLab"
        )
        return 1

    print("[INFO] Launching Isaac Lab training:")
    print(" ".join(cmd))

    process = subprocess.run(cmd)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
