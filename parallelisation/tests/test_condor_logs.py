"""Unit tests for condor_logs.py: Job event logs and dagman.out.

Anchored on a real CIT job log from the tutorial (a job held because /home was
gone), plus logs written here in the same format for the cases that one lacks.
Standard library only.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PARALLELISATION = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PARALLELISATION / "option_a"))

from condor_logs import (  # noqa: E402
    dag_outcome,
    dag_succeeded,
    job_timing,
    read_events,
    resources,
    run_remote_cpu,
)

REAL_LOG = (
    PARALLELISATION
    / "tutorial_reference/ex3_dingo_lensing_application/dingo_EXP1_lensed/log_data_generation"
    / "label_data0_1384782888-63_generation.log"
)
HOST = "<10.14.9.70:9618?addrs=10.14.9.70-9618&alias=node1070.cluster.ldas.cit&noUDP&sock=startd_1_2>"


def event(code, cluster, stamp, text, *body):
    return "\n".join([f"{code:03d} ({cluster}.000.000) 2026-10-08 {stamp} {text}", *body, "..."])


def terminated(cluster, stamp, return_value=0, cpu="Usr 0 00:07:00, Sys 0 00:00:20", received=5000000000):
    return event(
        5,
        cluster,
        stamp,
        "Job terminated.",
        f"\t(1) Normal termination (return value {return_value})",
        f"\t\t{cpu}  -  Run Remote Usage",
        "\t\tUsr 0 00:00:00, Sys 0 00:00:00  -  Run Local Usage",
        f"\t\t{cpu}  -  Total Remote Usage",
        "\t\tUsr 0 00:00:00, Sys 0 00:00:00  -  Total Local Usage",
        "\t12345  -  Run Bytes Sent By Job",
        f"\t{received}  -  Run Bytes Received By Job",
        "\t12345  -  Total Bytes Sent By Job",
        f"\t{received}  -  Total Bytes Received By Job",
        "\tPartitionable Resources :    Usage  Request Allocated ",
        "\t   Cpus                 :     1.84        8         8 ",
        "\t   Disk (KB)            :  5600000 12582912  12582912 ",
        "\t   GPUs                 :                           0 ",
        "\t   Memory (MB)          :     2345     8192      8192 ",
        "\t   TimeExecute (s)      :      220                    ",
        f"\tJob terminated of its own accord at 2026-10-08T15:{stamp[3:]}Z with exit-code {return_value}.",
    )


def submitted(cluster, stamp):
    return event(0, cluster, stamp, "Job submitted from host: <131.215.5.225:9618>", '    [ DAGNodeName = "x" ]')


def transfer(cluster, stamp, what):
    return event(40, cluster, stamp, what)


def executing(cluster, stamp):
    return event(1, cluster, stamp, f"Job executing on host: {HOST}", "\tSlotName: slot1_1@node1070.cluster.ldas.cit")


def job_ad(cluster, stamp):
    # CIT logs a job-ad event after each event: ClassAd lines, no indentation.
    return event(28, cluster, stamp, "Job ad information event triggered.", f"Cluster = {cluster}", 'MyType = "X"')


def at(stamp):
    return datetime.strptime(f"2026-10-08 {stamp}", "%Y-%m-%d %H:%M:%S")


class LogFiles(unittest.TestCase):
    def write(self, *events) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "job.log"
        path.write_text("\n".join(events) + "\n")
        return path


class TestReadEvents(LogFiles):
    def test_the_real_cit_log(self):
        events = read_events(REAL_LOG)
        self.assertEqual([e.code for e in events], [0, 28, 40, 28, 40, 28, 1, 28, 21, 4, 28, 12, 28, 9, 28])
        self.assertEqual(events[0].cluster, 225715616)
        self.assertEqual(events[0].time, datetime(2026, 9, 6, 20, 28, 48))
        self.assertEqual(events[2].text, "Started transferring input files")
        self.assertIn('DAGNodeName = "label_data0_1384782888-63_generation_arg_0"', events[0].body[0])

    def test_events_keep_their_bodies(self):
        path = self.write(submitted(1, "08:39:56"), job_ad(1, "08:39:56"), executing(1, "08:41:20"))
        events = read_events(path)
        self.assertEqual([e.code for e in events], [0, 28, 1])
        self.assertEqual(events[1].body, ["Cluster = 1", 'MyType = "X"'])
        self.assertEqual(events[2].body, ["\tSlotName: slot1_1@node1070.cluster.ldas.cit"])

    def test_a_log_cut_off_mid_event_keeps_the_last_event(self):
        path = self.write(submitted(1, "08:39:56"), "001 (1.000.000) 2026-10-08 08:41:20 Job executing on host: x")
        self.assertEqual([e.code for e in read_events(path)], [0, 1])

    def test_unexpected_lines_and_dates_are_errors(self):
        with self.assertRaisesRegex(ValueError, "Expected an event header"):
            read_events(self.write("not an event"))
        with self.assertRaisesRegex(ValueError, "Unrecognised event time"):
            read_events(self.write("000 (1.000.000) 10/08 08:39:56 Job submitted from host: x\n..."))


class TestBodies(unittest.TestCase):
    def test_run_remote_cpu_adds_user_and_system_time_across_days(self):
        body = ["\t\tUsr 1 02:03:04, Sys 0 00:00:06  -  Run Remote Usage"]
        self.assertEqual(run_remote_cpu(body), 86400 + 2 * 3600 + 3 * 60 + 4 + 6)
        self.assertIsNone(run_remote_cpu(["\t\tUsr 0 00:00:01, Sys 0 00:00:00  -  Run Local Usage"]))

    def test_resources_places_values_under_their_columns(self):
        table = resources(read_events(REAL_LOG)[9].body)  # The real log's eviction event.
        self.assertEqual(table["Cpus"], {"Usage": None, "Request": 1.0, "Allocated": 1.0})
        self.assertEqual(table["Disk (KB)"], {"Usage": 4500000.0, "Request": 5242880.0, "Allocated": 5242880.0})
        self.assertEqual(table["GPUs"], {"Usage": None, "Request": None, "Allocated": 0.0})
        self.assertEqual(table["Memory (MB)"], {"Usage": None, "Request": 16384.0, "Allocated": 16384.0})
        self.assertEqual(table["TimeSlotBusy (s)"], {"Usage": 18.0, "Request": None, "Allocated": None})

    def test_resources_table_ends_at_the_first_line_that_is_not_a_row(self):
        body = terminated(1, "08:45:05").splitlines()[1:-1]
        table = resources(body)
        self.assertEqual(set(table), {"Cpus", "Disk (KB)", "GPUs", "Memory (MB)", "TimeExecute (s)"})
        self.assertEqual(table["Cpus"]["Usage"], 1.84)


class TestJobTiming(LogFiles):
    def test_a_successful_job(self):
        events = read_events(
            self.write(
                submitted(1, "08:39:56"),
                job_ad(1, "08:39:56"),
                transfer(1, "08:41:00", "Started transferring input files"),
                transfer(1, "08:41:20", "Finished transferring input files"),
                executing(1, "08:41:20"),
                transfer(1, "08:45:00", "Started transferring output files"),
                transfer(1, "08:45:05", "Finished transferring output files"),
                terminated(1, "08:45:05"),
            )
        )
        timing = job_timing(events)
        self.assertTrue(timing.succeeded)
        self.assertEqual(timing.attempts, 1)
        self.assertEqual(timing.submitted, at("08:39:56"))
        self.assertEqual(timing.wait_seconds, 64)
        self.assertEqual(timing.input_seconds, 20)
        self.assertEqual(timing.run_seconds, 220)
        self.assertEqual(timing.output_seconds, 5)
        self.assertEqual(timing.finished, at("08:45:05"))
        self.assertEqual(timing.cpu_seconds, 440)
        self.assertEqual(timing.cores_used, 2.0)
        self.assertEqual(timing.wasted_cpu_seconds, 0.0)
        self.assertEqual(timing.bytes_received, 5000000000)
        self.assertEqual(timing.host, "node1070.cluster.ldas.cit")
        self.assertEqual(timing.resources["Memory (MB)"]["Request"], 8192.0)

    def test_an_evicted_attempt_counts_as_wasted_and_the_wait_runs_to_the_rerun(self):
        timing = job_timing(
            read_events(
                self.write(
                    submitted(1, "08:39:56"),
                    transfer(1, "08:40:00", "Started transferring input files"),
                    transfer(1, "08:40:10", "Finished transferring input files"),
                    executing(1, "08:40:10"),
                    event(4, 1, "08:50:10", "Job was evicted.", "\t\tUsr 0 00:10:00, Sys 0 00:00:00  -  Run Remote Usage"),
                    transfer(1, "09:00:00", "Started transferring input files"),
                    transfer(1, "09:00:20", "Finished transferring input files"),
                    executing(1, "09:00:20"),
                    terminated(1, "09:04:00"),
                )
            )
        )
        self.assertTrue(timing.succeeded)
        self.assertEqual(timing.attempts, 2)
        self.assertEqual(timing.wasted_cpu_seconds, 600)
        self.assertEqual(timing.started, at("09:00:00"))
        self.assertEqual(timing.wait_seconds, (at("09:00:00") - at("08:39:56")).total_seconds())
        self.assertEqual(timing.run_seconds, 220)

    def test_a_dagman_retry_after_a_failed_attempt(self):
        timing = job_timing(
            read_events(
                self.write(
                    submitted(1, "08:39:56"),
                    executing(1, "08:40:00"),
                    terminated(1, "08:41:00", return_value=1, cpu="Usr 0 00:01:00, Sys 0 00:00:00"),
                    submitted(2, "08:41:30"),
                    executing(2, "08:42:00"),
                    terminated(2, "08:46:00"),
                )
            )
        )
        self.assertTrue(timing.succeeded)
        self.assertEqual(timing.submitted, at("08:39:56"))
        self.assertEqual(timing.attempts, 2)
        self.assertEqual(timing.wasted_cpu_seconds, 60)
        self.assertEqual(timing.started, at("08:42:00"))

    def test_a_restart_without_new_transfers_does_not_keep_the_old_ones(self):
        # After a shadow exception (007) the job can execute again directly.
        timing = job_timing(
            read_events(
                self.write(
                    submitted(1, "08:39:56"),
                    transfer(1, "08:40:00", "Started transferring input files"),
                    transfer(1, "08:40:10", "Finished transferring input files"),
                    executing(1, "08:40:10"),
                    event(7, 1, "08:41:00", "Shadow exception!"),
                    executing(1, "08:42:00"),
                    terminated(1, "08:46:00"),
                )
            )
        )
        self.assertEqual(timing.attempts, 2)
        self.assertEqual(timing.started, at("08:42:00"))
        self.assertIsNone(timing.input_seconds)
        self.assertEqual(timing.run_seconds, 240)

    def test_a_job_that_never_succeeds(self):
        timing = job_timing(
            read_events(self.write(submitted(1, "08:39:56"), executing(1, "08:40:00"), terminated(1, "08:41:00", return_value=2)))
        )
        self.assertFalse(timing.succeeded)
        self.assertEqual(timing.return_value, 2)
        self.assertIsNone(timing.finished)
        self.assertIsNone(timing.wait_seconds)
        self.assertIsNone(timing.cores_used)

    def test_without_transfer_events_the_run_starts_at_execution(self):
        timing = job_timing(read_events(self.write(submitted(1, "08:39:56"), executing(1, "08:40:00"), terminated(1, "08:44:00"))))
        self.assertEqual(timing.started, at("08:40:00"))
        self.assertIsNone(timing.input_seconds)
        self.assertEqual(timing.run_seconds, 240)
        self.assertIsNone(timing.output_seconds)

    def test_the_real_held_job(self):
        timing = job_timing(read_events(REAL_LOG))
        self.assertFalse(timing.succeeded)
        self.assertEqual(timing.attempts, 1)
        self.assertEqual(timing.wasted_cpu_seconds, 0.0)
        self.assertIsNone(timing.started)

    def test_no_events_is_an_error(self):
        with self.assertRaises(ValueError):
            job_timing([])


DAGMAN_OUT_OK = """\
10/08/26 08:46:59 All jobs Completed!
10/08/26 08:46:59 DAG status: 0 (DAG_STATUS_OK)
10/08/26 08:46:59 Of 4 nodes total:
10/08/26 08:46:59  Done     Pre   Queued    Post   Ready   Un-Ready   Failed   Futile
10/08/26 08:46:59   ===     ===      ===     ===     ===        ===      ===      ===
10/08/26 08:46:59     4       0        0       0       0          0        0        0
10/08/26 08:46:59 **** condor_dagman (condor_DAGMAN) pid 1030889 EXITING WITH STATUS 0
"""
DAGMAN_OUT_FAILED = """\
10/08/26 08:41:00 Of 4 nodes total:
10/08/26 08:41:00  Done     Pre   Queued    Post   Ready   Un-Ready   Failed   Futile
10/08/26 08:41:00   ===     ===      ===     ===     ===        ===      ===      ===
10/08/26 08:41:00     0       0        1       0       0          3        0        0
10/08/26 08:46:00 DAG status: 2 (DAG_STATUS_NODE_FAILED)
10/08/26 08:46:00 Of 4 nodes total:
10/08/26 08:46:00  Done     Pre   Queued    Post   Ready   Un-Ready   Failed   Futile
10/08/26 08:46:00   ===     ===      ===     ===     ===        ===      ===      ===
10/08/26 08:46:00     1       0        0       0       0          2        1        0
10/08/26 08:46:00 **** condor_dagman (condor_DAGMAN) pid 1030889 EXITING WITH STATUS 1
"""


class TestDagOutcome(LogFiles):
    def test_a_successful_dag(self):
        outcome = dag_outcome(self.write(DAGMAN_OUT_OK))
        self.assertEqual(outcome["status"], 0)
        self.assertEqual(outcome["status_name"], "DAG_STATUS_OK")
        self.assertEqual(outcome["exit_status"], 0)
        self.assertEqual(outcome["nodes"]["total"], 4)
        self.assertEqual(outcome["nodes"]["done"], 4)
        self.assertEqual(outcome["nodes"]["un-ready"], 0)
        self.assertTrue(dag_succeeded(outcome))

    def test_a_failed_dag_reads_the_last_table(self):
        outcome = dag_outcome(self.write(DAGMAN_OUT_FAILED))
        self.assertEqual(outcome["status"], 2)
        self.assertEqual(outcome["exit_status"], 1)
        self.assertEqual(outcome["nodes"]["done"], 1)
        self.assertEqual(outcome["nodes"]["failed"], 1)
        self.assertFalse(dag_succeeded(outcome))

    def test_any_shortfall_is_a_failure(self):
        outcome = dag_outcome(self.write(DAGMAN_OUT_OK))
        outcome["nodes"]["done"] = 3
        self.assertFalse(dag_succeeded(outcome))
        outcome["nodes"]["done"], outcome["nodes"]["failed"] = 4, 1
        self.assertFalse(dag_succeeded(outcome))
        outcome["nodes"]["failed"], outcome["exit_status"] = 0, 1
        self.assertFalse(dag_succeeded(outcome))
        self.assertFalse(dag_succeeded({"status": 0, "exit_status": 0, "nodes": None, "status_name": None}))
        empty = {"status": 0, "exit_status": 0, "status_name": None, "nodes": {"total": 0, "done": 0, "failed": 0}}
        self.assertFalse(dag_succeeded(empty))

    def test_a_dag_still_running_has_no_outcome(self):
        outcome = dag_outcome(self.write("10/08/26 08:40:00 Bootstrapping...\n"))
        self.assertIsNone(outcome["status"])
        self.assertFalse(dag_succeeded(outcome))


if __name__ == "__main__":
    unittest.main()
