"""Exercise shell argument boundaries without launching DIALS or SGE."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TEMPLATES = Path(__file__).resolve().parents[1] / "chess-dials-reduction/example_job_scripts"
spec = importlib.util.spec_from_file_location(
    "batch_test_orchestrator", TEMPLATES.parent / "scripts/orchestrate_dials.py"
)
orchestrator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orchestrator)


class BatchTemplateTests(unittest.TestCase):
    def invoke(self, template, arguments):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "arguments.json"
            fake_python = root / "python3"
            fake_python.write_text(
                "#!" + sys.executable + "\n"
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['TEST_CAPTURE']).write_text(json.dumps({"
                "'argv':sys.argv[1:], 'threads':os.environ['OMP_NUM_THREADS']}))\n"
            )
            fake_python.chmod(0o755)
            environment = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                               TEST_CAPTURE=str(capture), NSLOTS="8",
                               SKILLS_DIR="/skills dir/with'quotes",
                               DIALS_ENV="/environment with spaces/activate.sh")
            result = subprocess.run(["bash", str(TEMPLATES / template), *arguments],
                                    env=environment, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "should-not-exist").exists())
            return json.loads(capture.read_text())

    def test_stage1_preserves_literals_and_extra_options(self):
        result = self.invoke("dials-stage1-template.sh", [
            "work dir", "raw$(touch should-not-exist)", "calibration.poni", "mask's.edf",
            "10,10,20,90,90,120", "P 63 2 2", "--global-threshold", "20",
        ])
        args = result["argv"]
        self.assertEqual(args[0], "/skills dir/with'quotes/scripts/orchestrate_dials.py")
        self.assertEqual(args[args.index("--raw-dir") + 1], "raw$(touch should-not-exist)")
        self.assertEqual(args[args.index("--space-group") + 1], "P 63 2 2")
        self.assertEqual(args[-2:], ["--global-threshold", "20"])
        self.assertEqual(args[args.index("--nproc") + 1], "8")
        self.assertEqual(result["threads"], "1")

    def test_stage2_templates_forward_refinement_options(self):
        for filename in ["dials-stage2-template.sh", "dials-batch-template.sh"]:
            with self.subTest(filename=filename):
                result = self.invoke(filename, ["work dir", "12", "b,c,a", "K Co Te O",
                                                "--no-fix-cell", "--scan-varying", "True"])
                args = result["argv"]
                self.assertEqual(args[args.index("--composition") + 1], "K Co Te O")
                self.assertEqual(args[-3:], ["--no-fix-cell", "--scan-varying", "True"])
                parsed = orchestrator.build_parser().parse_args(args[1:])
                self.assertFalse(parsed.fix_cell)
                self.assertEqual(parsed.scan_varying, "True")
                self.assertEqual(args[args.index("--nproc") + 1], "8")
                self.assertEqual(result["threads"], "1")

    def test_missing_arguments_report_usage(self):
        for path in TEMPLATES.glob("*.sh"):
            with self.subTest(filename=path.name):
                result = subprocess.run(["bash", str(path)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
