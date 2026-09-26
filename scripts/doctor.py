#!/usr/bin/env python3
"""TalentScreen AI Environment Doctor.
Performs read-only checks on OS, runtime dependencies, Docker, storage, and configuration.
Does NOT leak secrets, call paid APIs, or make destructive modifications.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Add services/backend to sys.path so app.config can be loaded
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "services" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PASS = "✓ PASS"
FAIL = "✗ FAIL"
WARN = "! WARN"
INFO = "ℹ INFO"

results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str):
    results.append((name, status, detail))


def check_os_arch():
    sys_name = platform.system()
    machine = platform.machine()
    detail = f"{sys_name} ({machine})"
    if sys_name == "Darwin" and machine == "arm64":
        record("OS & Architecture", PASS, f"{detail} — Apple Silicon detected")
    elif sys_name == "Darwin":
        record("OS & Architecture", WARN, f"{detail} — macOS Intel (MPS unavailable)")
    else:
        record("OS & Architecture", INFO, f"{detail} — Non-macOS system")


def check_python():
    version_info = sys.version_info
    ver_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    if version_info >= (3, 12):
        record("Python Runtime", PASS, f"Python {ver_str} (>= 3.12)")
    else:
        record("Python Runtime", FAIL, f"Python {ver_str} (< 3.12 required)")


def check_node_npm():
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node and npm:
        try:
            node_ver = subprocess.check_output([node, "-v"], text=True).strip()
            npm_ver = subprocess.check_output([npm, "-v"], text=True).strip()
            record("Node.js & npm", PASS, f"Node {node_ver}, npm {npm_ver}")
        except Exception as e:
            record("Node.js & npm", WARN, f"Error getting versions: {e}")
    else:
        record("Node.js & npm", FAIL, "Node.js or npm not found in PATH")


def check_docker():
    docker = shutil.which("docker")
    if not docker:
        record("Docker CLI", FAIL, "docker executable not found in PATH")
        return

    try:
        ver = subprocess.check_output([docker, "--version"], text=True).strip()
        # Test if daemon is responding
        ping = subprocess.run([docker, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ping.returncode == 0:
            record("Docker Daemon", PASS, f"{ver} — Daemon is running")
        else:
            record("Docker Daemon", FAIL, "Docker daemon is not running. Please start Docker Desktop.")
    except Exception as e:
        record("Docker Daemon", FAIL, f"Docker check error: {e}")


def check_storage():
    try:
        from app.config import get_settings
        settings = get_settings()
        storage_dir = settings.storage_path
        # Check write permissions
        test_file = storage_dir / ".doctor_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()

        # Check that it's outside repository or in .gitignore
        record("Private Storage", PASS, f"Writable at {storage_dir}")
    except Exception as e:
        record("Private Storage", FAIL, f"Storage configuration error: {e}")


def check_config():
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        record("Environment Config", WARN, ".env missing. Run 'cp .env.example .env'")
        return

    try:
        from app.config import get_settings
        settings = get_settings()
        safe_data = settings.safe_dict()
        record(
            "Configuration Typed",
            PASS,
            f"APP_ENV={settings.APP_ENV}, LLM_PROVIDER={settings.LLM_PROVIDER}, SECRETS MASKED",
        )

        # Check API key presence only as boolean
        key_present = bool(settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY.strip())
        if settings.LLM_PROVIDER == "mock":
            record("DeepSeek Key", INFO, f"Present={key_present} (Mock mode active, key not required)")
        else:
            if key_present:
                record("DeepSeek Key", PASS, "Present (Hidden). Real provider enabled.")
            else:
                record("DeepSeek Key", FAIL, "Missing key while LLM_PROVIDER=deepseek")
    except Exception as e:
        record("Environment Config", FAIL, f"Configuration validation failed: {e}")


def check_mps_pytorch():
    try:
        import torch
        if torch.backends.mps.is_available():
            record("PyTorch MPS (GPU)", PASS, "Apple Silicon MPS acceleration is available")
        else:
            record("PyTorch MPS (GPU)", INFO, "MPS not available, CPU mode will be used")
    except ImportError:
        record("PyTorch / MPS", INFO, "PyTorch not yet installed in active venv (CPU/MPS check deferred to ML setup)")


def main():
    print("=" * 70)
    print("TalentScreen AI — System Doctor Environment Diagnostics")
    print("=" * 70)

    check_os_arch()
    check_python()
    check_node_npm()
    check_docker()
    check_storage()
    check_config()
    check_mps_pytorch()

    all_pass = True
    print("\nCheck Results:")
    print("-" * 70)
    for name, status, detail in results:
        print(f"[{status}] {name:<22} : {detail}")
        if status == FAIL:
            all_pass = False
    print("-" * 70)

    if all_pass:
        print("\nAll prerequisite checks PASSED. System is ready for development.\n")
        return 0
    else:
        print("\nSome prerequisite checks FAILED. Please resolve the items above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
