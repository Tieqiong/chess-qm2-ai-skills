"""Regression checks for commands and safeguards, without diffraction jobs."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "chess-dials-reduction/scripts/orchestrate_dials.py"
spec = importlib.util.spec_from_file_location("orchestrate_dials", SCRIPT)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / "work with spaces"
        self.work.mkdir()
        self.raw = self.root / "raw sweep"
        self.raw.mkdir()
        (self.raw / "sample_001.cbf").touch()
        (self.raw / "sample_002.cbf").touch()

    def args(self, stage, *extra):
        common = [stage, "--work-dir", str(self.work), "--dials-env", str(self.root / "env file.sh")]
        if stage == "stage1":
            common += ["--raw-dir", str(self.raw)]
        else:
            common += ["--bravais-setting", "1"]
            (self.work / "bravais_setting_1.expt").touch()
        return pipeline.build_parser().parse_args([*common, *extra])

    def fake_run(self, argv, **kwargs):
        argv = [str(arg) for arg in argv]
        self.commands.append(argv)
        if argv[0] == "dials.export":
            for argument in argv:
                if argument.startswith(("shelx.hklout=", "shelx.ins=")):
                    Path(argument.split("=", 1)[1]).write_text("exported\n")
        if argv[0] == "iotbx.reflection_file_converter":
            Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--shelx="))).write_text("merged\n")
        return ""

    def run_stage2(self, *extra):
        self.commands = []
        with patch.object(pipeline, "run_cmd", side_effect=self.fake_run):
            pipeline.stage_2(self.args("stage2", *extra))
        return self.commands

    def test_bash_activation_and_literal_arguments(self):
        env_file = self.root / "env $file.sh"
        env_file.write_text("export TEST_DIALS_ACTIVATION=ready\n")
        literal = "a path; $(touch NOT_CREATED) `touch NOT_CREATED`"
        output = pipeline.run_cmd(
            [sys.executable, "-c", "import os,sys,json; print(json.dumps([os.environ['TEST_DIALS_ACTIVATION'],sys.argv[1]]))", literal],
            cwd=self.root, dials_env=env_file,
        )
        self.assertEqual(json.loads(output), ["ready", literal])
        self.assertFalse((self.root / "NOT_CREATED").exists())
        with self.assertRaises(RuntimeError):
            pipeline.run_cmd([sys.executable, "-c", "raise SystemExit(7)"])

    def test_poni_origin_and_rotation_guard(self):
        poni = self.root / "test.poni"
        poni.write_text("Distance: 0.5\nPoni1: 0.2\nPoni2: 0.21\nRot1: 0\nRot2: 0\nRot3: 0\n")
        self.assertEqual(pipeline.parse_poni_origin(poni), "-210.000000,200.000000,-500.000000")
        poni.write_text(poni.read_text().replace("Rot2: 0", "Rot2: 0.01"))
        with self.assertRaisesRegex(ValueError, "geometry-phil"):
            pipeline.parse_poni_origin(poni)

    def test_multi_sweep_is_not_silently_imported_with_one_axis(self):
        self.assertEqual(len(pipeline.discover_sweep(str(self.raw))), 2)
        other = self.raw / "other"
        other.mkdir()
        (other / "sample_001.cbf").touch()
        with self.assertRaisesRegex(ValueError, "dials.cosym"):
            pipeline.discover_sweep(str(self.raw))
        other_file = other / "sample_001.cbf"
        other_file.unlink()
        (self.raw / "second_001.cbf").touch()
        with self.assertRaisesRegex(ValueError, "multiple CBF sweeps"):
            pipeline.discover_sweep(str(self.raw))

    def test_missing_known_symmetry_fails_before_processing(self):
        args = self.args("stage1", "--constrain-symmetry", "--space-group", "P1")
        with patch.object(pipeline, "run_cmd") as runner:
            with self.assertRaisesRegex(ValueError, "requires both"):
                pipeline.stage_1(args)
            runner.assert_not_called()

    def test_stage1_uses_literal_paths_and_space_group_matcher(self):
        self.commands = []
        geometry = self.root / "calibration with spaces.phil"
        geometry.write_text("geometry.detector.panel.origin=-210,200,-500\n")
        custom = self.work / "find_spots.phil"
        custom.write_text("spotfinder.filter.min_spot_size=3\n")
        args = self.args("stage1", "--geometry-phil", str(geometry), "--unit-cell", "5 5 8 90 90 90",
                         "--space-group", "P 4", "--constrain-symmetry")
        with patch.object(pipeline, "run_cmd", side_effect=self.fake_run):
            pipeline.stage_1(args)
        self.assertEqual(custom.read_text(), "spotfinder.filter.min_spot_size=3\n")
        imported = self.commands[0]
        self.assertIn(str(self.raw / "sample_001.cbf"), imported)
        self.assertIn(str(geometry), imported)
        indexed = next(cmd for cmd in self.commands if cmd[0] == "dials.index")
        self.assertIn("indexing.known_symmetry.space_group=P 4", indexed)
        self.assertIn("indexing.known_symmetry.unit_cell=5.0,5.0,8.0,90.0,90.0,90.0", indexed)
        matcher = self.commands[-1]
        self.assertEqual(matcher[0], "dials.python")
        self.assertIn("--target-space-group", matcher)
        self.assertNotIn("--target-lattice", matcher)

    def test_export_uses_supported_outputs_and_real_merge_product(self):
        commands = self.run_stage2()
        export = next(cmd for cmd in commands if cmd[0] == "dials.export")
        self.assertIn("intensity=scale", export)
        self.assertIn("mtz.min_isigi=None", export)
        self.assertTrue(any(arg.startswith("shelx.hklout=") for arg in export))
        self.assertTrue(any(arg.startswith("shelx.ins=") for arg in export))
        self.assertFalse(any(arg.startswith("output.reflections=") for arg in export))
        self.assertNotIn("merged.expt", sum(commands, []))
        self.assertNotIn("merged.refl", sum(commands, []))
        merge = next(cmd for cmd in commands if cmd[0] == "dials.merge")
        self.assertIn("assess_space_group=False", merge)
        self.assertIn("truncate=False", merge)
        self.assertIn("--label=IMEAN,SIGIMEAN", commands[-1])
        bundle = self.work / "for_refinement"
        self.assertEqual((bundle / "merged.ins").read_text(), (bundle / "unmerged.ins").read_text())
        self.assertIn("Friedel-averaged", (bundle / "README.txt").read_text())

    def test_motion_scale_only_and_input_symmetry_are_selectable(self):
        commands = self.run_stage2("--scan-varying", "True", "--no-fix-cell", "--scaling-model", "scale-only", "--keep-input-symmetry")
        refine = next(cmd for cmd in commands if cmd[0] == "dials.refine")
        self.assertIn("scan_varying=True", refine)
        self.assertNotIn("refinement.parameterisation.crystal.fix=cell", refine)
        self.assertNotIn("dials.symmetry", [cmd[0] for cmd in commands])
        scale = next(cmd for cmd in commands if cmd[0] == "dials.scale")
        self.assertIn("integrated.expt", scale)
        self.assertIn("model=KB", scale)
        self.assertIn("KB.decay_correction=False", scale)
        self.assertFalse(any(arg.startswith("physical.") for arg in scale))

    def test_explicit_symmetry_and_no_absorption_branch(self):
        commands = self.run_stage2("--space-group", "P 1", "--absorption-level", "none")
        reindex = next(cmd for cmd in commands if cmd[0] == "dials.reindex")
        self.assertIn("space_group=P 1", reindex)
        scale = next(cmd for cmd in commands if cmd[0] == "dials.scale")
        self.assertIn("candidate.expt", scale)
        self.assertIn("physical.absorption_correction=False", scale)
        self.assertNotIn("dials.symmetry", [cmd[0] for cmd in commands])

    @unittest.skipUnless(importlib.util.find_spec("dials"), "requires an installed DIALS")
    def test_stage2_commands_match_installed_dials_phil(self):
        from dials.command_line import export, merge, reindex, refine, scale, symmetry
        modules = {"dials." + module.__name__.split(".")[-1]: module
                   for module in (export, merge, reindex, refine, scale, symmetry)}
        for options in ((), ("--scaling-model", "scale-only", "--no-fix-cell", "--scan-varying", "True"),
                        ("--space-group", "P 1", "--absorption-level", "none")):
            for command in self.run_stage2(*options):
                if command[0] not in modules:
                    continue
                scope = modules[command[0]].phil_scope
                interpreter = scope.command_line_argument_interpreter()
                sources = [interpreter.process(arg=arg) for arg in command[1:] if "=" in arg]
                validated, unused = scope.fetch(sources=sources, track_unused_definitions=True)
                self.assertFalse(unused, (command, unused))
                validated.extract()

    @unittest.skipUnless(importlib.util.find_spec("dials"), "requires an installed DIALS")
    def test_stage1_commands_match_installed_dials_phil(self):
        from dials.command_line import dials_import, find_spots, generate_mask, index, refine_bravais_settings
        modules = {"dials." + module.__name__.split(".")[-1]: module
                   for module in (find_spots, generate_mask, index, refine_bravais_settings)}
        modules["dials.import"] = dials_import
        self.commands = []
        with patch.object(pipeline, "run_cmd", side_effect=self.fake_run):
            pipeline.stage_1(self.args("stage1", "--unit-cell", "5,5,8,90,90,90", "--space-group", "P 4", "--constrain-symmetry"))
        for command in self.commands:
            if command[0] not in modules:
                continue
            scope = modules[command[0]].phil_scope
            interpreter = scope.command_line_argument_interpreter()
            sources = [interpreter.process(arg=arg) for arg in command[1:] if "=" in arg]
            validated, unused = scope.fetch(sources=sources, track_unused_definitions=True)
            self.assertFalse(unused, (command, unused))
            validated.extract()

    def test_converter_cannot_reuse_stale_output_after_silent_failure(self):
        bundle = self.work / "for_refinement"
        bundle.mkdir()
        (bundle / "merged.hkl").write_text("stale data\n")
        self.commands = []
        def fail_converter(argv, **kwargs):
            if argv[0] != "iotbx.reflection_file_converter":
                return self.fake_run(argv, **kwargs)
            return "converter failed\n"
        with patch.object(pipeline, "run_cmd", side_effect=fail_converter):
            with self.assertRaisesRegex(RuntimeError, "nonempty merged.hkl"):
                pipeline.stage_2(self.args("stage2"))
        self.assertEqual((bundle / "merged.hkl").read_text(), "stale data\n")


if __name__ == "__main__":
    unittest.main()
