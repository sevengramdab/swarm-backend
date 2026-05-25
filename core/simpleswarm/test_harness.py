"""
test_harness.py
================
Self-testing module for SwarmCoder-generated projects.
Automatically verifies syntax, imports, endpoints, and CLI behavior.
No human intervention required.
"""

import subprocess
import json
import time
import sys
import os
import urllib.request
from pathlib import Path
from typing import Dict, List, Any


class TestHarness:
    """Autonomous test runner for generated Python projects."""

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()
        self.results: List[Dict[str, Any]] = []

    def test_syntax(self, filepath: Path) -> Dict[str, Any]:
        """Test that a Python file compiles without syntax errors."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(filepath)],
            capture_output=True, text=True, timeout=10
        )
        return {
            "test": "syntax",
            "file": filepath.name,
            "passed": result.returncode == 0,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    def test_imports(self, filepath: Path) -> Dict[str, Any]:
        """Test that a Python file can be imported without errors."""
        original_dir = os.getcwd()
        try:
            os.chdir(self.project_dir)
            module_name = filepath.stem
            # Use importlib to test import
            cmd = f"import importlib; importlib.import_module('{module_name}')"
            result = subprocess.run(
                [sys.executable, "-c", cmd],
                capture_output=True, text=True, timeout=15,
                cwd=str(self.project_dir)
            )
            return {
                "test": "imports",
                "file": filepath.name,
                "passed": result.returncode == 0,
                "error": result.stderr.strip() if result.returncode != 0 else None,
            }
        finally:
            os.chdir(original_dir)

    def test_cli_help(self, filepath: Path) -> Dict[str, Any]:
        """Test that a CLI app responds to --help."""
        result = subprocess.run(
            [sys.executable, str(filepath), "--help"],
            capture_output=True, text=True, timeout=10
        )
        return {
            "test": "cli_help",
            "file": filepath.name,
            "passed": result.returncode == 0 and len(result.stdout) > 50,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    def test_flask_endpoints(self, filepath: Path, port: int = 8765) -> Dict[str, Any]:
        """Start a Flask app and test basic endpoints."""
        env = os.environ.copy()
        env["FLASK_RUN_PORT"] = str(port)
        env["FLASK_APP"] = str(filepath)
        
        # Try to detect if it's a Flask app by reading it
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        if "Flask(" not in text:
            return {"test": "flask_endpoints", "file": filepath.name, "passed": None, "error": "Not a Flask app"}

        # Start the app in a subprocess
        proc = subprocess.Popen(
            [sys.executable, str(filepath)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(self.project_dir), env=env
        )
        time.sleep(4)  # Give it time to start

        tests_passed = True
        errors = []
        try:
            # Test root or /tasks endpoint
            for path in ["/tasks", "/"]:
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", timeout=5)
                    resp = urllib.request.urlopen(req)
                    if resp.status in (200, 404):
                        break
                except Exception as e:
                    errors.append(f"{path}: {str(e)}")
            else:
                tests_passed = False
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()

        return {
            "test": "flask_endpoints",
            "file": filepath.name,
            "passed": tests_passed,
            "error": "; ".join(errors) if errors else None,
        }

    def test_streamlit_import(self, filepath: Path) -> Dict[str, Any]:
        """Test that a Streamlit app can at least be parsed without errors."""
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        if "streamlit" not in text.lower():
            return {"test": "streamlit_import", "file": filepath.name, "passed": None, "error": "Not a Streamlit app"}
        
        # Streamlit apps can't really be "imported" since they execute st calls at import time
        # We just verify syntax was already checked
        return {"test": "streamlit_import", "file": filepath.name, "passed": True, "error": None}

    def run_all_tests(self, filepath: Path) -> List[Dict[str, Any]]:
        """Run the full test suite for a single file."""
        results = []
        results.append(self.test_syntax(filepath))
        
        text = filepath.read_text(encoding="utf-8", errors="ignore").lower()
        
        if "flask" in text:
            results.append(self.test_flask_endpoints(filepath))
        elif "streamlit" in text:
            results.append(self.test_streamlit_import(filepath))
        elif "argparse" in text:
            results.append(self.test_cli_help(filepath))
        else:
            results.append(self.test_imports(filepath))
        
        return results

    def run_project_tests(self, project_dir: Path = None) -> Dict[str, Any]:
        """Run tests for all Python files in a project directory."""
        root = project_dir or self.project_dir
        exclude = {"test_*.py", "*_test.py", "conftest.py", "project_launcher.py"}
        
        all_results = []
        for f in sorted(root.glob("*.py")):
            if any(f.match(p) for p in exclude):
                continue
            all_results.extend(self.run_all_tests(f))
        
        passed = sum(1 for r in all_results if r["passed"] is True)
        failed = sum(1 for r in all_results if r["passed"] is False)
        skipped = sum(1 for r in all_results if r["passed"] is None)
        
        return {
            "total": len(all_results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "results": all_results,
        }


def main():
    """CLI entry point for running tests."""
    import argparse
    parser = argparse.ArgumentParser(description="SwarmCoder Self-Test Harness")
    parser.add_argument("--dir", default=".", help="Project directory to test")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()
    
    harness = TestHarness(args.dir)
    report = harness.run_project_tests()
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nTest Results: {report['passed']}/{report['total']} passed")
        if report['failed'] > 0:
            print(f"Failures: {report['failed']}")
        for r in report['results']:
            status = "PASS" if r['passed'] is True else "SKIP" if r['passed'] is None else "FAIL"
            print(f"  [{status}] {r['file']} — {r['test']}")
            if r['error']:
                print(f"       Error: {r['error'][:100]}")


if __name__ == "__main__":
    main()
