"""The ESP32 firmware's plain-C++ logic (esp32-node/include/ota.h, drift.h), built and run on this computer."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

NODE = Path(__file__).resolve().parents[1] / "esp32-node"


def _compiler() -> list[str] | None:
    cxx = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        return None
    cmd = [cxx, *shlex.split(os.environ.get("CXXFLAGS", ""))]
    if sys.platform == "darwin" and "-isysroot" not in cmd:
        # Use Xcode's SDK when there is one: a broken Command Line Tools SDK can't link (Oct 2026, macOS 27).
        try:
            dev = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            dev = ""
        sdk = Path(dev) / "Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
        if dev and sdk.exists():
            cmd += ["-isysroot", str(sdk)]
    return cmd


def test_ota_and_drift_logic(tmp_path: Path):
    cmd = _compiler()
    if cmd is None:
        pytest.skip("no C++ compiler")
    exe = tmp_path / "test_ota"
    build = subprocess.run([*cmd, "-std=c++17", "-Wall", "-Werror", "-I", str(NODE / "include"),
                            str(NODE / "test" / "test_ota.cpp"), "-o", str(exe)], capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
