#!/usr/bin/env python3
"""
AuraGen -- Project Setup & Verification Script.

Checks all prerequisites, verifies folder structure, and guides
the user through downloading models and installing dependencies.

Usage:
    python setup.py          # Full check + interactive setup
    python setup.py --check  # Verify-only mode (no changes)
    python setup.py --verbose # Show additional details
"""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ensure stdout can handle UTF-8 (critical on Windows cp1252 consoles).
# If reconfiguration fails, we fall back to ASCII-safe output characters.
# ---------------------------------------------------------------------------

_UTF8_SAFE: bool = False
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    _UTF8_SAFE = True
except Exception:
    # Python < 3.7 or non-reconfigurable stream -- stay with default encoding
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True,
        )
        _UTF8_SAFE = True
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR: Path = Path(__file__).resolve().parent
BACKEND_DIR: Path = ROOT_DIR / "backend"
FRONTEND_DIR: Path = ROOT_DIR / "frontend"
MODELS_DIR: Path = BACKEND_DIR / "models"
STYLES_DIR: Path = FRONTEND_DIR / "src" / "styles"

REQUIRED_PYTHON_MAJOR: int = 3
REQUIRED_PYTHON_MINOR: int = 10
REQUIRED_NODE_MAJOR: int = 18
REQUIRED_VRAM_GB: float = 4.0

# Model directories to verify
MODEL_DIRS: Dict[str, Dict[str, str]] = {
    "flux": {
        "path": "flux",
        "display_name": "FLUX Klein",
        "setup_flag": "flux",
    },
    "wan": {
        "path": "wan",
        "display_name": "Wan 2.1",
        "setup_flag": "wan",
    },
    "controlnet": {
        "path": "controlnet",
        "display_name": "ControlNet",
        "setup_flag": "controlnet",
    },
    "sam2": {
        "path": "sam2",
        "display_name": "SAM2",
        "setup_flag": "sam2",
    },
}

# Key Python packages that should be importable
KEY_PYTHON_PACKAGES: List[str] = ["fastapi", "torch", "diffusers"]

# Expected SCSS style files
EXPECTED_STYLE_FILES: List[str] = [
    "_tokens.scss",
    "_components.scss",
    "Grid.scss",
    "App.scss",
    "_index.scss",
]

# ---------------------------------------------------------------------------
# ANSI colour helpers (with graceful fallback)
# ---------------------------------------------------------------------------

_NO_COLOR: bool = (
    os.environ.get("NO_COLOR", "") != ""
    or os.environ.get("TERM", "") in ("dumb", "")
    # On Windows, enable ANSI if the terminal supports it
)


def _supports_ansi() -> bool:
    """Return True if the current terminal likely supports ANSI escape codes."""
    if _NO_COLOR:
        return False
    # On Windows 10+ with virtual terminal processing enabled
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # Enable virtual terminal processing on stdout
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
        except Exception:
            return False
    # Unix systems generally support ANSI
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_USE_COLOR: bool = _supports_ansi()


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m" if _USE_COLOR else text


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m" if _USE_COLOR else text


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m" if _USE_COLOR else text


def _cyan(text: str) -> str:
    return f"\033[96m{text}\033[0m" if _USE_COLOR else text


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _USE_COLOR else text


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if _USE_COLOR else text


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

class CheckResult:
    """Stores the outcome of a single verification check."""

    __slots__ = ("name", "passed", "detail", "fix_command", "category", "warning")

    def __init__(
        self,
        name: str,
        passed: bool,
        detail: str = "",
        fix_command: str = "",
        category: str = "",
        warning: bool = False,
    ) -> None:
        self.name = name
        self.passed = passed
        self.detail = detail
        self.fix_command = fix_command
        self.category = category
        self.warning = warning  # warnings count as pass but still print

    @property
    def status_label(self) -> str:
        if self.passed and not self.warning:
            return _green("PASS")
        elif self.warning:
            return _yellow("WARN")
        else:
            return _red("FAIL")

    @property
    def raw_status(self) -> str:
        if self.passed and not self.warning:
            return "PASS"
        elif self.warning:
            return "WARN"
        else:
            return "FAIL"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _run_cmd(cmd: List[str], timeout: int = 15) -> Tuple[bool, str]:
    """Run an external command and return (success, stdout_text).

    Captures both stdout and stderr. Returns (False, "") on any error.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, output
    except FileNotFoundError:
        return False, ""
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception:
        return False, ""


def _parse_version(version_string: str) -> Optional[Tuple[int, ...]]:
    """Extract a numeric version tuple from a string like 'v20.10.0' or 'Python 3.11.5'."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version_string)
    if match:
        parts = [int(match.group(1)), int(match.group(2))]
        if match.group(3) is not None:
            parts.append(int(match.group(3)))
        return tuple(parts)
    return None


def _dir_has_content(path: Path) -> bool:
    """Return True if the directory exists and contains at least one file (recursively)."""
    if not path.is_dir():
        return False
    try:
        for item in path.rglob("*"):
            if item.is_file():
                # Ignore common metadata files that don't count as "real" content
                if item.name in (".gitkeep", "__init__.py", "TODO.md"):
                    continue
                return True
    except PermissionError:
        pass
    return False


def _count_files(path: Path) -> int:
    """Count the number of files in a directory (recursively)."""
    if not path.is_dir():
        return 0
    count = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                count += 1
    except PermissionError:
        pass
    return count


# ---------------------------------------------------------------------------
# System checks
# ---------------------------------------------------------------------------


def check_python_version() -> CheckResult:
    """Verify Python >= 3.10."""
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    passed = (ver.major, ver.minor) >= (REQUIRED_PYTHON_MAJOR, REQUIRED_PYTHON_MINOR)
    detail = f"({ver_str})" if passed else f"({ver_str} -- need {REQUIRED_PYTHON_MAJOR}.{REQUIRED_PYTHON_MINOR}+)"
    return CheckResult(
        name="Python",
        passed=passed,
        detail=detail,
        fix_command="" if passed else "Install Python 3.10+ from https://python.org",
        category="SYSTEM PREREQUISITES",
    )


def check_node_version() -> CheckResult:
    """Verify Node.js >= 18."""
    ok, output = _run_cmd(["node", "--version"])
    if not ok:
        return CheckResult(
            name="Node.js",
            passed=False,
            detail="(not found)",
            fix_command="Install Node.js 18+ from https://nodejs.org",
            category="SYSTEM PREREQUISITES",
        )
    ver = _parse_version(output)
    if ver is None:
        return CheckResult(
            name="Node.js",
            passed=False,
            detail=f"(unparseable: {output})",
            fix_command="Install Node.js 18+ from https://nodejs.org",
            category="SYSTEM PREREQUISITES",
        )
    ver_str = output.lstrip("v")
    passed = ver[0] >= REQUIRED_NODE_MAJOR
    detail = f"({ver_str})" if passed else f"({ver_str} -- need {REQUIRED_NODE_MAJOR}+)"
    return CheckResult(
        name="Node.js",
        passed=passed,
        detail=detail,
        fix_command="" if passed else "Install Node.js 18+ from https://nodejs.org",
        category="SYSTEM PREREQUISITES",
    )


def check_npm() -> CheckResult:
    """Check if npm is available."""
    ok, output = _run_cmd(["npm", "--version"])
    if not ok:
        return CheckResult(
            name="npm",
            passed=False,
            detail="(not found)",
            fix_command="Install Node.js (includes npm) from https://nodejs.org",
            category="SYSTEM PREREQUISITES",
        )
    return CheckResult(
        name="npm",
        passed=True,
        detail=f"({output})",
        category="SYSTEM PREREQUISITES",
    )


def check_cuda() -> CheckResult:
    """Check if CUDA is available via PyTorch."""
    try:
        import torch  # noqa: F811
    except ImportError:
        return CheckResult(
            name="CUDA",
            passed=False,
            detail="(torch not installed)",
            fix_command=f"cd backend && pip install -r requirements.txt",
            category="SYSTEM PREREQUISITES",
            warning=True,
        )
    if torch.cuda.is_available():
        cuda_version = torch.version.cuda or "unknown"
        return CheckResult(
            name="CUDA",
            passed=True,
            detail=f"({cuda_version})",
            category="SYSTEM PREREQUISITES",
        )
    else:
        return CheckResult(
            name="CUDA",
            passed=True,
            detail="(not available -- CPU-only mode)",
            category="SYSTEM PREREQUISITES",
            warning=True,
        )


def check_gpu_vram() -> CheckResult:
    """Check GPU VRAM (if torch + CUDA available)."""
    try:
        import torch
    except ImportError:
        return CheckResult(
            name="GPU VRAM",
            passed=True,
            detail="(torch not installed -- skipped)",
            category="SYSTEM PREREQUISITES",
            warning=True,
        )
    if not torch.cuda.is_available():
        return CheckResult(
            name="GPU VRAM",
            passed=True,
            detail="(no GPU -- CPU-only mode)",
            category="SYSTEM PREREQUISITES",
            warning=True,
        )
    try:
        props = torch.cuda.get_device_properties(0)
        total_gb = props.total_mem / (1024 ** 3)
        gpu_name = props.name
        passed = total_gb >= REQUIRED_VRAM_GB
        detail = f"({total_gb:.1f} GB - {gpu_name})"
        fix = "" if passed else f"WARNING: Only {total_gb:.1f} GB VRAM. 4 GB+ recommended. Generation will be slower."
        return CheckResult(
            name="GPU VRAM",
            passed=passed,
            detail=detail,
            fix_command=fix,
            category="SYSTEM PREREQUISITES",
            warning=not passed,
        )
    except Exception as exc:
        return CheckResult(
            name="GPU VRAM",
            passed=True,
            detail=f"(could not query: {exc})",
            category="SYSTEM PREREQUISITES",
            warning=True,
        )


# ---------------------------------------------------------------------------
# Backend dependency checks
# ---------------------------------------------------------------------------


def check_requirements_txt() -> CheckResult:
    """Check if backend/requirements.txt exists."""
    path = BACKEND_DIR / "requirements.txt"
    if path.is_file():
        return CheckResult(
            name="requirements.txt",
            passed=True,
            category="BACKEND DEPENDENCIES",
        )
    return CheckResult(
        name="requirements.txt",
        passed=False,
        detail="(not found)",
        fix_command="Ensure backend/requirements.txt exists in the project",
        category="BACKEND DEPENDENCIES",
    )


def check_python_package(package_name: str) -> CheckResult:
    """Check if a Python package is importable."""
    try:
        __import__(package_name)
        return CheckResult(
            name=package_name,
            passed=True,
            category="BACKEND DEPENDENCIES",
        )
    except ImportError:
        return CheckResult(
            name=package_name,
            passed=False,
            detail="(not installed)",
            fix_command=f"cd backend && pip install -r requirements.txt",
            category="BACKEND DEPENDENCIES",
        )


# ---------------------------------------------------------------------------
# Model weight checks
# ---------------------------------------------------------------------------


def check_model_dir(key: str) -> CheckResult:
    """Check if a model directory has content."""
    meta = MODEL_DIRS[key]
    model_path = MODELS_DIR / meta["path"]
    display = meta["display_name"]
    rel_path = f"models/{meta['path']}/"

    if not model_path.exists():
        return CheckResult(
            name=display,
            passed=False,
            detail=f"({rel_path} missing)",
            fix_command=f"cd backend && python setup_models.py --model {meta['setup_flag']}",
            category="MODEL WEIGHTS",
        )
    if not _dir_has_content(model_path):
        return CheckResult(
            name=display,
            passed=False,
            detail=f"({rel_path} empty)",
            fix_command=f"cd backend && python setup_models.py --model {meta['setup_flag']}",
            category="MODEL WEIGHTS",
        )

    file_count = _count_files(model_path)
    return CheckResult(
        name=display,
        passed=True,
        detail=f"({file_count} files)",
        category="MODEL WEIGHTS",
    )


# ---------------------------------------------------------------------------
# Frontend checks
# ---------------------------------------------------------------------------


def check_package_json() -> CheckResult:
    """Check if frontend/package.json exists."""
    path = FRONTEND_DIR / "package.json"
    if path.is_file():
        return CheckResult(
            name="package.json",
            passed=True,
            category="FRONTEND",
        )
    return CheckResult(
        name="package.json",
        passed=False,
        detail="(not found)",
        fix_command="Ensure frontend/package.json exists in the project",
        category="FRONTEND",
    )


def check_sass_dependency() -> CheckResult:
    """Check if sass is listed in devDependencies of package.json."""
    path = FRONTEND_DIR / "package.json"
    if not path.is_file():
        return CheckResult(
            name="sass dependency",
            passed=False,
            detail="(package.json not found)",
            fix_command="cd frontend && npm install --save-dev sass",
            category="FRONTEND",
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        dev_deps = pkg.get("devDependencies", {})
        if "sass" in dev_deps:
            return CheckResult(
                name="sass dependency",
                passed=True,
                detail=f"({dev_deps['sass']})",
                category="FRONTEND",
            )
        else:
            return CheckResult(
                name="sass dependency",
                passed=False,
                detail="(not in devDependencies)",
                fix_command="cd frontend && npm install --save-dev sass",
                category="FRONTEND",
            )
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(
            name="sass dependency",
            passed=False,
            detail=f"(error reading package.json: {exc})",
            fix_command="cd frontend && npm install --save-dev sass",
            category="FRONTEND",
        )


def check_node_modules() -> CheckResult:
    """Check if frontend/node_modules/ exists and has content."""
    nm_path = FRONTEND_DIR / "node_modules"
    if nm_path.is_dir() and any(nm_path.iterdir()):
        return CheckResult(
            name="node_modules",
            passed=True,
            category="FRONTEND",
        )
    return CheckResult(
        name="node_modules",
        passed=False,
        detail="(not installed)",
        fix_command="cd frontend && npm install",
        category="FRONTEND",
    )


def check_scss_token_system() -> CheckResult:
    """Check if the SCSS token system directory has files."""
    if not STYLES_DIR.is_dir():
        return CheckResult(
            name="SCSS Token System",
            passed=False,
            detail="(styles/ directory not found)",
            fix_command="Ensure frontend/src/styles/ exists with SCSS files",
            category="FRONTEND",
        )
    scss_files = [f for f in STYLES_DIR.iterdir() if f.suffix == ".scss"]
    if len(scss_files) == 0:
        return CheckResult(
            name="SCSS Token System",
            passed=False,
            detail="(no .scss files found)",
            fix_command="Add SCSS token files to frontend/src/styles/",
            category="FRONTEND",
        )
    return CheckResult(
        name="SCSS Token System",
        passed=True,
        detail=f"({len(scss_files)} files found)",
        category="FRONTEND",
    )


def check_style_file(filename: str) -> CheckResult:
    """Check if a specific style file exists."""
    path = STYLES_DIR / filename
    if path.is_file():
        return CheckResult(
            name=filename,
            passed=True,
            category="STYLE SYSTEM FILES",
        )
    return CheckResult(
        name=filename,
        passed=False,
        detail="(missing)",
        fix_command=f"Create frontend/src/styles/{filename}",
        category="STYLE SYSTEM FILES",
    )


def check_outputs_dir() -> CheckResult:
    """Check if backend/outputs/ exists (auto-create if needed)."""
    outputs_path = BACKEND_DIR / "outputs"
    if outputs_path.is_dir():
        return CheckResult(
            name="outputs directory",
            passed=True,
            category="BACKEND DEPENDENCIES",
        )
    return CheckResult(
        name="outputs directory",
        passed=False,
        detail="(missing -- will auto-create)",
        fix_command="auto",  # Special marker: we will auto-create it
        category="BACKEND DEPENDENCIES",
    )


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------


def run_all_checks() -> List[CheckResult]:
    """Execute every check and return the list of results."""
    results: List[CheckResult] = []

    # -- System Prerequisites --
    results.append(check_python_version())
    results.append(check_node_version())
    results.append(check_npm())
    results.append(check_cuda())
    results.append(check_gpu_vram())

    # -- Backend Dependencies --
    results.append(check_requirements_txt())
    for pkg in KEY_PYTHON_PACKAGES:
        results.append(check_python_package(pkg))
    results.append(check_outputs_dir())

    # -- Model Weights --
    for key in MODEL_DIRS:
        results.append(check_model_dir(key))

    # -- Frontend --
    results.append(check_package_json())
    results.append(check_sass_dependency())
    results.append(check_node_modules())
    results.append(check_scss_token_system())

    # -- Style System Files --
    for filename in EXPECTED_STYLE_FILES:
        results.append(check_style_file(filename))

    return results


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

# Column widths for alignment
_COL_NAME: int = 22
_COL_REQ: int = 16
_COL_STATUS: int = 8
_LINE_WIDTH: int = 64


def _print_header() -> None:
    """Print the report header banner."""
    print()
    print("=" * _LINE_WIDTH)
    print(f"{'AURAGEN SETUP VERIFICATION':^{_LINE_WIDTH}}")
    print("=" * _LINE_WIDTH)


def _separator_char() -> str:
    """Return a horizontal-rule character safe for the current console."""
    return "\u2500" if _UTF8_SAFE else "-"


def _print_section(title: str) -> None:
    """Print a section heading."""
    print()
    print(f"  {_bold(title)}")
    print(f"  {_separator_char() * (_LINE_WIDTH - 4)}")


def _requirement_for(name: str) -> str:
    """Return a short description of the requirement for alignment."""
    reqs: Dict[str, str] = {
        "Python": "3.10+",
        "Node.js": "18+",
        "npm": "available",
        "CUDA": "available",
        "GPU VRAM": "4GB+",
    }
    return reqs.get(name, "")


def _print_result(result: CheckResult, verbose: bool = False) -> None:
    """Print a single check result line."""
    req = _requirement_for(result.name)
    name_col = f"  {result.name:<{_COL_NAME}}"
    req_col = f"{req:<{_COL_REQ}}" if req else f"{'':>{_COL_REQ}}"

    # Use raw_status for alignment, then colorise -- ANSI escapes break
    # Python's padding because they add invisible bytes.
    raw = result.raw_status
    status_col = f"{raw:<{_COL_STATUS}}"

    # Colorise the status token in-place
    if raw == "PASS":
        status_col = status_col.replace(raw, _green(raw), 1)
    elif raw == "WARN":
        status_col = status_col.replace(raw, _yellow(raw), 1)
    else:
        status_col = status_col.replace(raw, _red(raw), 1)

    detail_col = f"  {result.detail}" if result.detail else ""

    # Build the fix hint for failures
    fix_hint = ""
    advisory_prefixes = ("http", "Install", "Ensure", "Add", "Create", "WARNING")
    if not result.passed and not result.warning and result.fix_command:
        if result.fix_command.startswith(advisory_prefixes):
            fix_hint = f"  {_dim(result.fix_command)}"
        else:
            fix_hint = f"  Run: {_cyan(result.fix_command)}"
    elif result.warning and result.fix_command:
        fix_hint = f"  {_dim(result.fix_command)}"

    line = f"{name_col}{req_col}{status_col}{detail_col}"
    if fix_hint:
        line += f"\n{'':>{_COL_NAME + 2}}{' ' * _COL_REQ}{fix_hint}"
    print(line)


def _print_footer(results: List[CheckResult]) -> None:
    """Print the summary footer."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    warnings = sum(1 for r in results if r.warning)

    print()
    print("=" * _LINE_WIDTH)

    if failed == 0 and warnings == 0:
        msg = f"RESULT: All {total} checks passed."
        print(f"  {_green(msg)}")
    elif failed == 0:
        msg = f"RESULT: {passed}/{total} checks passed. {warnings} warning(s)."
        print(f"  {_yellow(msg)}")
    else:
        actions = sum(1 for r in results if not r.passed and not r.warning)
        msg = f"RESULT: {passed}/{total} checks passed. {actions} action(s) needed."
        print(f"  {_red(msg)}")

    print("=" * _LINE_WIDTH)
    print()


def print_report(results: List[CheckResult], verbose: bool = False) -> None:
    """Print the full verification report."""
    _print_header()

    # Group results by category (preserving insertion order)
    categories: Dict[str, List[CheckResult]] = {}
    for r in results:
        cat = r.category or "OTHER"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    for cat_name, cat_results in categories.items():
        _print_section(cat_name)
        for r in cat_results:
            _print_result(r, verbose=verbose)

    _print_footer(results)


# ---------------------------------------------------------------------------
# Interactive fix runner
# ---------------------------------------------------------------------------


def _collect_fix_actions(results: List[CheckResult]) -> List[Tuple[str, str]]:
    """Return a list of (description, command) pairs for failed checks that have runnable fix commands.

    Only includes checks that are actual failures (not warnings) and have
    shell commands (not advisory messages like URLs or instructions).
    """
    actions: List[Tuple[str, str]] = []
    seen_commands: set = set()

    for r in results:
        if r.passed or r.warning:
            continue
        cmd = r.fix_command
        if not cmd:
            continue
        # Skip advisory-only messages
        if cmd.startswith(("http", "Install", "Ensure", "Add", "Create", "WARNING")):
            continue
        # Handle the special auto-create marker for outputs dir
        if cmd == "auto":
            continue
        if cmd in seen_commands:
            continue
        seen_commands.add(cmd)
        actions.append((r.name, cmd))

    return actions


def _auto_create_outputs(results: List[CheckResult]) -> None:
    """Auto-create the outputs directory if its check failed."""
    for r in results:
        if r.name == "outputs directory" and not r.passed and r.fix_command == "auto":
            outputs_path = BACKEND_DIR / "outputs"
            try:
                outputs_path.mkdir(parents=True, exist_ok=True)
                r.passed = True
                r.detail = "(auto-created)"
                r.fix_command = ""
                print(f"  [+] Created {outputs_path}")
            except OSError as exc:
                print(f"  [!] Failed to create outputs directory: {exc}")


def run_fix_actions(actions: List[Tuple[str, str]]) -> None:
    """Interactively run fix commands."""
    if not actions:
        print("  No automatic fixes available.")
        return

    print()
    print(f"  The following {len(actions)} command(s) will be executed:")
    print()
    for i, (desc, cmd) in enumerate(actions, 1):
        print(f"    {i}. [{desc}] {_cyan(cmd)}")
    print()

    try:
        answer = input("  Proceed? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        print("  Aborted.")
        return

    if answer not in ("y", "yes"):
        print("  Skipped.")
        return

    print()
    for desc, cmd in actions:
        print(f"  >>> Running: {cmd}")
        print(f"  {_separator_char() * (_LINE_WIDTH - 4)}")

        # Determine working directory from the command
        # Commands like "cd backend && ..." need to change directory
        cwd = str(ROOT_DIR)
        actual_cmd = cmd
        if cmd.startswith("cd backend && "):
            cwd = str(BACKEND_DIR)
            actual_cmd = cmd[len("cd backend && "):]
        elif cmd.startswith("cd frontend && "):
            cwd = str(FRONTEND_DIR)
            actual_cmd = cmd[len("cd frontend && "):]

        try:
            # Use shell=True to handle complex commands
            proc = subprocess.run(
                actual_cmd,
                shell=True,
                cwd=cwd,
                timeout=600,  # 10 minute timeout for npm install / pip install
            )
            if proc.returncode == 0:
                print(f"  {_green('[OK]')} {desc}")
            else:
                print(f"  {_red('[FAILED]')} {desc} (exit code {proc.returncode})")
        except subprocess.TimeoutExpired:
            print(f"  {_red('[TIMEOUT]')} {desc} (exceeded 10 minutes)")
        except Exception as exc:
            print(f"  {_red('[ERROR]')} {desc}: {exc}")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="setup",
        description=(
            "AuraGen -- Project Setup & Verification Script. "
            "Checks prerequisites, verifies folder structure, and "
            "guides the user through fixing any issues."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python setup.py            Full check + interactive fix\n"
            "  python setup.py --check    Verify only (no changes)\n"
            "  python setup.py --verbose  Show extra details\n"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Verify-only mode: print the report and exit (no changes made).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show additional details for each check.",
    )
    return parser


def main() -> int:
    """Entry point. Returns 0 if all checks pass, 1 otherwise."""
    parser = build_parser()
    args = parser.parse_args()

    # --- Run all checks ---
    results = run_all_checks()

    # --- Auto-create trivial directories ---
    _auto_create_outputs(results)

    # --- Print the report ---
    print_report(results, verbose=args.verbose)

    # --- Compute outcome ---
    all_passed = all(r.passed for r in results)
    hard_failures = [r for r in results if not r.passed and not r.warning]

    if args.check:
        # Verify-only mode: exit with appropriate code
        return 0 if all_passed else 1

    # --- Interactive mode ---
    if hard_failures:
        fix_actions = _collect_fix_actions(results)
        if fix_actions:
            print("  Some checks failed. Automatic fixes are available.")
            try:
                answer = input("  Would you like to install missing dependencies now? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if answer in ("y", "yes"):
                run_fix_actions(fix_actions)
                # Re-run checks and print updated report
                print()
                print("  Re-running verification...")
                results = run_all_checks()
                _auto_create_outputs(results)
                print_report(results, verbose=args.verbose)
                all_passed = all(r.passed for r in results)
        else:
            print("  Some checks failed but require manual intervention.")
            print("  Review the FAIL items above for guidance.")
            print()
    else:
        if all_passed:
            print("  All systems go. You can start developing!")
        else:
            print("  All critical checks passed. Warnings above are informational.")
        print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
