"""Unit tests for the step 2.1 baseline tools: baseline_run.py's helpers and failure
reports, make_submit.py, collect_baseline.py and compare_results.py. The job's DINGO
steps run on the cluster (the launcher's pre-flight and the job). Standard library
only, except compare_results.py's tests, which need numpy as the script does."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import COMMIT, SPEEDUPS, load_module, make_tree, run_script, write  # noqa: E402

BASELINE = SPEEDUPS / "baseline"
run = load_module("baseline_run_under_test", BASELINE / "baseline_run.py")
make_submit = load_module("make_submit_under_test", BASELINE / "make_submit.py")
collect = load_module("collect_baseline_under_test", BASELINE / "collect_baseline.py")
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
compare = load_module("compare_results_under_test", BASELINE / "compare_results.py") if HAVE_NUMPY else None
REAL_LOG = (
    SPEEDUPS.parent / "parallelisation/tutorial_reference/ex3_dingo_lensing_application"
    / "dingo_EXP1_lensed/log_data_generation/label_data0_1384782888-63_generation.log"
)


def tarball_of(tree: Path, destination: Path) -> Path:
    path = destination / f"{tree.name}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        archive.add(tree, arcname=tree.name)
    return path


class TempCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)


class TestHelpers(TempCase):
    def test_parse_status_reads_kilobytes_as_bytes(self):
        text = "Name:\tpython\nVmHWM:\t  2048 kB\nVmRSS:\t1024 kB\n"
        self.assertEqual(run.parse_status(text, "VmHWM"), 2048 * 1024)
        self.assertEqual(run.parse_status(text, "VmRSS"), 1024 * 1024)
        self.assertIsNone(run.parse_status(text, "VmPeak"))
        self.assertIsNone(run.parse_status("VmHWM:\t12 MB\n", "VmHWM"))

    def test_wrap_timed_calls_through_and_counts(self):
        class Owner:
            @staticmethod
            def work(x, y=1):
                return x + y

        records = {}
        run.wrap_timed(Owner, "work", records, "work")
        self.assertEqual(Owner.work(2, y=3), 5)
        self.assertEqual(Owner.work(1), 2)
        self.assertTrue(records["work"]["found"])
        self.assertEqual(records["work"]["calls"], 2)
        self.assertGreaterEqual(records["work"]["seconds"], 0)

    def test_wrap_timed_records_a_missing_function_without_failing(self):
        records = {}
        run.wrap_timed(object(), "absent", records, "absent")
        self.assertEqual(records["absent"], {"found": False})

    def test_stages_time_each_step(self):
        stages = run.Stages()
        with stages.stage("one"):
            pass
        self.assertGreaterEqual(stages.records["one"]["seconds"], 0)
        self.assertIn("main_peak_bytes", stages.records["one"])

    def test_unpack_gives_the_tree(self):
        tree = make_tree(self.base / "src")
        tarball = tarball_of(tree, self.base)
        unpacked = run.unpack(tarball, self.base / "dest")
        self.assertEqual(unpacked, (self.base / "dest" / tree.name).resolve())
        self.assertTrue((unpacked / "dingo" / "__init__.py").is_file())

    def test_unpack_refuses_members_outside_the_folder_and_links(self):
        for kind in ("outside", "link"):
            with self.subTest(kind=kind):
                path = self.base / f"{kind}_{'0' * 10}.tar.gz"
                with tarfile.open(path, "w:gz") as archive:
                    info = tarfile.TarInfo("../evil.txt" if kind == "outside" else "dingo_x/link")
                    if kind == "link":
                        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                    archive.addfile(info, io.BytesIO(b""))
                with self.assertRaises(ValueError):
                    run.unpack(path, self.base / f"dest_{kind}")


class TestJobFailures(TempCase):
    """The job always leaves out/baseline.json and exits with the documented code."""

    def scratch(self, tree_commit: str = COMMIT) -> Path:
        scratch = self.base / "scratch"
        scratch.mkdir()
        shutil.copy(BASELINE / "baseline_run.py", scratch)
        shutil.copy(SPEEDUPS / "guard.py", scratch)
        tarball_of(make_tree(self.base / "src", commit=tree_commit), scratch)
        return scratch

    def run_job(self, scratch: Path, tarball: str, commit: str, network=("--model", "model.pt")):
        args = ["--tarball", tarball, "--commit", commit, *network, "--event-data", "event.hdf5"]
        result = run_script(scratch / "baseline_run.py", args, cwd=scratch)
        report = json.loads((scratch / "out" / "baseline.json").read_text())
        return result, report

    def test_a_refused_commit_exits_2_with_a_report(self):
        scratch = self.scratch()
        result, report = self.run_job(scratch, f"dingo_{COMMIT[:10]}.tar.gz", "fedcba9876543210")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("GUARD FAILED", report["error"])

    def test_a_missing_tarball_exits_2_with_a_report(self):
        scratch = self.scratch()
        result, report = self.run_job(scratch, "missing.tar.gz", COMMIT)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("SETUP FAILED", report["error"])

    def test_exactly_one_of_model_and_proposal_or_exit_2(self):
        for network in ((), ("--model", "model.pt", "--proposal", "samples.hdf5")):
            with self.subTest(network=network):
                scratch = self.scratch()
                result, report = self.run_job(scratch, f"dingo_{COMMIT[:10]}.tar.gz", COMMIT, network)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("SETUP FAILED", report["error"])
                self.assertIn("exactly one of --model and --proposal", report["error"])
                shutil.rmtree(scratch)
                shutil.rmtree(self.base / "src")

    def test_a_failure_after_the_guard_exits_1_with_the_traceback(self):
        # Without site-packages there is no numpy, so the first DINGO step fails.
        scratch = self.scratch()
        result, report = self.run_job(scratch, f"dingo_{COMMIT[:10]}.tar.gz", COMMIT)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Traceback", report["traceback"])
        self.assertEqual(report["provenance"]["dingo"]["commit"], COMMIT)
        self.assertIn("unpack", report["stages"])
        self.assertIn("total_seconds", report)


class TestSubmitFile(unittest.TestCase):
    def job(self, **changes):
        settings = dict(
            image_url="osdf:///igwn/cit/staging/me/containers/dingo-deps_recipe-8f44d79_cpu.sif",
            run_script="/home/me/run/baseline_run.py",
            guard="/home/me/run/guard.py",
            tarball="/home/me/run/dingo_dd481d9846.tar.gz",
            model="/home/me/models/model_nonlensed.pt",
            event_data="/home/me/data/event.hdf5",
            commit="dd481d98467c14114d7cf81981076806c5b2a4bc"
        )
        settings.update(changes)
        return make_submit.BaselineJob(**settings)

    def lines(self, **changes):
        return make_submit.submit_text(self.job(**changes)).splitlines()

    def test_runs_the_images_python_on_the_script_with_the_inputs_by_name(self):
        lines = self.lines()
        self.assertIn("executable = /opt/dingo_env/bin/python", lines)
        self.assertIn(
            'arguments = "-I baseline_run.py --tarball dingo_dd481d9846.tar.gz '
            "--commit dd481d98467c14114d7cf81981076806c5b2a4bc --model model_nonlensed.pt "
            '--event-data event.hdf5 --num-samples 50000 --batch-size 5000 --num-processes 32 --seed 1"',
            lines
        )

    def test_uses_the_image_from_osdf_as_the_smoke_test_did(self):
        lines = self.lines()
        self.assertIn('MY.SingularityImage = "./dingo-deps_recipe-8f44d79_cpu.sif"', lines)
        self.assertIn("requirements = (HAS_SINGULARITY=?=True)", lines)
        self.assertIn("use_oauth_services = scitokens", lines)
        self.assertIn("MY.flock_local = True", lines)
        self.assertIn('MY.DESIRED_Sites = "nogrid"', lines)
        transfer = next(line for line in lines if line.startswith("transfer_input_files = "))
        expected = [
            "osdf:///igwn/cit/staging/me/containers/dingo-deps_recipe-8f44d79_cpu.sif",
            "/home/me/run/baseline_run.py",
            "/home/me/run/guard.py",
            "/home/me/run/dingo_dd481d9846.tar.gz",
            "/home/me/models/model_nonlensed.pt",
            "/home/me/data/event.hdf5"
        ]
        self.assertEqual(transfer.split(" = ", 1)[1].split(", "), expected)
        self.assertIn("transfer_output_files = out", lines)

    def test_resources_priority_and_threads(self):
        lines = self.lines()
        expected_lines = (
            "request_cpus = 32",
            "request_memory = 48GB",
            "request_disk = 12GB",
            "priority = 50",
            'environment = "OMP_NUM_THREADS=1"',
            "accounting_group = ligo.dev.o4.cbc.explore.test"
        )
        for expected in expected_lines:
            self.assertIn(expected, lines)
        self.assertIn("--num-processes 16", self.lines(cpus=16)[2])
        self.assertIn("priority = 10", self.lines(priority=10))

    def test_refuses_bad_inputs(self):
        bad_inputs = (
            {"image_url": "/home/me/image.sif"},
            {"model": "model.pt"},
            {"tarball": "/home/me/a b.tar.gz"},
            {"commit": "dd481d98"},
            {"cpus": 0}
        )
        for changes in bad_inputs:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    make_submit.submit_text(self.job(**changes))

    def test_a_proposal_replaces_the_model(self):
        lines = self.lines(model=None, proposal="/home/me/runs/out/network_samples.hdf5")
        arguments = next(line for line in lines if line.startswith("arguments = "))
        expected = f"--commit {self.job().commit} --proposal network_samples.hdf5 --event-data"
        self.assertIn(expected, arguments)
        self.assertNotIn("--model", arguments)
        transfer_line = next(line for line in lines if line.startswith("transfer_input_files = "))
        transfer = transfer_line.split(" = ", 1)[1].split(", ")
        self.assertIn("/home/me/runs/out/network_samples.hdf5", transfer)
        self.assertNotIn("/home/me/models/model_nonlensed.pt", transfer)

    def test_refuses_both_or_neither_network_input(self):
        cases = ({"proposal": "/home/me/p.hdf5"}, {"model": None}, {"model": None, "proposal": "p.hdf5"})
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    make_submit.submit_text(self.job(**changes))

    def test_command_line_takes_a_proposal_but_not_both(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.sub"
            job = self.job(model=None, proposal="/home/me/runs/out/network_samples.hdf5")
            names = ("image_url", "run_script", "guard", "tarball", "proposal", "event_data", "commit")
            args = [f"--{k.replace('_', '-')}={v}" for k, v in vars(job).items() if k in names]
            self.assertEqual(make_submit.main([*args, "--output", str(output)]), 0)
            self.assertEqual(output.read_text(), make_submit.submit_text(job))
            both = [*args, "--model", "/home/me/models/model_nonlensed.pt", "--output", str(output)]
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                make_submit.main(both)

    def test_command_line_writes_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.sub"
            job = self.job()
            names = ("image_url", "run_script", "guard", "tarball", "model", "event_data", "commit")
            args = [f"--{k.replace('_', '-')}={v}" for k, v in vars(job).items() if k in names]
            self.assertEqual(make_submit.main([*args, "--priority", "50", "--output", str(output)]), 0)
            self.assertEqual(output.read_text(), make_submit.submit_text(job))


class TestCompare(TempCase):
    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_identical_columns_agree_with_matching_nans_and_infinities(self):
        # The log prior of samples outside the prior is -inf in both results.
        nan, inf = float("nan"), float("inf")
        values = [1.0, -2.0, nan, -inf, inf]
        differences = compare.column_differences(values, list(values))
        expected = {"max_abs": 0.0, "max_rel": 0.0, "nonfinite": 3, "nonfinite_mismatch": 0}
        self.assertEqual(differences, expected)
        self.assertTrue(compare.agrees(differences, 0.0))

    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_mismatched_infinities_fail(self):
        inf = float("inf")
        pairs = (([1.0, -inf], [1.0, inf]), ([1.0, -inf], [1.0, -5.0]), ([1.0, float("nan")], [1.0, -inf]))
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                differences = compare.column_differences(a, b)
                self.assertEqual(differences["nonfinite_mismatch"], 1)
                self.assertEqual(differences["max_rel"], 0.0)
                self.assertFalse(compare.agrees(differences, 1.0))

    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_relative_difference_is_against_the_larger_magnitude(self):
        differences = compare.column_differences([100.0, -1.0], [100.5, -1.0])
        self.assertEqual(differences["max_abs"], 0.5)
        self.assertEqual(differences["max_rel"], 0.5 / 100.5)
        self.assertTrue(compare.agrees(differences, 0.005))
        self.assertFalse(compare.agrees(differences, 0.004))

    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_a_difference_from_zero_counts_in_full(self):
        differences = compare.column_differences([0.0, 0.0], [0.0, 1e-300])
        self.assertEqual(differences["max_rel"], 1.0)

    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_a_nan_in_only_one_fails(self):
        differences = compare.column_differences([1.0, float("nan")], [1.0, 2.0])
        self.assertEqual(differences["nonfinite_mismatch"], 1)
        self.assertEqual(differences["max_rel"], 0.0)
        self.assertFalse(compare.agrees(differences, 1.0))

    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_columns_of_different_length_are_refused(self):
        with self.assertRaises(ValueError):
            compare.column_differences([1.0, 2.0], [1.0])

    @unittest.skipUnless(HAVE_NUMPY, "needs numpy")
    def test_a_refused_commit_exits_2(self):
        # With site-packages for numpy; the guard refuses before DINGO is imported.
        tree = make_tree(self.base / "src")
        args = ["--tree", str(tree), "--commit", "fedcba9876543210", "--output", str(self.base / "c.json")]
        args += ["a.hdf5", "b.hdf5"]
        result = run_script(BASELINE / "compare_results.py", args, site=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("GUARD FAILED", result.stderr)
        self.assertFalse((self.base / "c.json").exists())


sys.path.insert(0, str(SPEEDUPS.parent / "parallelisation" / "tests"))
try:  # the hand-built Condor log events of the log reader's own tests
    from test_condor_logs import executing, job_ad, submitted, terminated, transfer
except ImportError:  # pragma: no cover
    submitted = None


def successful_log() -> str:
    cluster = 600000001
    events = [
        submitted(cluster, "12:00:00"),
        job_ad(cluster, "12:00:00"),
        transfer(cluster, "14:00:00", "Started transferring input files"),
        transfer(cluster, "14:01:30", "Finished transferring input files"),
        executing(cluster, "14:01:31"),
        job_ad(cluster, "14:01:31"),
        transfer(cluster, "14:13:31", "Started transferring output files"),
        transfer(cluster, "14:13:40", "Finished transferring output files"),
        terminated(cluster, "14:13:41")
    ]
    return "\n".join(events) + "\n"


@unittest.skipUnless(submitted is not None, "needs the parallelisation tests on this branch")
class TestCollect(TempCase):
    def run_dir(self, log: str, error=None) -> Path:
        run_dir = self.base / "20261027T120000Z"
        write(run_dir / "baseline.log", log)
        report = {
            "stages": {"synthetic_phase": {"seconds": 12.5}},
            "evidence": {"log_evidence": -1.0},
            "total_seconds": 99.0,
            "provenance": {"host": {"cpu": {"model": "CPU"}}}
        }
        if error:
            report["error"] = error
        write(run_dir / "out" / "baseline.json", json.dumps(report))
        write(run_dir / "launch.json", "{}")
        return run_dir

    def test_summary_combines_the_report_and_condors_log(self):
        summary = collect.summarise(self.run_dir(successful_log()))
        condor = summary["condor"]
        self.assertTrue(condor["succeeded"])
        self.assertEqual(condor["wait_seconds"], 2 * 3600)
        self.assertEqual(condor["input_transfer_seconds"], 90)
        self.assertEqual(condor["run_seconds"], 12 * 60)
        self.assertEqual(condor["memory_usage_mb"], 2345)
        self.assertEqual(condor["memory_request_mb"], 8192)
        self.assertIn("node1070", condor["host"])
        self.assertEqual(summary["stage_seconds"], {"synthetic_phase": 12.5})
        self.assertEqual(summary["host_cpu"], {"model": "CPU"})

    def test_copies_the_files_and_writes_the_summary(self):
        run_dir, results = self.run_dir(successful_log()), self.base / "results"
        with redirect_stdout(io.StringIO()):
            code = collect.main([str(run_dir), "--results", str(results)])
        self.assertEqual(code, 0)
        written = {path.name for path in (results / run_dir.name).iterdir()}
        self.assertEqual(written, {"baseline.log.txt", "launch.json", "baseline.json", "summary.json"})

    def test_a_job_that_reported_an_error_is_a_failure(self):
        run_dir = self.run_dir(successful_log(), error="boom")
        with redirect_stdout(io.StringIO()):
            code = collect.main([str(run_dir), "--results", str(self.base / "r")])
        self.assertEqual(code, 1)

    @unittest.skipUnless(REAL_LOG.is_file(), "needs the Exercise 3 Condor log on this branch")
    def test_a_job_condor_never_finished_is_a_failure(self):
        # The real CIT log of a job that was evicted, held and aborted.
        run_dir = self.run_dir(REAL_LOG.read_text())
        self.assertFalse(collect.summarise(run_dir)["condor"]["succeeded"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(collect.main([str(run_dir), "--results", str(self.base / "r")]), 1)


if __name__ == "__main__":
    unittest.main()
