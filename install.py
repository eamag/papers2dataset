#!/usr/bin/env python3
"""
Install papers2dataset skill for Claude Code, OpenAI Codex, and compatible agents.

Usage:
    curl -sSL https://raw.githubusercontent.com/eamag/papers2dataset/main/install.py | python3

Or locally:
    python3 install.py
    python3 install.py --target-dir ~/.my-agent/skills
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_URL = "https://github.com/eamag/papers2dataset.git"
SKILL_NAME = "papers2dataset"


def check_and_install_uv() -> str:
    """Check for uv, install if missing, return executable path."""
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    print("uv not found. Installing uv...")
    try:
        subprocess.run(
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            shell=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        print("Failed to install uv via script.")
        print("Please install manually: https://github.com/astral-sh/uv")
        sys.exit(1)

    # Check common install locations if not in PATH yet
    home = Path.home()
    candidates = [
        home / ".cargo" / "bin" / "uv",
        home / ".local" / "bin" / "uv",
    ]
    for cand in candidates:
        if cand.exists() and os.access(cand, os.X_OK):
            return str(cand)

    print("Installed uv but cannot find executable. Please ensure it is in your PATH.")
    return "uv"


def install_skill(source_path: Path, target_dir: Path, uv_cmd: str):
    """Install skill to target directory and setup venv."""
    print(f"\nInstalling to {target_dir}...")

    # Create parent if needed
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing
    if target_dir.exists():
        print(f"  Removing existing installation at {target_dir}")
        shutil.rmtree(target_dir)

    # Copy files
    shutil.copytree(source_path, target_dir)
    print("  Copied skill files.")

    # Make scripts executable
    scripts_dir = target_dir / "scripts"
    if scripts_dir.exists():
        for script in scripts_dir.iterdir():
            if script.is_file() and script.suffix == ".py":
                script.chmod(script.stat().st_mode | 0o111)

    # Setup venv
    print(f"  Setting up environment with {uv_cmd}...")
    try:
        subprocess.run(
            [uv_cmd, "venv"], cwd=target_dir, check=True, capture_output=True
        )
        subprocess.run(
            [uv_cmd, "pip", "install", "httpx"],
            cwd=target_dir,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  Warning: Error setting up environment: {e}")


def main():
    parser = argparse.ArgumentParser(description=f"Install {SKILL_NAME} agent skill")
    parser.add_argument(
        "--target-dir",
        "-t",
        action="append",
        help="Specific target directory to install to",
    )
    args = parser.parse_args()

    print(f"{SKILL_NAME} skill installer")
    print("=" * 40)

    # 1. Check/Install uv
    uv_cmd = check_and_install_uv()

    # Determine targets
    targets = []
    if args.target_dir:
        for t in args.target_dir:
            targets.append(Path(t).expanduser() / SKILL_NAME)
    else:
        # Auto-detect default locations
        home = Path.home()

        # Claude Code
        targets.append(home / ".claude" / "skills" / SKILL_NAME)

        # OpenAI Codex (only if ~/.codex exists)
        if (home / ".codex").exists():
            targets.append(home / ".codex" / "skills" / SKILL_NAME)

        # VS Code / GitHub Copilot (often uses .github/skills repo-local or .claude/skills global)
        # We start with the 2 global ones.

    # Deduplicate
    targets = list(dict.fromkeys(targets))

    # Get source files
    with tempfile.TemporaryDirectory() as tmp_dir:
        source_path = None

        local_skill = Path(__file__).parent / "skill"
        if local_skill.exists() and local_skill.is_dir():
            print(f"Source: Local directory {local_skill}")
            source_path = local_skill
            # We can use it directly, but subsequent copytree might fail if we modify it?
            # No, copytree is fine.
        else:
            print(f"Source: Cloning from {REPO_URL}...")
            clone_path = Path(tmp_dir) / "repo"
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", REPO_URL, str(clone_path)],
                    check=True,
                    capture_output=True,
                )
                source_path = clone_path / "skill"
            except subprocess.CalledProcessError as e:
                print(f"Error cloning repository: {e.stderr.decode()}")
                sys.exit(1)
            except FileNotFoundError:
                print("Error: git is required.")
                sys.exit(1)

        if not source_path or not source_path.exists():
            print("Error: Could not find skill files.")
            sys.exit(1)

        # Install to all targets
        for target in targets:
            install_skill(source_path, target, uv_cmd)

    print()
    print("=" * 40)
    print("✅ Installation complete!")
    print("Installed to:")
    for t in targets:
        print(f"  - {t}")

    print("\nThe skill is ready to use with your agents.")
    print("Optional: Set OPENALEX_EMAIL for 10x faster API access.")


if __name__ == "__main__":
    main()
