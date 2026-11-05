"""Unit tests for the end-to-end test of the multi-phase XPHM route: pack_lal.py, make_xphm_jobs.py,
xphm_job.py, stress_multiphase.py, run_suite.py, collect_xphm_tests.py, and baseline_run.py's and
compare_results.py's parts for it.

TestDryRun goes through the whole chain with the real manifests, job script and collection, and
stand-ins for the scripts that need DINGO and LAL. What needs them runs in the launcher's pre-flight.
The stress test's tests need numpy, as the script does; the rest is standard library."""
from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SPEEDUPS, load_module, make_tree, run_script, write  # noqa: E402

LAL = SPEEDUPS / "lal"
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
pack = load_module("pack_lal_under_test", LAL / "pack_lal.py")
jobs = load_module("make_xphm_jobs_under_test", LAL / "make_xphm_jobs.py")
driver = load_module("xphm_job_under_test", LAL / "xphm_job.py")
collect = load_module("collect_xphm_tests_under_test", LAL / "collect_xphm_tests.py")
show = load_module("show_job_under_test", LAL / "show_job.py")
run = load_module("baseline_run_for_xphm", SPEEDUPS / "baseline" / "baseline_run.py")
guard = load_module("guard_for_xphm", SPEEDUPS / "guard.py")
compare = load_module("compare_results_for_xphm", SPEEDUPS / "baseline" / "compare_results.py") if HAVE_NUMPY else None
stress = load_module("stress_multiphase_under_test", LAL / "stress_multiphase.py") if HAVE_NUMPY else None
leak = load_module("leak_check_under_test", LAL / "leak_check.py") if HAVE_NUMPY else None
if HAVE_NUMPY:
    import numpy as np

COMMITS = {name: character * 40 for name, character in (("upstream", "a"), ("branch", "b"), ("combined", "c"), ("pr454", "d"))}


class TempCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)


def inputs_at(base: str = "/runs/x") -> "jobs.Inputs":
    return jobs.Inputs(
        run_dir=base,
        image_url="osdf:///igwn/cit/staging/me/containers/image.sif",
        upstream_tarball=f"{base}/dingo_aaaaaaaaaa.tar.gz",
        upstream_commit=COMMITS["upstream"],
        pr454_tarball=f"{base}/dingo_dddddddddd.tar.gz",
        pr454_commit=COMMITS["pr454"],
        branch_tarball=f"{base}/dingo_bbbbbbbbbb.tar.gz",
        branch_commit=COMMITS["branch"],
        combined_tarball=f"{base}/dingo_cccccccccc.tar.gz",
        combined_commit=COMMITS["combined"],
        lal_tarball=f"{base}/lal_e21ec9674d.tar.gz",
        proposal="/data/runs/network_samples.hdf5",
        model="/data/models/model_nonlensed.pt",
        event_data="/data/event/event_data.hdf5"
    )


class TestParseLdd(unittest.TestCase):
    OUTPUT = """\
\tlinux-vdso.so.1 (0x00007ffc)
\tliblal.so.20 => /home/me/env/lib/liblal.so.20 (0x00007f01)
\tlibm.so.6 => /lib64/libm.so.6 (0x00007f02)
\t/lib64/ld-linux-x86-64.so.2 (0x00007f03)
"""

    def test_reads_the_libraries_with_a_path(self):
        found = pack.parse_ldd(self.OUTPUT)
        self.assertEqual(found, {"liblal.so.20": "/home/me/env/lib/liblal.so.20", "libm.so.6": "/lib64/libm.so.6"})

    def test_a_library_ldd_cannot_find_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "libgsl.so.28"):
            pack.parse_ldd("\tlibgsl.so.28 => not found\n")


class TestPack(TempCase):
    def make_env(self, extra_ldd=""):
        env = self.base / "env"
        site = env / "lib" / "python3.13" / "site-packages"
        write(site / "lal" / "__init__.py", "")
        write(site / "lal" / "_lal.cpython-313-x86_64-linux-gnu.so", "lal module")
        write(site / "lal" / "__pycache__" / "x.pyc", "bytecode")
        write(site / "lalsimulation" / "__init__.py", "")
        write(site / "lalsimulation" / "gwsignal" / "__init__.py", "")
        write(site / "lalsimulation" / "_lalsimulation.cpython-313-x86_64-linux-gnu.so", "lalsimulation module")
        for library in ("liblal.so.20", "liblalsimulation.so.37", "libopenblas.so.0"):
            write(env / "lib" / library, library)
        built = write(self.base / "BUILT.txt", "tag x\npatch_sha256 e21ec9674dc6b108\n")
        return env, built, self.make_env_output(env, extra_ldd)

    def make_env_output(self, env, extra_ldd=""):
        lib = (env / "lib").as_posix()
        return f"""\
\tliblal.so.20 => {lib}/liblal.so.20 (0x1)
\tliblalsimulation.so.37 => {lib}/liblalsimulation.so.37 (0x2)
\tlibcblas.so.3 => {lib}/libopenblas.so.0 (0x3)
\tlibopenblas.so.0 => {lib}/libopenblas.so.0 (0x3)
\tlibm.so.6 => /lib64/libm.so.6 (0x4)
{extra_ldd}"""

    def test_the_tarball_holds_the_packages_and_the_libraries_of_the_environment(self):
        env, built, output = self.make_env()
        record = pack.pack(env, built, self.base / "out", ldd=lambda path: output)
        self.assertEqual(record["top"], "lal_e21ec9674d")
        self.assertEqual(Path(record["path"]).name, "lal_e21ec9674d.tar.gz")
        self.assertNotIn("libm.so.6", record["libraries"])
        with tarfile.open(record["path"]) as archive:
            names = set(archive.getnames())
            top = "lal_e21ec9674d"
            self.assertIn(f"{top}/python/lal/_lal.cpython-313-x86_64-linux-gnu.so", names)
            self.assertIn(f"{top}/python/lalsimulation/gwsignal/__init__.py", names)
            self.assertIn(f"{top}/lib/liblal.so.20", names)
            self.assertIn(f"{top}/BUILT.txt", names)
            self.assertFalse([name for name in names if "__pycache__" in name])
            manifest = json.load(archive.extractfile(f"{top}/MANIFEST.json"))
            self.assertEqual(manifest["patch_sha256"], "e21ec9674dc6b108")
            self.assertEqual(set(manifest["libraries"]), set(record["libraries"]))
            # One file asked for under two names goes in once.
            link = archive.getmember(f"{top}/lib/libopenblas.so.0")
            self.assertTrue(link.issym())
            self.assertEqual(link.linkname, "libcblas.so.3")

    def test_the_job_script_unpacks_it(self):
        env, built, output = self.make_env()
        record = pack.pack(env, built, self.base / "out", ldd=lambda path: output)
        root = driver.unpack(Path(record["path"]), self.base / "unpacked")
        self.assertEqual(root.name, "lal_e21ec9674d")
        self.assertEqual((root / "lib" / "liblal.so.20").read_text(), "liblal.so.20")
        self.assertTrue((root / "python" / "lalsimulation" / "__init__.py").is_file())
        self.assertEqual((root / "lib" / "libopenblas.so.0").read_text(), "libopenblas.so.0")

    def test_refuses_an_environment_without_lal(self):
        env, built, output = self.make_env()
        without = "\n".join(line for line in output.splitlines() if "liblal" not in line)
        with self.assertRaisesRegex(ValueError, "liblal.so"):
            pack.pack(env, built, self.base / "out", ldd=lambda path: without)

    def test_refuses_a_build_without_the_extension_modules(self):
        env, built, output = self.make_env()
        next(env.glob("lib/python3.*/site-packages/lalsimulation/_lalsimulation*")).unlink()
        with self.assertRaisesRegex(ValueError, "extension modules"):
            pack.pack(env, built, self.base / "out", ldd=lambda path: output)

    def test_a_library_the_environment_has_comes_from_it_and_the_rest_is_listed(self):
        env, built, _ = self.make_env()
        write(env / "lib" / "libgfortran.so.5", "gfortran")
        steered = "\tlibgfortran.so.5 => /cvmfs/other/lib/libgfortran.so.5 (0x9)\n\tlibfoo.so.1 => /usr/lib64/libfoo.so.1 (0xa)\n"
        output = self.make_env_output(env, steered)
        record = pack.pack(env, built, self.base / "out", ldd=lambda path: output)
        self.assertIn("libgfortran.so.5", record["libraries"])
        self.assertEqual(record["left_to_the_image"], {"libfoo.so.1": "/usr/lib64/libfoo.so.1"})
        with tarfile.open(record["path"]) as archive:
            self.assertEqual(archive.extractfile("lal_e21ec9674d/lib/libgfortran.so.5").read(), b"gfortran")

    def test_every_name_of_a_packed_file_goes_in(self):
        # ldd lists OpenBLAS once, as libopenblas.so.0, where GSL asks for it as libcblas.so.3.
        env, built, _ = self.make_env()
        lib = env / "lib"
        os.link(lib / "libopenblas.so.0", lib / "libcblas.so.3")
        write(lib / "libunrelated.so.1", "unrelated")
        output = f"\tliblal.so.20 => {lib.as_posix()}/liblal.so.20 (0x1)\n\tlibopenblas.so.0 => {lib.as_posix()}/libopenblas.so.0 (0x2)\n"
        record = pack.pack(env, built, self.base / "out", ldd=lambda path: output)
        self.assertIn("libcblas.so.3", record["libraries"])
        self.assertNotIn("libunrelated.so.1", record["libraries"])
        root = driver.unpack(Path(record["path"]), self.base / "unpacked")
        self.assertEqual((root / "lib" / "libcblas.so.3").read_text(), "libopenblas.so.0")
        self.assertEqual((root / "lib" / "libopenblas.so.0").read_text(), "libopenblas.so.0")

    def test_ldd_runs_as_a_job_resolves_the_libraries(self):
        calls = []

        def fake_run(command, **options):
            calls.append((command, options["env"]))
            return SimpleNamespace(stdout="")

        environment = {"LD_LIBRARY_PATH": "/cvmfs/other/lib", "LD_PRELOAD": "/x.so"}
        with mock.patch.dict(os.environ, environment), mock.patch.object(pack.subprocess, "run", fake_run):
            pack.run_ldd(Path("/env/lib/python3.13/site-packages/lal/_lal.so"), Path("/env"))
        command, used = calls[0]
        self.assertEqual(command[0], "ldd")
        self.assertEqual(used["LD_LIBRARY_PATH"], str(Path("/env") / "lib"))
        self.assertNotIn("LD_PRELOAD", used)

    def test_refuses_a_built_file_without_the_patch_hash(self):
        env, _, output = self.make_env()
        built = write(self.base / "other.txt", "tag x\n")
        with self.assertRaisesRegex(ValueError, "patch_sha256"):
            pack.pack(env, built, self.base / "out", ldd=lambda path: output)


class TestMappedLibraries(TempCase):
    def maps(self, *paths):
        lines = ["7f00-7f01 r--p 00000000 00:00 0 ", "7f01-7f02 rw-p 00000000 00:00 0                          [heap]"]
        lines += [f"7f{k:02x}-7f{k + 1:02x} r-xp 00000000 08:01 {k}    {path}" for k, path in enumerate(paths, 3)]
        return write(self.base / "maps", "\n".join(lines) + "\n")

    def test_lists_the_lal_libraries_the_process_has_loaded(self):
        maps = self.maps("/a/lib/liblal.so.20", "/a/lib/liblal.so.20", "/a/lib/libgsl.so.28", "/usr/lib/libc.so.6", "/b/numpy.libs/libscipy_openblas.so")
        self.assertEqual(guard.mapped_libraries(maps=maps), ["/a/lib/libgsl.so.28", "/a/lib/liblal.so.20"])

    def test_finds_a_liblal_from_somewhere_else(self):
        shipped = self.base / "lal_e21ec9674d"
        inside = (shipped / "lib" / "liblal.so.20").as_posix()
        other = (self.base / "env" / "lib" / "liblalsupport.so.14").as_posix()
        self.assertEqual(guard.lal_libraries_outside(shipped, maps=self.maps(inside)), [])
        self.assertEqual(guard.lal_libraries_outside(shipped, maps=self.maps(inside, other)), [other])

    def test_cannot_tell_without_a_maps_file(self):
        self.assertIsNone(guard.mapped_libraries(maps=self.base / "missing"))
        self.assertIsNone(guard.lal_libraries_outside(self.base, maps=self.base / "missing"))


class TestRoute(unittest.TestCase):
    def test_count_calls_counts_and_passes_everything_through(self):
        owner = SimpleNamespace(work=lambda x, y=1: x + y)
        counters = {}
        run.count_calls(owner, "work", counters)
        self.assertEqual(owner.work(2, y=3), 5)
        self.assertEqual(owner.work(1), 2)
        self.assertEqual(counters["work"].value, 2)

    def test_count_calls_leaves_a_missing_function_uncounted(self):
        counters = {}
        run.count_calls(SimpleNamespace(), "work", counters)
        self.assertEqual(counters, {})

    @unittest.skipUnless(hasattr(os, "fork"), "needs fork, as DINGO's workers have on the cluster")
    def test_the_counts_reach_the_main_process_from_forked_workers(self):
        owner = SimpleNamespace(work=lambda x: x)
        counters = {}
        run.count_calls(owner, "work", counters)
        process = multiprocessing.get_context("fork").Process(target=owner.work, args=(1,))
        process.start()
        process.join()
        self.assertEqual(counters["work"].value, 1)

    def test_the_two_routes_by_their_calls(self):
        one = {run.MULTI_PHASE_CALL: 49_900, run.SINGLE_CALL: 9}
        nine = {run.SINGLE_CALL: 449_100}
        self.assertIsNone(run.route_problem("one", one, 50_000))
        self.assertIsNone(run.route_problem("nine", nine, 50_000))

    def test_a_run_on_the_other_route_is_a_problem(self):
        one = {run.MULTI_PHASE_CALL: 49_900, run.SINGLE_CALL: 0}
        nine = {run.MULTI_PHASE_CALL: 0, run.SINGLE_CALL: 449_100}
        self.assertIn("one SimInspiralFDMultiPhase call", run.route_problem("one", nine, 50_000))
        self.assertIn("9 SimInspiralFD calls", run.route_problem("nine", one, 50_000))
        self.assertIsNotNone(run.route_problem("nine", {run.MULTI_PHASE_CALL: 1, run.SINGLE_CALL: 449_100}, 50_000))

    def test_falling_back_for_most_samples_is_a_problem(self):
        calls = {run.MULTI_PHASE_CALL: 49_900, run.SINGLE_CALL: 449_100}
        self.assertIsNotNone(run.route_problem("one", calls, 50_000))

    def test_lal_record_says_what_ran(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory) / "site"
            LS = SimpleNamespace(__file__=str(site / "lalsimulation" / "__init__.py"), __version__="6.2.1", SimInspiralFDMultiPhase=len)
            record = run.lal_record(LS, str(site), "one")
            self.assertEqual(record["version"], "6.2.1")
            self.assertTrue(record["has_multi_phase"])

    def test_lal_record_refuses_another_lal(self):
        with tempfile.TemporaryDirectory() as directory:
            LS = SimpleNamespace(__file__=str(Path(directory) / "image" / "__init__.py"), __version__="6.2.1")
            with self.assertRaisesRegex(ValueError, "not from"):
                run.lal_record(LS, str(Path(directory) / "site"), "nine")

    def test_lal_record_refuses_the_one_call_route_without_the_function(self):
        with tempfile.TemporaryDirectory() as directory:
            LS = SimpleNamespace(__file__=str(Path(directory) / "__init__.py"), __version__="6.2.1")
            with self.assertRaisesRegex(ValueError, "needs SimInspiralFDMultiPhase"):
                run.lal_record(LS, None, "one")
            self.assertFalse(run.lal_record(LS, None, "nine")["has_multi_phase"])


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestCompareTolerances(unittest.TestCase):
    def test_an_absolute_tolerance_lets_a_column_through_zero_pass(self):
        near_zero = compare.column_differences([1e-5, 1.0], [1e-5 + 1e-12, 1.0])
        self.assertGreater(near_zero["max_rel"], 1e-9)
        self.assertFalse(compare.agrees(near_zero, 1e-9))
        self.assertTrue(compare.agrees(near_zero, 1e-9, 1e-7))

    def test_zero_tolerances_mean_bit_for_bit(self):
        self.assertTrue(compare.agrees(compare.column_differences([1.0, 2.0], [1.0, 2.0]), 0.0, 0.0))
        self.assertFalse(compare.agrees(compare.column_differences([1.0, 2.0], [1.0, 2.0 + 1e-15]), 0.0, 0.0))

    def test_no_tolerance_excuses_a_non_finite_mismatch(self):
        self.assertFalse(compare.agrees(compare.column_differences([1.0, -np.inf], [1.0, 0.0]), 1.0, 1.0))


class TestJobs(unittest.TestCase):
    def tasks(self, job, kind):
        manifest = jobs.manifest(job, inputs_at(), jobs.JOB_SCALE)
        return [task for task in manifest["tasks"] if task["kind"] == kind]

    def test_the_ladders_run_the_same_setups_in_opposite_orders(self):
        forward = [task["name"] for task in self.tasks("ladder_forward", "importance_sampling")]
        backward = [task["name"] for task in self.tasks("ladder_reverse", "importance_sampling")]
        self.assertEqual(forward, list(reversed(backward)))
        self.assertEqual(len(forward), 6)

    def test_the_ladder_uses_the_right_dingo_lal_and_route(self):
        setups = {task["name"]: task for task in self.tasks("ladder_forward", "importance_sampling")}
        self.assertEqual(setups["upstream_release"]["commit"], COMMITS["upstream"])
        self.assertFalse(setups["upstream_release"]["lal"])
        self.assertEqual(setups["pr454_release"]["commit"], COMMITS["pr454"])
        self.assertFalse(setups["pr454_release"]["lal"])
        self.assertEqual(setups["combined_patched_nine"]["commit"], COMMITS["combined"])
        self.assertTrue(setups["combined_patched_nine"]["lal"])
        self.assertEqual(setups["combined_patched_nine"]["route"], "nine")
        self.assertEqual(setups["combined_patched_one"]["route"], "one")
        self.assertEqual(setups["branch_patched_one"]["commit"], COMMITS["branch"])
        self.assertTrue(setups["branch_patched_one"]["lal"])

    def test_every_setup_of_a_ladder_starts_from_the_same_samples_and_seed(self):
        setups = self.tasks("ladder_forward", "importance_sampling")
        self.assertEqual({task["proposal"] for task in setups}, {"network_samples.hdf5"})
        self.assertEqual({task["seed"] for task in setups}, {1})
        self.assertEqual({task["num_processes"] for task in setups}, {32})

    def test_what_must_agree_and_how_closely(self):
        comparisons = {(task["first"], task["second"]): task for task in self.tasks("ladder_forward", "compare")}

        def tolerances(pair):
            return comparisons[pair]["rtol"], comparisons[pair]["atol"]

        # Bit for bit only where the code path and array shapes are the same: The branch on the release LAL.
        self.assertEqual(tolerances(("pr454_release", "combined_release")), (0.0, 0.0))
        for pair in (("upstream_release", "pr454_release"), ("combined_patched_nine", "combined_patched_one"), ("combined_patched_one", "branch_patched_one")):
            self.assertEqual(tolerances(pair), jobs.ROUND_OFF, pair)
        for pair in comparisons:
            self.assertEqual(comparisons[pair]["must_pass"], pair != ("upstream_release", "combined_patched_nine"), pair)

    def test_compared_tasks_exist_and_come_first(self):
        for job in ("ladder_forward", "ladder_reverse", "full"):
            names = []
            for task in jobs.manifest(job, inputs_at(), jobs.JOB_SCALE)["tasks"]:
                if task["kind"] == "compare":
                    self.assertIn(task["first"], names)
                    self.assertIn(task["second"], names)
                names.append(task["name"])

    def test_the_full_job_draws_from_the_network(self):
        setups = self.tasks("full", "importance_sampling")
        self.assertEqual({task["model"] for task in setups}, {"model_nonlensed.pt"})
        self.assertFalse([task for task in setups if "proposal" in task])
        self.assertEqual([task["route"] for task in setups], ["nine", "one"])

    def test_a_job_has_the_files_where_the_preflight_keeps_the_data_in_place(self):
        job = jobs.manifest("ladder_forward", inputs_at(), jobs.JOB_SCALE)["tasks"][0]
        preflight = jobs.manifest("ladder_forward", inputs_at(), jobs.PREFLIGHT_SCALE, preflight=True)["tasks"][0]
        self.assertEqual(job["proposal"], "network_samples.hdf5")
        self.assertEqual(preflight["proposal"], "/data/runs/network_samples.hdf5")
        self.assertEqual(preflight["event_data"], "/data/event/event_data.hdf5")
        self.assertEqual(job["tarball"], preflight["tarball"])
        self.assertEqual((job["num_samples"], preflight["num_samples"]), (50_000, 500))

    def test_the_suite_only_has_to_pass_in_the_preflight(self):
        job = self.tasks("suite_patched", "suite")[0]
        self.assertFalse(job["must_pass"])
        self.assertEqual(job["pytest_args"], [])
        self.assertTrue(job["lal"])
        self.assertFalse(self.tasks("suite_release", "suite")[0]["lal"])
        preflight = jobs.manifest("suite_patched", inputs_at(), jobs.PREFLIGHT_SCALE, preflight=True)["tasks"][0]
        self.assertTrue(preflight["must_pass"])
        self.assertEqual(preflight["pytest_args"], ["tests/gw/waveform_generator/test_wfg_m.py"])

    def test_a_job_is_sent_only_what_it_uses(self):
        def inputs_of(job):
            manifest = jobs.manifest(job, inputs_at(), jobs.JOB_SCALE)
            return {Path(path).name for path in jobs.needed_inputs(manifest, inputs_at())}

        ladder = inputs_of("ladder_forward")
        self.assertEqual(len([name for name in ladder if name.startswith("dingo_")]), 4)
        self.assertIn("lal_e21ec9674d.tar.gz", ladder)
        self.assertIn("network_samples.hdf5", ladder)
        self.assertNotIn("model_nonlensed.pt", ladder)
        full = inputs_of("full")
        self.assertIn("model_nonlensed.pt", full)
        self.assertNotIn("network_samples.hdf5", full)
        self.assertNotIn("dingo_bbbbbbbbbb.tar.gz", full)
        self.assertNotIn("dingo_dddddddddd.tar.gz", full)
        self.assertEqual(inputs_of("stress"), {"lal_e21ec9674d.tar.gz"})
        self.assertEqual(inputs_of("suite_release"), {"dingo_cccccccccc.tar.gz"})
        self.assertEqual(inputs_of("suite_patched"), {"dingo_cccccccccc.tar.gz", "lal_e21ec9674d.tar.gz"})

    def test_the_submit_file_is_set_up_as_the_2_1_job(self):
        inputs = inputs_at()
        text = jobs.submit_text("full", jobs.manifest("full", inputs, jobs.JOB_SCALE), inputs)
        for line in (
            "executable = /opt/dingo_env/bin/python",
            'arguments = "-I xphm_job.py manifest.json"',
            'MY.SingularityImage = "./image.sif"',
            "transfer_output_files = out",
            "use_oauth_services = scitokens",
            'environment = "OMP_NUM_THREADS=1"',
            "request_cpus = 32",
            "request_memory = 48GB",
            "log = job.log"
        ):
            self.assertIn(line + "\n", text)
        files = next(line for line in text.splitlines() if line.startswith("transfer_input_files"))
        self.assertIn("osdf:///igwn/cit/staging/me/containers/image.sif", files)
        self.assertIn("/runs/x/full/manifest.json", files)
        for script in jobs.SCRIPTS:
            self.assertIn(f"/runs/x/scripts/{script}", files)

    def test_the_stress_test_stops_itself_below_its_memory_request(self):
        job = self.tasks("stress", "stress")[0]
        self.assertEqual((job["memory_limit_gb"], job["max_tasks_per_worker"]), (42.0, 10))
        self.assertLess(job["memory_limit_gb"], jobs.RESOURCES["stress"].memory_gb)
        self.assertEqual(job["environment"], {"MALLOC_MMAP_THRESHOLD_": "131072"})
        self.assertEqual(job["num_processes"], jobs.RESOURCES["stress"].cpus)
        inputs = inputs_at()
        text = jobs.submit_text("stress", jobs.manifest("stress", inputs, jobs.JOB_SCALE), inputs)
        self.assertIn("request_memory = 48GB\n", text)
        self.assertIn("request_cpus = 16\n", text)
        preflight = jobs.manifest("stress", inputs, jobs.PREFLIGHT_SCALE, preflight=True)["tasks"][0]
        self.assertEqual((preflight["memory_limit_gb"], preflight["max_tasks_per_worker"], preflight["num_processes"]), (0.0, 1, 4))

    def test_the_suite_gets_its_cores_as_threads(self):
        inputs = inputs_at()
        text = jobs.submit_text("suite_patched", jobs.manifest("suite_patched", inputs, jobs.JOB_SCALE), inputs)
        self.assertIn('environment = "OMP_NUM_THREADS=8"\n', text)
        self.assertIn("request_cpus = 8\n", text)

    def test_every_job_has_resources_and_every_preflight_a_job(self):
        self.assertEqual(set(jobs.JOBS), set(jobs.RESOURCES))
        self.assertLessEqual(set(jobs.PREFLIGHT_JOBS), set(jobs.JOBS))

    def test_the_launcher_copies_every_script_a_job_is_sent(self):
        for launcher in ("launch_xphm_tests.sh", "resubmit_xphm_job.sh"):
            text = (LAL / launcher).read_text(encoding="utf-8")
            for script in jobs.SCRIPTS:
                self.assertIn(f"/{script}", text, launcher)

    def test_every_script_a_job_is_sent_exists(self):
        for script in jobs.SCRIPTS:
            self.assertTrue(driver.find_script(script).is_file(), script)

    def test_refuses_a_short_commit(self):
        inputs = inputs_at()
        inputs.combined_commit = "c" * 10
        with self.assertRaisesRegex(ValueError, "combined_commit"):
            inputs.check()

    def test_refuses_a_relative_path(self):
        inputs = inputs_at()
        inputs.proposal = "samples.hdf5"
        with self.assertRaisesRegex(ValueError, "proposal"):
            inputs.check()

    def test_refuses_a_path_condor_would_split(self):
        inputs = inputs_at()
        inputs.model = "/data/a,b.pt"
        with self.assertRaisesRegex(ValueError, "commas"):
            inputs.check()

    def test_refuses_an_image_not_on_osdf(self):
        inputs = inputs_at()
        inputs.image_url = "/data/image.sif"
        with self.assertRaisesRegex(ValueError, "osdf"):
            inputs.check()


class TestRewrite(TempCase):
    def make_run(self):
        run_dir = self.base / "run"
        launch = {
            "upstream": COMMITS["upstream"],
            "pr454": COMMITS["pr454"],
            "branch": COMMITS["branch"],
            "combined": COMMITS["combined"],
            "lal_tarball": (run_dir / "lal_e21ec9674d.tar.gz").as_posix(),
            "image_url": "osdf:///igwn/cit/staging/me/containers/image.sif",
            "proposal": "/data/runs/network_samples.hdf5",
            "model": "/data/models/model_nonlensed.pt",
            "event_data": "/data/event/event_data.hdf5",
            "priority": 50
        }
        write(run_dir / "launch.json", json.dumps(launch))
        return run_dir

    def test_writes_one_job_again_from_the_launch(self):
        run_dir = self.make_run()
        with mock.patch.object(jobs.Inputs, "check"):
            jobs.rewrite_job(run_dir, "stress")
        manifest = json.loads((run_dir / "stress" / "manifest.json").read_text(encoding="utf-8"))
        inputs = jobs.inputs_from_run(run_dir)
        self.assertEqual(manifest, jobs.manifest("stress", inputs, jobs.JOB_SCALE))
        self.assertEqual(manifest["tasks"][0]["memory_limit_gb"], 42.0)
        self.assertIn("request_memory = 48GB\n", (run_dir / "stress" / "job.sub").read_text(encoding="utf-8"))
        self.assertEqual(inputs.combined_tarball, (run_dir / "dingo_cccccccccc.tar.gz").as_posix())
        self.assertFalse((run_dir / "full").exists())

    def test_refuses_an_unknown_job(self):
        run_dir = self.make_run()
        with self.assertRaisesRegex(ValueError, "Unknown job"):
            jobs.rewrite_job(run_dir, "ladder_sideways")


class TestTaskVerdicts(unittest.TestCase):
    def test_verdicts_by_exit_code(self):
        self.assertEqual(driver.task_verdict("compare", 0), "passed")
        self.assertEqual(driver.task_verdict("compare", 1), "disagrees")
        self.assertEqual(driver.task_verdict("compare", 2), "failed")
        self.assertEqual(driver.task_verdict("stress", 3), "disagrees")
        self.assertEqual(driver.task_verdict("stress", 1), "failed")
        self.assertEqual(driver.task_verdict("importance_sampling", 1), "failed")
        self.assertEqual(driver.task_verdict("importance_sampling", -11), "failed")

    def test_exit_code_of_a_job(self):
        def record(verdict, must_pass=True):
            return {"verdict": verdict, "must_pass": must_pass}

        self.assertEqual(driver.job_exit_code([record("passed"), record("failed", False)]), 0)
        self.assertEqual(driver.job_exit_code([record("passed"), record("disagrees")]), 3)
        self.assertEqual(driver.job_exit_code([record("disagrees"), record("failed")]), 1)
        self.assertEqual(driver.job_exit_code([record("skipped")]), 1)


FAKE_BASELINE_RUN = """\
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
def value(key):
    return args[args.index(key) + 1] if key in args else None

Path("out").mkdir(exist_ok=True)
name = Path.cwd().name
one = value("--route") == "one"
samples = int(value("--num-samples"))
per_sample = 70.0 if one else 180.0
report = {
    "args": args,
    "library_path": os.environ.get("LD_LIBRARY_PATH"),
    "malloc_mmap_threshold": os.environ.get("MALLOC_MMAP_THRESHOLD_"),
    "stages": {"synthetic_phase": {"seconds": per_sample + 14.0, "main_peak_bytes": 5000000000}},
    "synthetic_phase_parts": {
        "per_sample_terms_in_workers": {"found": True, "seconds": per_sample},
        "grid_and_floor_in_workers": {"found": True, "seconds": 7.0},
        "draws": {"found": True, "seconds": 7.0}
    },
    "evidence": {"log_evidence": -5829.6248, "n_eff": 11027.6},
    "route": {"calls": {"SimInspiralFD": 0 if one else 9 * samples, "SimInspiralFDMultiPhase": samples if one else 0}},
    "total_seconds": 100.0 + per_sample,
    "children_peak_bytes": 600000000,
    "provenance": {"host": {"cpu": {"model": "Test CPU"}}}
}
if os.environ.get("FAKE_CRASH") == name:
    report["error"] = "ValueError: broken"
    Path("out/baseline.json").write_text(json.dumps(report))
    sys.exit(1)
Path("out/baseline.json").write_text(json.dumps(report))
Path("out/importance_sampling.hdf5").write_text("results")
"""

FAKE_COMPARE = """\
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
def value(key):
    return args[args.index(key) + 1]

agrees = os.environ.get("FAKE_DISAGREE") is None or float(value("--rtol")) == 0.0
report = {
    "identical_to_rtol": agrees,
    "rtol": float(value("--rtol")),
    "atol": float(value("--atol")),
    "columns": {"phase": {"max_abs": 1e-11, "max_rel": 2e-10, "nonfinite": 0, "nonfinite_mismatch": 0}},
    "summary": {"log_evidence": [-5829.6248, -5829.6249]}
}
Path(value("--output")).write_text(json.dumps(report))
sys.exit(0 if agrees else 1)
"""

FAKE_RUN_SUITE = """\
import os, sys
from pathlib import Path

args = sys.argv[1:]
patched = "--lal-site" in args
needs_patch = '<testcase classname="tests.gw.waveform_generator.test_wfg_m" name="test_lalsimulation_multi_phase_matches_repeated_calls[IMRPhenomXPHM]">{}</testcase>'
Path(args[args.index("--junit") + 1]).write_text(f'''<testsuites><testsuite>
<testcase classname="tests.core.test_compile.TestResetGraphsOnRequiresGradChange" name="test_unfreeze_without_reset_gives_no_gradient"><failure message="x"/></testcase>
<testcase classname="tests.gw.waveform_generator.test_wfg_tidal" name="test_tidal_prior_defaults"><failure message="x"/></testcase>
<testcase classname="tests.gw.test_other" name="test_fine"></testcase>
{needs_patch.format("" if patched else '<skipped message="x"/>')}
{'<testcase classname="tests.gw.test_other" name="test_new_failure"><failure message="x"/></testcase>' if patched and os.environ.get("FAKE_SUITE_FAILS") else ""}
</testsuite></testsuites>''')
sys.exit(0 if any(arg.endswith("test_wfg_m.py") for arg in args) else 1)  # the pre-flight's subset passes
"""

FAKE_STRESS = """\
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
failures = int(os.environ.get("FAKE_STRESS_FAILURES", "0"))
report = {
    "args": args,
    "malloc_mmap_threshold": os.environ.get("MALLOC_MMAP_THRESHOLD_"),
    "seconds": 100.0,
    "failures": failures,
    "chunks": 10,
    "chunks_missing": [],
    "stalled": False,
    "library_path": os.environ.get("LD_LIBRARY_PATH"),
    "kinds": {"dingo": {"draws": 1000, "outcomes": {"within_rtol": 1000}, "max_difference": 1e-14, "speedup_of_sums": 7.3}}
}
Path(args[args.index("--output") + 1]).write_text(json.dumps(report))
sys.exit(3 if failures else 0)
"""


class TestDryRun(TempCase):
    """The chain on the real manifests, job script and collection, with stand-in scripts."""

    def make_run(self):
        run_dir = self.base / "run"
        inputs = inputs_at(run_dir.as_posix())
        with mock.patch.object(jobs.Inputs, "check"):
            written = jobs.write_jobs(inputs)
        self.assertEqual(written["jobs"], list(jobs.JOBS))
        (run_dir / "scripts").mkdir()
        shutil.copy2(LAL / "xphm_job.py", run_dir / "scripts")
        scripts = {
            "baseline_run.py": FAKE_BASELINE_RUN,
            "compare_results.py": FAKE_COMPARE,
            "run_suite.py": FAKE_RUN_SUITE,
            "stress_multiphase.py": FAKE_STRESS
        }
        for script, text in scripts.items():
            write(run_dir / "scripts" / script, text)
        for commit in ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "dddddddddd"):
            self.tarball(run_dir, f"dingo_{commit}", {"COMMIT.json": "{}"})
        self.tarball(run_dir, "lal_e21ec9674d", {"python/lal/__init__.py": "", "lib/liblal.so.20": "library"})
        write(run_dir / "network_samples.hdf5", "samples")
        write(run_dir / "model_nonlensed.pt", "model")
        write(run_dir / "event_data.hdf5", "event")
        return run_dir, inputs

    def tarball(self, folder, top, files):
        source = self.base / "source" / top
        for name, text in files.items():
            write(source / name, text)
        with tarfile.open(folder / f"{top}.tar.gz", "w:gz") as archive:
            archive.add(source, top)

    def run_job(self, run_dir, inputs, job, environment=None):
        """Run the job as Condor would: In a scratch folder of its inputs, with out/ coming back."""
        scratch = self.base / "scratch" / job
        scratch.mkdir(parents=True)
        for script in run_dir.joinpath("scripts").iterdir():
            shutil.copy2(script, scratch)
        manifest = json.loads((run_dir / job / "manifest.json").read_text(encoding="utf-8"))
        for path in jobs.needed_inputs(manifest, inputs):
            shutil.copy2(run_dir / Path(path).name, scratch)
        shutil.copy2(run_dir / job / "manifest.json", scratch)
        finished = subprocess.run(
            [sys.executable, "-I", "xphm_job.py", "manifest.json"],
            cwd=scratch,
            env={**os.environ, **(environment or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        shutil.copytree(scratch / "out", run_dir / job / "out")
        return finished

    def run_all(self, environment=None):
        run_dir, inputs = self.make_run()
        codes = {job: self.run_job(run_dir, inputs, job, environment) for job in jobs.JOBS}
        return run_dir, codes

    def summarise(self, run_dir):
        return collect.summarise(run_dir, self.base / "results", list(jobs.JOBS))

    def test_everything_as_it_should_be_passes(self):
        run_dir, codes = self.run_all()
        for job, finished in codes.items():
            self.assertEqual(finished.returncode, 0, f"{job}: {finished.stdout}")
        summary = self.summarise(run_dir)
        self.assertEqual(summary["problems"], [])
        text = collect.render(summary)
        self.assertTrue(text.rstrip().endswith("PASS"), text)
        self.assertIn("ladder_forward", text)
        self.assertIn("Per injection", text)
        json.dumps(summary)

    def test_the_timings_are_paired_within_a_job(self):
        run_dir, _ = self.run_all()
        tasks = self.summarise(run_dir)["jobs"]["ladder_forward"]["tasks"]
        setup = tasks["combined_patched_one"]["setup"]
        self.assertEqual(setup["synthetic_phase_seconds"], 84.0)
        self.assertEqual(setup["per_sample_seconds"], 70.0)
        self.assertEqual(setup["grid_seconds"], 7.0)
        self.assertAlmostEqual(setup["synthetic_phase_speedup"], 194.0 / 84.0)
        self.assertEqual(setup["multi_phase_calls"], 50_000)
        self.assertEqual(setup["single_calls"], 0)
        self.assertEqual(tasks["upstream_release"]["setup"]["synthetic_phase_speedup"], 1.0)

    def test_the_cost_per_injection_on_the_baseline_s_stages(self):
        run_dir, _ = self.run_all()
        costs = self.summarise(run_dir)["injection_cost_on_2_1"]
        self.assertEqual(set(costs), {"full", "ladder_forward", "ladder_reverse"})
        self.assertAlmostEqual(costs["full"]["speedup"], collect.injection_cost_on_baseline(194.0 / 84.0)["speedup"])
        self.assertIn("Per injection on 2.1's other stages", collect.render(self.summarise(run_dir)))

    def test_the_cost_per_injection_comes_from_the_full_job(self):
        run_dir, _ = self.run_all()
        cost = self.summarise(run_dir)["injection_cost"]
        self.assertAlmostEqual(cost["core_hours_before"], (280.0 + 116) * 32 * 2 / 3600)
        self.assertAlmostEqual(cost["core_hours_after"], (170.0 + 116) * 32 * 2 / 3600)
        self.assertAlmostEqual(cost["speedup"], 396 / 286)

    def test_only_tasks_on_the_patched_lal_get_its_libraries(self):
        run_dir, _ = self.run_all()
        out = run_dir / "ladder_forward" / "out"

        def library_path(task):
            return json.loads((out / task / "baseline.json").read_text(encoding="utf-8"))["library_path"]

        self.assertEqual(Path(library_path("combined_patched_one")).parts[-2:], ("lal_e21ec9674d", "lib"))
        self.assertEqual(library_path("upstream_release"), os.environ.get("LD_LIBRARY_PATH"))
        report = json.loads((run_dir / "stress" / "out" / "stress" / "stress.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(report["library_path"]).parts[-2:], ("lal_e21ec9674d", "lib"))

    def test_only_tasks_on_the_patched_lal_get_its_packages(self):
        run_dir, _ = self.run_all()
        out = run_dir / "ladder_forward" / "out"

        def arguments(task):
            return json.loads((out / task / "baseline.json").read_text(encoding="utf-8"))["args"]

        patched = arguments("combined_patched_one")
        self.assertEqual(Path(patched[patched.index("--lal-site") + 1]).parts[-2:], ("lal_e21ec9674d", "python"))
        self.assertNotIn("--lal-site", arguments("upstream_release"))

    def test_the_results_come_back_with_the_reports(self):
        run_dir, _ = self.run_all()
        self.summarise(run_dir)
        results = self.base / "results" / "ladder_forward"
        self.assertTrue((results / "job.json").is_file())
        self.assertTrue((results / "manifest.json").is_file())
        self.assertTrue((results / "combined_patched_one" / "baseline.json").is_file())
        self.assertTrue((results / "compare_pr454_release_vs_combined_release" / "compare.json").is_file())
        self.assertFalse(list(results.rglob("*.hdf5")))
        self.assertTrue((run_dir / "ladder_forward" / "out" / "combined_patched_one" / "importance_sampling.hdf5").is_file())

    def test_a_crashed_setup_stops_nothing_else_and_is_reported(self):
        run_dir, codes = self.run_all({"FAKE_CRASH": "combined_patched_nine"})
        self.assertEqual(codes["ladder_forward"].returncode, 1)
        self.assertEqual(codes["stress"].returncode, 0)
        report = json.loads((run_dir / "ladder_forward" / "out" / "job.json").read_text(encoding="utf-8"))
        self.assertEqual(report["tasks"]["combined_patched_nine"]["verdict"], "failed")
        self.assertEqual(report["tasks"]["combined_patched_one"]["verdict"], "passed")
        self.assertEqual(report["tasks"]["branch_patched_one"]["verdict"], "passed")
        self.assertEqual(report["tasks"]["compare_combined_patched_nine_vs_combined_patched_one"]["verdict"], "skipped")
        self.assertEqual(report["tasks"]["compare_combined_patched_one_vs_branch_patched_one"]["verdict"], "passed")
        problems = "\n".join(self.summarise(run_dir)["problems"])
        self.assertIn("ladder_forward: combined_patched_nine failed", problems)
        self.assertIn("ladder_reverse: compare_combined_patched_nine_vs_combined_patched_one skipped", problems)

    def test_routes_that_disagree_fail_the_test_but_the_job_finishes(self):
        run_dir, codes = self.run_all({"FAKE_DISAGREE": "1"})
        self.assertEqual(codes["ladder_forward"].returncode, 3)
        self.assertEqual(codes["full"].returncode, 0)  # that comparison is only for scale
        summary = self.summarise(run_dir)
        self.assertIn("compare_combined_patched_nine_vs_combined_patched_one disagrees", "\n".join(summary["problems"]))
        self.assertTrue(collect.render(summary).startswith("End-to-end"))

    def test_the_stress_test_gets_its_memory_settings(self):
        run_dir, _ = self.run_all()
        report = json.loads((run_dir / "stress" / "out" / "stress" / "stress.json").read_text(encoding="utf-8"))
        arguments = report["args"]
        self.assertEqual(arguments[arguments.index("--memory-limit-gb") + 1], "42.0")
        self.assertEqual(arguments[arguments.index("--max-tasks-per-worker") + 1], "10")
        self.assertEqual(arguments[arguments.index("--num-processes") + 1], "16")
        self.assertEqual(report["malloc_mmap_threshold"], "131072")
        setup = json.loads((run_dir / "ladder_forward" / "out" / "upstream_release" / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(setup["malloc_mmap_threshold"], os.environ.get("MALLOC_MMAP_THRESHOLD_"))  # only the stress task gets it

    def test_a_stress_failure_fails_the_test(self):
        run_dir, codes = self.run_all({"FAKE_STRESS_FAILURES": "2"})
        self.assertEqual(codes["stress"].returncode, 3)
        self.assertIn("stress: 2 failures", self.summarise(run_dir)["problems"])

    def test_a_new_suite_failure_on_the_patched_lal_fails_the_test(self):
        run_dir, codes = self.run_all({"FAKE_SUITE_FAILS": "1"})
        self.assertEqual(codes["suite_patched"].returncode, 0)  # the job leaves this to the collection
        problems = "\n".join(self.summarise(run_dir)["problems"])
        self.assertIn("tests.gw.test_other.test_new_failure", problems)

    def test_a_job_that_has_not_finished_is_a_problem_and_the_rest_is_kept(self):
        run_dir, inputs = self.make_run()
        self.run_job(run_dir, inputs, "ladder_forward")
        summary = self.summarise(run_dir)
        self.assertIn("full: Not finished", summary["problems"])
        self.assertIn("suite: No junit report from both LALs", summary["problems"])
        self.assertIn("combined_patched_one", summary["jobs"]["ladder_forward"]["tasks"])
        self.assertIn("NOT PASSED", collect.render(summary))

    def test_the_command_line_writes_the_summary(self):
        run_dir, _ = self.run_all()
        result = run_script(LAL / "collect_xphm_tests.py", [str(run_dir), "--results", str(self.base / "results")], site=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.base / "results" / run_dir.name
        self.assertTrue((destination / "summary.json").is_file())
        self.assertIn("PASS", (destination / "summary.txt").read_text(encoding="utf-8"))

    def test_the_job_keeps_a_report_when_the_manifest_is_broken(self):
        scratch = self.base / "scratch"
        scratch.mkdir()
        shutil.copy2(LAL / "xphm_job.py", scratch)
        write(scratch / "manifest.json", "not json")
        finished = subprocess.run([sys.executable, "-I", "xphm_job.py", "manifest.json"], cwd=scratch, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(finished.returncode, 1)
        self.assertIn("JSONDecodeError", json.loads((scratch / "out" / "job.json").read_text(encoding="utf-8"))["error"])


class TestShowJob(TempCase):
    def test_shows_every_verdict_and_the_end_of_what_failed(self):
        report = {
            "job": "ladder_forward",
            "host": "node1",
            "exit_code": 1,
            "tasks": {
                "upstream_release": {"verdict": "passed", "exit_code": 0, "seconds": 30.0},
                "combined_patched_one": {"verdict": "failed", "exit_code": 1, "seconds": 9.0},
                "compare_a_vs_b": {"verdict": "skipped", "reason": "No result from combined_patched_one"}
            }
        }
        write(self.base / "job.json", json.dumps(report))
        write(self.base / "upstream_release" / "output.txt", "fine\n")
        write(self.base / "combined_patched_one" / "output.txt", "".join(f"line {k}\n" for k in range(50)) + "ValueError: broken\n")
        text = "\n".join(show.describe(self.base, lines=5))
        self.assertIn("ladder_forward on node1: exit 1", text)
        self.assertIn("upstream_release: passed, exit 0", text)
        self.assertIn("compare_a_vs_b: skipped, exit None, None s No result from combined_patched_one", text)
        self.assertIn("ValueError: broken", text)
        self.assertIn("line 49", text)
        self.assertNotIn("line 40", text)
        self.assertNotIn("fine", text)

    def test_a_job_that_never_started(self):
        self.assertIn("did not start", show.describe(self.base)[0])


class TestCollectPieces(TempCase):
    def test_comparison_row_finds_the_worst_columns(self):
        report = {
            "identical_to_rtol": True,
            "rtol": 1e-9,
            "atol": 1e-7,
            "columns": {
                "phase": {"max_abs": 1e-11, "max_rel": 3e-9, "nonfinite": 0, "nonfinite_mismatch": 0},
                "log_likelihood": {"max_abs": 2e-10, "max_rel": 1e-13, "nonfinite": 90, "nonfinite_mismatch": 0}
            },
            "summary": {"log_evidence": [-5829.625, -5829.626]}
        }
        row = collect.comparison_row(report)
        self.assertEqual((row["max_rel_column"], row["max_abs_column"]), ("phase", "log_likelihood"))
        self.assertAlmostEqual(row["log_evidence_difference"], 0.001)

    def test_the_known_failures_are_expected_and_others_are_not(self):
        known = sorted(collect.KNOWN_FAILURES)
        release = {known[0]: "failed", known[1]: "failed", "tests.a.b": "passed"}
        self.assertEqual(collect.suite_comparison(release, dict(release))["unexpected_failures_patched"], [])
        patched = {**release, "tests.a.b": "failed"}
        comparison = collect.suite_comparison(release, patched)
        self.assertEqual(comparison["unexpected_failures_patched"], ["tests.a.b"])
        self.assertEqual(comparison["differing"], {"tests.a.b": ["passed", "failed"]})

    def test_the_test_of_the_patched_lal_must_pass_on_it(self):
        test = next(iter(collect.NEEDS_PATCHED_LAL))
        comparison = collect.suite_comparison({test: "skipped"}, {test: "skipped"})
        job = {"finished": True, "tasks": {}}
        self.assertIn("is skipped on the patched LAL", "\n".join(collect.judge({"suite_patched": job}, comparison)))

    def test_a_stalled_stress_test_is_a_problem(self):
        stress = {"failures": 0, "stalled": True, "chunks_missing": [["wide", 3]]}
        job = {"finished": True, "tasks": {"stress": {"kind": "stress", "verdict": "disagrees", "stress": stress}}}
        self.assertIn("stress: Chunks lost, probably to a crash: [['wide', 3]]", collect.judge({"stress": job}, None))

    def test_the_cost_on_the_baseline_s_stages(self):
        unchanged = collect.injection_cost_on_baseline(1.0)
        self.assertAlmostEqual(unchanged["core_hours_before"], unchanged["core_hours_after"])
        self.assertAlmostEqual(unchanged["core_hours_before"], 7.526, places=3)  # 2.1's measured cost
        faster = collect.injection_cost_on_baseline(2.76)
        self.assertAlmostEqual(faster["core_hours_after"], (307.342 - 222.673 + 222.673 / 2.76 + 116) * 64 / 3600)

    def test_stopping_at_the_memory_limit_is_a_problem(self):
        stress = {"failures": 0, "stalled": False, "stopped_for_memory": True, "peak_total_resident_gb": 41.2}
        job = {"finished": True, "tasks": {"stress": {"kind": "stress", "verdict": "disagrees", "stress": stress}}}
        self.assertEqual(collect.judge({"stress": job}, None), ["stress: Stopped at its memory limit, with 41.2 GB held", "suite: No junit report from both LALs"])

    def test_a_stress_test_that_broke_is_still_a_problem(self):
        job = {"finished": True, "tasks": {"stress": {"kind": "stress", "verdict": "failed", "exit_code": 1}}}
        self.assertIn("stress: stress failed: exit 1", collect.judge({"stress": job}, None))

    def test_stopping_at_the_time_limit_is_not_a_problem(self):
        stress = {"failures": 0, "stalled": False, "chunks_missing": [["wide", 3]], "stopped_at_time_limit": True}
        job = {"finished": True, "tasks": {"stress": {"kind": "stress", "verdict": "passed", "stress": stress}}}
        self.assertEqual([p for p in collect.judge({"stress": job}, None) if p.startswith("stress")], [])


FAKE_LAL = """\
from types import SimpleNamespace
import numpy as np

__version__ = "7.7.1"

def CreateREAL8Vector(length):
    return SimpleNamespace(data=np.zeros(length))

def CreateDict():
    return {}
"""

FAKE_LALSIMULATION = """\
from types import SimpleNamespace
import numpy as np

__version__ = "6.2.1"
IMRPhenomXPHM = 1

def series(phase, scale=1.0):
    data = scale * 1e-23 * np.exp(1j * phase) * np.arange(1.0, 33.0)
    epoch = SimpleNamespace(gpsSeconds=-8, gpsNanoSeconds=0)
    return SimpleNamespace(data=SimpleNamespace(data=data, length=len(data)), epoch=epoch, deltaF=0.125, f0=0.0)

def SimInspiralTransformPrecessingNewInitialConditions(*args):
    return (0.5, 0.1, 0.0, 0.2, 0.0, 0.1, 0.3)

def SimInspiralFD(*args):
    return series(args[10]), series(args[10] + 0.1)

def SimInspiralFDMultiPhase(*args):
    phases = args[10].data
    rows_p = np.array([series(phase, 1 + 1e-15).data.data for phase in phases])
    rows_c = np.array([series(phase + 0.1, 1 + 1e-15).data.data for phase in phases])
    first = series(phases[0], 1 + 1e-15)
    return first, None, SimpleNamespace(data=rows_p), SimpleNamespace(data=rows_c)

def __getattr__(name):
    if name.startswith("SimInspiralWaveformParamsInsert") or name.startswith("SimInspiral"):
        return lambda *args: []
    raise AttributeError(name)
"""


class FakeLal:
    @staticmethod
    def CreateREAL8Vector(length):
        return SimpleNamespace(data=np.zeros(length))

    @staticmethod
    def CreateDict():
        return {}


class FakeLS:
    """Polarisations proportional to exp(i phase), with switches for each way the routes can differ."""

    IMRPhenomXPHM = 1

    def __init__(self, error=1e-15, single_raises=False, multi_raises=False, unstable=(False, False), epoch=-8, conversion_raises=False):
        self.error = error
        self.single_raises = single_raises
        self.multi_raises = multi_raises
        self.unstable = unstable
        self.epoch = epoch
        self.conversion_raises = conversion_raises

    def SimInspiralTransformPrecessingNewInitialConditions(self, *args):
        if self.conversion_raises:
            raise RuntimeError("Input domain error")
        return (0.5, 0.1, 0.0, 0.2, 0.0, 0.1, 0.3)

    @staticmethod
    def series(phase, scale=1.0, epoch=-8, spike=False):
        data = scale * 1e-23 * np.exp(1j * phase) * np.arange(1.0, 33.0)
        if spike:
            data[3] = 1.0
        return SimpleNamespace(
            data=SimpleNamespace(data=data, length=len(data)),
            epoch=SimpleNamespace(gpsSeconds=epoch, gpsNanoSeconds=0),
            deltaF=0.125,
            f0=0.0
        )

    def SimInspiralFD(self, *args):
        if self.single_raises:
            raise RuntimeError("Input domain error")
        return self.series(args[10], spike=self.unstable[0]), self.series(args[10] + 0.1)

    def SimInspiralFDMultiPhase(self, *args):
        if self.multi_raises:
            raise RuntimeError("Input domain error")
        phases = args[10].data
        scale = 1 + self.error
        rows_p = [self.series(phase, scale, spike=self.unstable[1]).data.data for phase in phases]
        rows_c = [self.series(phase + 0.1, scale).data.data for phase in phases]
        first = self.series(phases[0], scale, self.epoch, spike=self.unstable[1])
        return first, None, SimpleNamespace(data=np.array(rows_p)), SimpleNamespace(data=np.array(rows_c))


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestStressDraws(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(1)

    def test_dingo_draws_are_in_the_model_s_ranges_and_on_its_settings(self):
        for _ in range(2000):
            draw = stress.dingo_draw(self.rng)
            self.assertLessEqual(draw["m2"], draw["m1"])
            q = draw["m2"] / draw["m1"]
            self.assertTrue(0.125 <= q <= 1.0)
            chirp_mass = (draw["m1"] * draw["m2"]) ** 0.6 / (draw["m1"] + draw["m2"]) ** 0.2
            self.assertTrue(10.0 <= chirp_mass <= 180.0 + 1e-9, chirp_mass)
            self.assertTrue(0.0 <= draw["a_1"] <= 0.99)
            self.assertTrue(0.0 <= draw["tilt_1"] <= np.pi)
            self.assertEqual((draw["f_min"], draw["f_max"], draw["delta_f"], draw["f_ref"]), (20.0, 448.0, 0.125, 20.0))
            self.assertEqual((draw["num_phases"], draw["dictionary"], draw["long_asc_nodes"]), (9, {}, 0.0))

    def test_wide_draws_reach_the_edges_and_stay_valid(self):
        draws = [stress.wide_draw(self.rng) for _ in range(5000)]
        for draw in draws:
            self.assertLessEqual(draw["m2"], draw["m1"])
            self.assertGreater(draw["m2"], 0.0)
            self.assertTrue(draw["a_1"] < 1.0 and draw["a_2"] < 1.0)
            json.dumps(draw)
        total = [draw["m1"] + draw["m2"] for draw in draws]
        self.assertGreater(max(total), 500.0)  # above which the function hands over to single calls
        self.assertTrue(any(draw["m1"] == draw["m2"] for draw in draws))
        self.assertTrue(any(draw["a_1"] == 0.0 and draw["a_2"] == 0.0 for draw in draws))
        self.assertTrue(any(draw["theta_jn"] == 0.0 for draw in draws))
        self.assertTrue(any(draw["tilt_1"] == np.pi for draw in draws))
        self.assertEqual({draw["f_ref"] for draw in draws} >= {0.0, 50.0}, True)
        self.assertEqual({draw["num_phases"] for draw in draws}, {1, 2, 3, 5, 9, 11})
        self.assertTrue(any(draw["long_asc_nodes"] != 0.0 for draw in draws))
        kinds = {key for draw in draws for key in draw["dictionary"]}
        self.assertEqual(kinds, {"modes", "prec_version", "convention", "prec_threshold", "mode_threshold"})

    def test_a_chunk_is_reproducible_from_its_seed(self):
        first = [stress.wide_draw(np.random.default_rng([1, 1, 7])) for _ in range(2)]
        self.assertEqual(first[0], first[1])

    def test_the_chunks_cover_every_draw_of_both_kinds_in_mixed_order(self):
        chunks = stress.chunk_plan(1000, 120, 1)
        self.assertEqual(sum(draws for kind, _, draws in chunks if kind == "dingo"), 1000)
        self.assertEqual(sum(draws for kind, _, draws in chunks if kind == "wide"), 120)
        self.assertEqual(len({(kind, index) for kind, index, _ in chunks}), len(chunks))
        kinds = [kind for kind, _, _ in chunks]
        self.assertNotEqual(kinds, sorted(kinds))
        self.assertEqual(chunks, stress.chunk_plan(1000, 120, 1))


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestStressOutcomes(unittest.TestCase):
    def outcome(self, **switches):
        draw = stress.dingo_draw(np.random.default_rng(1))
        return stress.evaluate(FakeLal, FakeLS(**switches), draw, 1e-10)

    def test_classify(self):
        cases = [
            (("a", "b", 0.0, False, False, False), "both_raise"),
            (("a", None, 0.0, False, False, False), "one_raises"),
            ((None, "b", 0.0, False, False, False), "one_raises"),
            ((None, None, 1e-15, True, True, False), "unstable_differs"),
            ((None, None, 1.0, False, True, True), "unstable"),
            ((None, None, 1e-15, False, False, False), "series_differs"),
            ((None, None, 1e-5, True, False, False), "over_rtol"),
            ((None, None, 0.0, True, False, False), "exact"),
            ((None, None, 1e-15, True, False, False), "within_rtol")
        ]
        for arguments, expected in cases:
            self.assertEqual(stress.classify(*arguments, 1e-10), expected, arguments)

    def test_agreement_to_round_off(self):
        record = self.outcome()
        self.assertEqual(record["outcome"], "within_rtol")
        self.assertGreater(record["difference"], 0.0)
        self.assertLess(record["difference"], 1e-14)

    def test_a_fallback_agrees_exactly(self):
        self.assertEqual(self.outcome(error=0.0)["outcome"], "exact")

    def test_a_real_difference_fails(self):
        self.assertEqual(self.outcome(error=1e-6)["outcome"], "over_rtol")

    def test_both_refusing_is_fine(self):
        self.assertEqual(self.outcome(single_raises=True, multi_raises=True)["outcome"], "both_raise")

    def test_only_one_refusing_fails(self):
        self.assertEqual(self.outcome(single_raises=True)["outcome"], "one_raises")
        record = self.outcome(multi_raises=True)
        self.assertEqual(record["outcome"], "one_raises")
        self.assertIn("Input domain error", record["multi_error"])

    def test_another_epoch_fails(self):
        self.assertEqual(self.outcome(epoch=-7)["outcome"], "series_differs")

    def test_unstable_for_both_is_left_to_dingo(self):
        self.assertEqual(self.outcome(unstable=(True, True))["outcome"], "unstable")

    def test_unstable_for_one_fails(self):
        self.assertEqual(self.outcome(unstable=(True, False))["outcome"], "unstable_differs")

    def test_parameters_the_spin_conversion_refuses_are_counted_not_fatal(self):
        self.assertEqual(self.outcome(conversion_raises=True)["outcome"], "no_spins")

    def test_tallies_add_up_across_chunks(self):
        first, second = stress.new_tally(), stress.new_tally()
        draw = {"m1": 30.0}
        for difference, tally in ((1e-14, first), (3e-13, second), (2e-11, second)):
            record = {"outcome": "within_rtol", "difference": difference, "single_seconds": 0.02, "multi_seconds": 0.003, "single_error": None, "multi_error": None}
            stress.add_to_tally(tally, draw, record)
        stress.add_to_tally(second, draw, {"outcome": "both_raise", "difference": 0.0, "single_seconds": 5.0, "multi_seconds": 5.0, "single_error": "a", "multi_error": "b"})
        stress.merge_tallies(first, second)
        self.assertEqual(first["draws"], 4)
        self.assertEqual(first["outcomes"], {"within_rtol": 3, "both_raise": 1})
        self.assertEqual(first["max_difference"], 2e-11)
        self.assertEqual(first["difference_decades"], {"-14": 1, "-13": 1, "-11": 1})
        self.assertAlmostEqual(first["single_seconds"], 0.06)
        self.assertEqual(first["worst"][0]["difference"], 2e-11)

    def test_memory_growth_adds_up_apart_from_first_chunks(self):
        first, later = stress.new_tally(), stress.new_tally()
        first.update(memory_first_growth_kb=5000, memory_first_draws=200, worker_peak_mb=300.0)
        later.update(memory_later_growth_kb=40, memory_later_draws=200, worker_peak_mb=320.0)
        stress.merge_tallies(first, later)
        self.assertEqual((first["memory_first_growth_kb"], first["memory_later_growth_kb"]), (5000, 40))
        self.assertEqual(first["memory_later_draws"], 200)
        self.assertEqual(first["worker_peak_mb"], 320.0)

    def test_resident_memory_of_a_process_that_is_not_there(self):
        self.assertIsNone(stress.resident_kb("not-a-process"))

    def test_failures_keep_their_parameters_up_to_a_limit(self):
        tally = stress.new_tally()
        record = {"outcome": "over_rtol", "difference": 1e-5, "single_seconds": 0.0, "multi_seconds": 0.0, "single_error": None, "multi_error": None}
        for k in range(stress.FAILURES_KEPT + 5):
            stress.add_to_tally(tally, {"m1": float(k)}, record)
        self.assertEqual(stress.failure_count(tally), stress.FAILURES_KEPT + 5)
        self.assertEqual(len(tally["failures"]), stress.FAILURES_KEPT)
        self.assertEqual(tally["failures"][0]["draw"], {"m1": 0.0})
        self.assertEqual(len(tally["worst"]), stress.WORST_KEPT)


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestLeakCheck(unittest.TestCase):
    def test_growth_per_call_by_window(self):
        self.assertEqual(leak.growth_per_call([1000, 1400, 1600, 1800], 100), [4.0, 2.0, 2.0])

    def test_only_steady_growth_is_a_leak(self):
        self.assertTrue(leak.leaks([30.0, 2.0, 1.9], 0.5))
        self.assertFalse(leak.leaks([30.0, 0.1, 0.0], 0.5))  # the allocator settling in
        self.assertFalse(leak.leaks([30.0, 2.0, 0.2], 0.5))
        self.assertFalse(leak.leaks([], 0.5))

    def test_measure_reads_the_memory_around_three_windows(self):
        readings = iter([1000, 1100, 1200, 1300])
        calls = []
        result = leak.measure(calls.append, [("a",), ("b",)], 4, resident=lambda: next(readings))
        self.assertEqual(result["kb_per_call"], [25.0, 25.0, 25.0])
        self.assertEqual(len(calls), 1 + 3 * 4)  # a warm-up of a quarter, then the windows

    def test_measure_without_proc_reports_no_growth(self):
        result = leak.measure(lambda arguments: None, [("a",)], 4, resident=lambda: None)
        self.assertNotIn("kb_per_call", result)

    def test_each_route_makes_its_own_calls(self):
        made = []
        LS = SimpleNamespace(
            SimInspiralFD=lambda *args: made.append(("fd", args[10])),
            SimInspiralFDMultiPhase=lambda *args: made.append(("fd_multi", list(args[10].data))),
            SimIMRPhenomXPHM=lambda *args: made.append(("xphm", args[10:])),
            SimIMRPhenomXPHMMultiPhase=lambda *args: made.append(("xphm_multi", args[11:]))
        )
        head = tuple(range(10))
        tail = (0.0, 0.0, 0.0, 0.125, 20.0, 448.0, 20.0, "dictionary", 1)
        for route in leak.ROUTES:
            leak.call_route(FakeLal, LS, route, head, tail, [0.5, 1.5])
        self.assertEqual(made[:2], [("fd", 0.5), ("fd", 1.5)])
        self.assertEqual(made[2], ("fd_multi", [0.5, 1.5]))
        self.assertEqual(made[3], ("xphm", (0.5, 20.0, 448.0, 0.125, 20.0, "dictionary")))
        self.assertEqual(made[5], ("xphm_multi", (20.0, 448.0, 0.125, 20.0, "dictionary")))
        with self.assertRaisesRegex(ValueError, "Unknown route"):
            leak.call_route(FakeLal, LS, "sideways", head, tail, [0.5])


class SerialResults:
    def __init__(self, function, chunks):
        self.function, self.chunks = function, chunks

    def next(self, timeout=None):
        if not self.chunks:
            raise multiprocessing.TimeoutError
        return self.function(self.chunks.pop(0))


class SerialPool:
    """multiprocessing.Pool in this process, losing the first chunk if told to, as a crash would."""

    lose_first = False

    def __init__(self, processes, **options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *details):
        return False

    def terminate(self):
        pass

    def imap_unordered(self, function, chunks):
        return SerialResults(function, list(chunks)[1 if self.lose_first else 0:])


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestStressRun(TempCase):
    def run_stress(self, *arguments, lose_first=False):
        site = self.base / "site"
        write(site / "lal" / "__init__.py", FAKE_LAL)
        write(site / "lalsimulation" / "__init__.py", FAKE_LALSIMULATION)
        output = self.base / "stress.json"
        path, environment = list(sys.path), dict(os.environ)

        def restore():
            sys.path[:] = path
            os.environ.clear()
            os.environ.update(environment)
            sys.modules.pop("lal", None)
            sys.modules.pop("lalsimulation", None)

        self.addCleanup(restore)
        SerialPool.lose_first = lose_first
        with mock.patch.object(stress.multiprocessing, "Pool", SerialPool):
            code = stress.main(["--lal-site", str(site), "--output", str(output), *arguments])
        return code, json.loads(output.read_text(encoding="utf-8"))

    def test_a_run_that_agrees(self):
        code, report = self.run_stress("--dingo-draws", "400", "--wide-draws", "75", "--num-processes", "1")
        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])
        self.assertEqual(report["kinds"]["dingo"]["draws"], 400)
        self.assertEqual(report["kinds"]["wide"]["draws"], 75)
        self.assertEqual(report["kinds"]["dingo"]["outcomes"], {"within_rtol": 400})
        self.assertEqual(report["chunks_missing"], [])
        self.assertGreater(report["kinds"]["dingo"]["speedup_of_sums"], 0.0)
        self.assertEqual(os.environ["LAL_DEBUG_LEVEL"], "0")

    def test_a_lost_chunk_is_a_failed_run(self):
        code, report = self.run_stress("--dingo-draws", "400", "--wide-draws", "0", "--stall-minutes", "0.002", lose_first=True)
        self.assertEqual(code, 3)
        self.assertTrue(report["stalled"])
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["chunks_missing"]), 1)

    def test_the_time_limit_stops_a_run_without_failing_it(self):
        code, report = self.run_stress("--dingo-draws", "400", "--wide-draws", "0", "--max-minutes", "0")
        self.assertEqual(code, 0)
        self.assertTrue(report["stopped_at_time_limit"])
        self.assertTrue(report["ok"])

    def test_the_memory_limit_stops_a_run_with_its_report(self):
        with mock.patch.object(stress, "total_resident_gb", return_value=99.0):
            code, report = self.run_stress("--dingo-draws", "400", "--wide-draws", "0", "--memory-limit-gb", "40")
        self.assertEqual(code, 3)
        self.assertTrue(report["stopped_for_memory"])
        self.assertFalse(report["stopped_at_time_limit"])
        self.assertEqual(report["peak_total_resident_gb"], 99.0)
        self.assertFalse(report["ok"])

    def test_a_lal_without_the_function_is_refused(self):
        site = self.base / "other"
        write(site / "lal" / "__init__.py", FAKE_LAL)
        write(site / "lalsimulation" / "__init__.py", "__version__ = '6.2.1'\n")
        result = run_script(LAL / "stress_multiphase.py", ["--lal-site", str(site), "--output", str(self.base / "x.json")], site=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("LAL FAILED", result.stderr)


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestRunSuite(TempCase):
    def run_suite(self, body: str, commit: str = "fedcba9876543210"):
        site = self.base / "site"
        write(site / "lal" / "__init__.py", "__version__ = '0'\n")
        write(site / "lalsimulation" / "__init__.py", body)
        tree = make_tree(self.base / "src")
        arguments = ["--tree", str(tree), "--commit", commit, "--lal-site", str(site), "--junit", str(self.base / "junit.xml")]
        return run_script(LAL / "run_suite.py", arguments, site=True)

    def test_a_lal_without_the_function_exits_2(self):
        result = self.run_suite("__version__ = '0'\n")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("LAL FAILED", result.stderr)

    def test_then_the_guard_still_refuses_a_wrong_commit(self):
        body = "SimInspiralFDMultiPhase = NRSur7dq2 = NRSur7dq4 = SimInspiralChooseTDModes = 0\n"
        result = self.run_suite(body)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("GUARD FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main()
