"""Unit tests for the launch checks: check_workflow.py and check_frames.py's helpers.

check_workflow is tested on workflows written here the way pycondor 0.6.1 and
bilby_pipe 1.8.0 (with DINGO 0.9.8's job classes) write them in osg mode with a
container: First a good one, then one change at a time that must stop a launch.
Standard library only, so these run wherever the other unit tests do.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

OPTION_A = Path(__file__).resolve().parent.parent / "option_a"
sys.path.insert(0, str(OPTION_A))

import check_frames  # noqa: E402
import check_workflow  # noqa: E402
from check_frames import covers, gwf_library  # noqa: E402
from check_workflow import (  # noqa: E402
    disk_gb,
    last_value,
    read_submit_file,
    requirements_override,
    transfer_inputs,
)

IMAGE_NAME = "dingo-lensing_test_cpu.sif"
IMAGE_URL = f"osdf:///igwn/cit/staging/someone/containers/{IMAGE_NAME}"
OVERRIDE = "(HAS_SINGULARITY=?=True)"
# What osg mode makes DINGO and bilby_pipe write for sampling and importance sampling.
GLIDEIN = "IS_GLIDEIN=?=True && (HAS_SINGULARITY=?=True)"
EXECUTABLES = {
    "generation": "dingo_lensing_pipe_generation",
    "sampling": "dingo_lensing_pipe_sampling",
    "importance sampling": "dingo_lensing_pipe_importance_sampling",
    "plot": "dingo_pipe_plot",
}
GiB = 1024**3


class Workflow:
    """A run folder with a config and the workflow dingo_lensing_pipe builds from it."""

    def __init__(self, root: Path, events: int = 1, psd_files: bool = True, gps_file: bool = False):
        self.run_dir = root / "run"
        self.osdf = root / "osdf"
        self.events = events
        self.image = self.osdf / IMAGE_URL[len("osdf:///"):]
        self.model = (root / "home" / "model.pt").as_posix()
        self.frames = ["gwosc/H1.gwf", "gwosc/L1.gwf"]
        self.psds = [(root / "home" / f"{ifo}_psd.txt").as_posix() for ifo in ("H1", "L1")]
        self.gps_file = "T_gps.txt" if gps_file else None
        for path in [self.image, Path(self.model), *(self.run_dir / f for f in self.frames), *map(Path, self.psds)]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\0" * 1000)

        event = f"gps-file = {self.gps_file}" if gps_file else "trigger-time = 1000.0"
        psd_dict = f"{{'H1': '{self.psds[0]}', 'L1': '{self.psds[1]}'}}" if psd_files else "None"
        if not psd_files:
            self.psds = []
        (self.run_dir / "T.ini").write_text(
            "label = T\n"
            "outdir = T\n"
            f"container = {IMAGE_URL}\n"
            "conda-env = /opt/dingo_env\n"
            "osg = True\n"
            f"extra-lines = [requirements = {OVERRIDE}]\n"
            f"model = {self.model}\n"
            f"data-dict = {{'H1': '{self.frames[0]}', 'L1': '{self.frames[1]}'}}\n"
            f"psd-dict = {psd_dict}\n"
            f"{event}\n"
        )
        if gps_file:
            (self.run_dir / self.gps_file).write_text("994.0\n" * events)

        self.submit_dir = self.run_dir / "T" / "submit"
        self.jobs = {}
        for idx in range(events):
            for kind in EXECUTABLES:
                self.jobs[(kind, idx)] = self.submit_lines(kind, idx)

    def name(self, kind, idx):
        return f"T_data{idx}_1000-0_{kind.replace(' ', '_')}"

    def submit_lines(self, kind, idx):
        ini = (self.run_dir / "T" / "T_config_complete.ini").as_posix()
        data_file = f"T/data/T_data{idx}_1000-0_generation_data_dump.hdf5"
        transfer = {
            "generation": [ini]
            + ([(self.run_dir / self.gps_file).as_posix()] if self.gps_file else [])
            + [self.model, IMAGE_URL, *self.psds, *self.frames],
            "sampling": [data_file, ini, self.model, IMAGE_URL],
            "importance sampling": [f"T/result/T_data{idx}_1000-0_sampling.hdf5", data_file, ini, IMAGE_URL],
            "plot": [f"T/result/T_data{idx}_1000-0_importance_sampling.hdf5", IMAGE_URL],
        }[kind]
        generated = GLIDEIN if kind in ("sampling", "importance sampling") else OVERRIDE
        log = (self.run_dir / "T" / "log" / self.name(kind, idx)).as_posix()
        return [
            "universe = vanilla",
            f"executable = /opt/dingo_env/bin/{EXECUTABLES[kind]}",
            "request_memory = 8GB",
            "request_disk = 5.0GB",
            "request_cpus = 1",
            f"initialdir = {self.run_dir.as_posix()}",
            "notification = Never",
            f"requirements = {generated}",
            f"requirements = {OVERRIDE}",
            f"log = {log}.log",
            f"output = {log}.out",
            f"error = {log}.err",
            "accounting_group = ligo.dev.o4.cbc.explore.test",
            "priority = 0",
            'environment = "HDF5_USE_FILE_LOCKING=FAlSE OMP_NUM_THREADS=1 OMP_PROC_BIND=false"',
            "MY.flock_local = True",
            f'MY.SingularityImage = "./{IMAGE_NAME}"',
            "transfer_executable = False",
            "should_transfer_files = YES",
            f"transfer_input_files = {','.join(transfer)}",
            "transfer_output_files = T",
            "when_to_transfer_output = ON_EXIT_OR_EVICT",
            "preserve_relative_paths = True",
            "use_oauth_services = scitokens",
            "arguments = $(ARGS)",
            "queue",
        ]

    def set_line(self, kind, key, line, idx=0):
        """Replace a job's last line starting with key; line=None removes it."""
        lines = self.jobs[(kind, idx)]
        where = max(i for i, text in enumerate(lines) if text.startswith(key))
        if line is None:
            del lines[where]
        else:
            lines[where] = line

    def transfer(self, kind, idx=0):
        return transfer_inputs(read_submit_file_from_lines(self.jobs[(kind, idx)]))

    def write(self, absolute_paths=False):
        self.submit_dir.mkdir(parents=True, exist_ok=True)
        dag = ["# BEGIN META", "# END META", "# BEGIN NODES AND EDGES"]
        for (kind, idx), lines in self.jobs.items():
            name = self.name(kind, idx)
            submit = self.submit_dir / f"{name}.submit"
            submit.write_text("\n".join(lines) + "\n")
            # pycondor names submit files relative to the run folder, as bilby_pipe's outdir is.
            listed = submit.as_posix() if absolute_paths else f"T/submit/{name}.submit"
            dag += [f"JOB {name}_arg_0 {listed}", f'VARS {name}_arg_0 ARGS="--label {name}"']
        dag.append("# END NODES AND EDGES")
        (self.submit_dir / "dag_T.submit").write_text("\n".join(dag) + "\n")

    def check(self, events=None, write=True):
        if write:
            self.write()
        return check_workflow.check_workflow(
            self.run_dir, "T.ini", self.events if events is None else events, osdf_root=self.osdf.as_posix()
        )


def read_submit_file_from_lines(lines):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "job.submit"
        path.write_text("\n".join(lines))
        return read_submit_file(path)


class TestCheckWorkflow(unittest.TestCase):
    def workflow(self, **kwargs) -> Workflow:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Workflow(Path(directory.name), **kwargs)

    def assertCaught(self, workflow, expected, events=None, write=True):
        problems, _ = workflow.check(events, write=write)
        self.assertTrue(problems, "The check let a bad workflow through")
        self.assertTrue(
            any(expected in problem for problem in problems),
            f"No problem mentions {expected!r}: {problems}",
        )

    def test_a_good_single_event_workflow_passes(self):
        problems, counts = self.workflow().check()
        self.assertEqual(problems, [])
        self.assertEqual(counts, dict.fromkeys(EXECUTABLES, 1))

    def test_submit_files_listed_with_absolute_paths_are_found_too(self):
        workflow = self.workflow()
        workflow.write(absolute_paths=True)
        problems, counts = workflow.check(write=False)
        self.assertEqual(problems, [])
        self.assertEqual(counts, dict.fromkeys(EXECUTABLES, 1))

    def test_a_good_multi_event_workflow_with_a_gps_file_passes(self):
        problems, counts = self.workflow(events=3, gps_file=True, psd_files=False).check()
        self.assertEqual(problems, [])
        self.assertEqual(counts, dict.fromkeys(EXECUTABLES, 3))

    def test_an_executable_outside_the_image(self):
        workflow = self.workflow()
        workflow.set_line(
            "generation",
            "executable",
            "executable = /home/someone/.conda/envs/dingo_env/bin/dingo_lensing_pipe_generation",
        )
        self.assertCaught(workflow, "is not the image's")

    def test_an_unexpected_executable(self):
        workflow = self.workflow()
        workflow.set_line("generation", "executable", "executable = /opt/dingo_env/bin/bilby_pipe_generation")
        self.assertCaught(workflow, "Unexpected executable")
        self.assertCaught(workflow, "0 generation job(s), expected 1")

    def test_a_job_not_run_inside_the_image(self):
        workflow = self.workflow()
        workflow.set_line("plot", "MY.SingularityImage", None)
        self.assertCaught(workflow, "Not run inside the image")

    def test_a_job_run_inside_another_image(self):
        workflow = self.workflow()
        workflow.set_line("plot", "MY.SingularityImage", 'MY.SingularityImage = "./other.sif"')
        self.assertCaught(workflow, "Not run inside the image")

    def test_the_image_not_sent_with_a_job(self):
        # DINGO's sampling job without osg mode: The image is named but not sent.
        workflow = self.workflow()
        items = [item for item in workflow.transfer("sampling") if item != IMAGE_URL]
        workflow.set_line("sampling", "transfer_input_files", f"transfer_input_files = {','.join(items)}")
        self.assertCaught(workflow, "is not among the files sent")

    def test_the_executable_transferred_instead_of_used_from_the_image(self):
        workflow = self.workflow()
        workflow.set_line("generation", "transfer_executable", "transfer_executable = True")
        self.assertCaught(workflow, "transfer_executable")

    def test_the_vault_token_instead_of_the_access_points(self):
        workflow = self.workflow()
        workflow.set_line("importance sampling", "use_oauth_services", "use_oauth_services = igwn")
        self.assertCaught(workflow, "not scitokens")

    def test_no_token_at_all(self):
        workflow = self.workflow()
        workflow.set_line("plot", "use_oauth_services", None)
        self.assertCaught(workflow, "not scitokens")

    def test_the_glidein_requirement_left_in_place(self):
        # Without the override, sampling would wait for remote-pool slots.
        workflow = self.workflow()
        workflow.set_line("sampling", f"requirements = {OVERRIDE}", None)
        self.assertCaught(workflow, f"Final requirements are '{GLIDEIN}'")

    def test_a_requirement_added_after_the_override(self):
        workflow = self.workflow()
        workflow.jobs[("generation", 0)].insert(-2, "requirements = (TARGET.EPNFS =?= True)")
        self.assertCaught(workflow, "Final requirements")

    def test_a_file_fetched_with_the_vault_token_prefix(self):
        workflow = self.workflow()
        items = [f"igwn+{item}" if item == IMAGE_URL else item for item in workflow.transfer("plot")]
        workflow.set_line("plot", "transfer_input_files", f"transfer_input_files = {','.join(items)}")
        self.assertCaught(workflow, "igwn+osdf://")

    def test_the_model_not_sent_to_sampling(self):
        workflow = self.workflow()
        items = [item for item in workflow.transfer("sampling") if item != workflow.model]
        workflow.set_line("sampling", "transfer_input_files", f"transfer_input_files = {','.join(items)}")
        self.assertCaught(workflow, f"{workflow.model} is not sent to the job")

    def test_the_model_not_sent_to_generation(self):
        workflow = self.workflow()
        items = [item for item in workflow.transfer("generation") if item != workflow.model]
        workflow.set_line("generation", "transfer_input_files", f"transfer_input_files = {','.join(items)}")
        self.assertCaught(workflow, f"{workflow.model} is not sent to the job")

    def test_a_frame_file_not_sent_to_generation(self):
        workflow = self.workflow()
        items = [item for item in workflow.transfer("generation") if item != "gwosc/L1.gwf"]
        workflow.set_line("generation", "transfer_input_files", f"transfer_input_files = {','.join(items)}")
        self.assertCaught(workflow, "gwosc/L1.gwf is not sent to the job")

    def test_a_psd_file_not_sent_to_generation(self):
        workflow = self.workflow()
        items = [item for item in workflow.transfer("generation") if item != workflow.psds[0]]
        workflow.set_line("generation", "transfer_input_files", f"transfer_input_files = {','.join(items)}")
        self.assertCaught(workflow, f"{workflow.psds[0]} is not sent to the job")

    def test_the_gps_file_not_sent_to_generation(self):
        workflow = self.workflow(events=2, gps_file=True)
        items = [item for item in workflow.transfer("generation", idx=1) if not item.endswith("T_gps.txt")]
        workflow.set_line("generation", "transfer_input_files", f"transfer_input_files = {','.join(items)}", idx=1)
        self.assertCaught(workflow, "The GPS file T_gps.txt is not sent to the job")

    def test_too_little_disk_for_the_model_and_the_image(self):
        workflow = self.workflow()
        sizes = {IMAGE_URL: int(0.8 * GiB), workflow.model: int(4.5 * GiB)}
        with mock.patch.object(check_workflow, "file_sizes", return_value=sizes):
            problems, _ = workflow.check()
        # Only the jobs that receive the model run short at the default 5 GB.
        short = sorted(problem.split(":")[0] for problem in problems if "Requests 5 GB of disk" in problem)
        self.assertEqual(
            short,
            ["T_data0_1000-0_generation.submit", "T_data0_1000-0_sampling.submit"],
        )

    def test_enough_disk_for_the_model_and_the_image(self):
        workflow = self.workflow()
        for kind in EXECUTABLES:
            workflow.set_line(kind, "request_disk", "request_disk = 12.0GB")
        sizes = {IMAGE_URL: int(0.8 * GiB), workflow.model: int(4.5 * GiB)}
        with mock.patch.object(check_workflow, "file_sizes", return_value=sizes):
            problems, _ = workflow.check()
        self.assertEqual(problems, [])

    def test_disk_must_leave_room_for_outputs(self):
        # 4.3 GB of files fit in 5 GB, but not with the 2 GB kept for outputs.
        workflow = self.workflow()
        sizes = {IMAGE_URL: int(0.8 * GiB), workflow.model: int(3.5 * GiB)}
        with mock.patch.object(check_workflow, "file_sizes", return_value=sizes):
            problems, _ = workflow.check()
        self.assertTrue(any("set request-disk to at least 6.3" in problem for problem in problems), problems)

    def test_disk_requested_in_other_units(self):
        workflow = self.workflow()
        workflow.set_line("plot", "request_disk", "request_disk = 5120")
        self.assertCaught(workflow, "Expected request_disk as '<n>GB'")

    def test_a_merge_job(self):
        workflow = self.workflow()
        workflow.jobs[("merge", 0)] = list(workflow.jobs[("plot", 0)])
        self.assertCaught(workflow, "A merge job")

    def test_an_event_without_jobs(self):
        self.assertCaught(self.workflow(), "1 generation job(s), expected 2", events=2)

    def test_a_missing_submit_file(self):
        workflow = self.workflow()
        workflow.write()
        (workflow.submit_dir / "T_data0_1000-0_plot.submit").unlink()
        self.assertCaught(workflow, "Missing submit file", write=False)

    def test_two_dag_files(self):
        workflow = self.workflow()
        workflow.write()
        (workflow.submit_dir / "dag_T_old.submit").write_text("")
        self.assertCaught(workflow, "Expected exactly one DAG file")

    def test_the_image_missing_from_osdf(self):
        # bilby_pipe would not send the image at all.
        workflow = self.workflow()
        workflow.image.unlink()
        self.assertCaught(workflow, "Cannot work out what to expect")


class TestSubmitFileHelpers(unittest.TestCase):
    def test_read_submit_file_keeps_order_and_equals_signs_in_values(self):
        pairs = read_submit_file_from_lines(
            [
                "# comment",
                "Universe = vanilla",
                "requirements = (HAS_SINGULARITY=?=True)",
                'MY.SingularityImage = "./x.sif"',
                "queue",
            ]
        )
        self.assertEqual(
            pairs,
            [
                ("universe", "vanilla"),
                ("requirements", "(HAS_SINGULARITY=?=True)"),
                ("my.singularityimage", '"./x.sif"'),
            ],
        )

    def test_last_value_is_the_one_condor_uses(self):
        pairs = [("requirements", "a"), ("requirements", "b")]
        self.assertEqual(last_value(pairs, "Requirements"), "b")
        self.assertIsNone(last_value(pairs, "executable"))

    def test_transfer_inputs_splits_on_commas(self):
        pairs = [("transfer_input_files", "a.ini, osdf:///x/y.sif ,b/c.gwf")]
        self.assertEqual(transfer_inputs(pairs), ["a.ini", "osdf:///x/y.sif", "b/c.gwf"])
        self.assertEqual(transfer_inputs([]), [])

    def test_disk_gb(self):
        self.assertEqual(disk_gb("12.0GB"), 12.0)
        self.assertEqual(disk_gb("5GB"), 5.0)
        for value in (None, "5120", "5120MB"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                disk_gb(value)

    def test_requirements_override(self):
        self.assertEqual(
            requirements_override({"extra-lines": f"[requirements = {OVERRIDE}, MY.Foo = 1]"}),
            OVERRIDE,
        )
        for raw in ("", "requirements = x", "[MY.Foo = 1]", "[requirements = a, requirements = b]"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                requirements_override({"extra-lines": raw})


class TestCovers(unittest.TestCase):
    def test_exact_and_wider_spans_cover(self):
        self.assertTrue(covers(100.0, 200.0, 100.0, 200.0, 1024))
        self.assertTrue(covers(0.0, 4096.0, 100.0, 200.0, 1024))

    def test_spans_short_at_either_end_do_not(self):
        self.assertFalse(covers(101.0, 200.0, 100.0, 200.0, 1024))
        self.assertFalse(covers(100.0, 199.0, 100.0, 200.0, 1024))

    def test_half_a_sample_of_rounding_is_allowed_and_no_more(self):
        sample = 1 / 1024
        self.assertTrue(covers(100.0 + 0.4 * sample, 200.0 - 0.4 * sample, 100.0, 200.0, 1024))
        self.assertFalse(covers(100.0 + 0.6 * sample, 200.0, 100.0, 200.0, 1024))
        self.assertFalse(covers(100.0, 200.0 - 0.6 * sample, 100.0, 200.0, 1024))


class TestGwfLibrary(unittest.TestCase):
    def library_with(self, available):
        def import_module(name):
            if name not in available:
                raise ImportError(name)

        with mock.patch.object(check_frames.importlib, "import_module", side_effect=import_module):
            return gwf_library()

    def test_reports_the_library_gwpy_tries_first(self):
        self.assertEqual(self.library_with({"lalframe"}), "LALFrame")
        self.assertEqual(self.library_with({"framel", "lalframe"}), "FrameL")
        self.assertEqual(self.library_with({"LDAStools.frameCPP", "framel", "lalframe"}), "frameCPP")
        self.assertEqual(self.library_with(set()), "none")


if __name__ == "__main__":
    unittest.main()
