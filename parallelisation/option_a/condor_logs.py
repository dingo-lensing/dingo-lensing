#!/usr/bin/env python3
"""Read HTCondor job event logs, and DAGMan's dagman.out.

The event format is the one CIT's HTCondor writes (see the job logs under
tutorial_reference/ex3_dingo_lensing_application/dingo_EXP1_lensed/): Each event
starts with 'NNN (cluster.proc.subproc) YYYY-MM-DD HH:MM:SS text' and ends with
a '...' line. Standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

HEADER = re.compile(r"^(\d{3}) \((\d+)\.(\d+)\.(\d+)\) (\S+ \S+) (.*)$")
RUN_REMOTE_USAGE = re.compile(
    r"Usr (\d+) (\d+):(\d+):(\d+), Sys (\d+) (\d+):(\d+):(\d+)\s+-\s+Run Remote Usage"
)
RETURN_VALUE = re.compile(r"Normal termination \(return value (-?\d+)\)")
BYTES_RECEIVED = re.compile(r"^\s*(\d+)\s+-\s+Run Bytes Received By Job")
HOST = re.compile(r"alias=([^&>]+)")

SUBMITTED, EXECUTING, EVICTED, TERMINATED, FILE_TRANSFER = 0, 1, 4, 5, 40


@dataclass
class Event:
    code: int
    cluster: int
    time: datetime
    text: str
    body: List[str] = field(default_factory=list)


def read_events(path) -> List[Event]:
    """All events in a job event log, in order."""
    events = []
    current = None
    for number, line in enumerate(Path(path).read_text(errors="replace").splitlines(), start=1):
        if current is None:
            if not line.strip():
                continue
            match = HEADER.match(line)
            if match is None:
                raise ValueError(f"{path}:{number}: Expected an event header, got {line!r}")
            code, cluster, _, _, stamp, text = match.groups()
            try:
                time = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise ValueError(f"{path}:{number}: Unrecognised event time {stamp!r}") from None
            current = Event(int(code), int(cluster), time, text.strip())
        elif line.strip() == "...":
            events.append(current)
            current = None
        else:
            current.body.append(line)
    if current is not None:  # A log cut off mid-event.
        events.append(current)
    return events


def run_remote_cpu(body: List[str]) -> Optional[float]:
    """CPU seconds (user + system) an attempt used, from its 'Run Remote Usage' line."""
    for line in body:
        match = RUN_REMOTE_USAGE.search(line)
        if match:
            d1, h1, m1, s1, d2, h2, m2, s2 = map(int, match.groups())
            return float(d1 * 86400 + h1 * 3600 + m1 * 60 + s1 + d2 * 86400 + h2 * 3600 + m2 * 60 + s2)
    return None


def resources(body: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
    """The 'Partitionable Resources' table: {resource: {Usage, Request, Allocated}}.

    Values are right-aligned under the header's column names, and a blank cell
    means HTCondor did not report that value.
    """
    table = {}
    column_ends = None
    for line in body:
        name, separator, cells = line.partition(":")
        if not separator:
            continue
        if name.strip() == "Partitionable Resources":
            column_ends = {
                column: cells.index(column) + len(column) for column in ("Usage", "Request", "Allocated")
            }
            continue
        if column_ends is None:
            continue
        tokens = list(re.finditer(r"\S+", cells))
        try:
            values = [float(token.group()) for token in tokens]
        except ValueError:
            break  # The table has ended.
        row = dict.fromkeys(column_ends)
        for token, value in zip(tokens, values):
            row[min(column_ends, key=lambda column: abs(column_ends[column] - token.end()))] = value
        table[name.strip()] = row
    return table


@dataclass
class JobTiming:
    """One job's history, from its first submission to its successful run."""

    submitted: datetime
    attempts: int  # Executions, including the successful one.
    wasted_cpu_seconds: float  # CPU used by attempts that didn't succeed.
    started: Optional[datetime] = None  # The successful run's input transfer, else its execution.
    input_seconds: Optional[float] = None
    executing: Optional[datetime] = None
    run_seconds: Optional[float] = None  # From execution to output transfer (or termination).
    output_seconds: Optional[float] = None
    finished: Optional[datetime] = None
    return_value: Optional[int] = None
    cpu_seconds: Optional[float] = None
    bytes_received: Optional[int] = None
    host: Optional[str] = None
    resources: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.return_value == 0

    @property
    def wait_seconds(self) -> Optional[float]:
        """From first submission to the start of the successful run."""
        return None if self.started is None else (self.started - self.submitted).total_seconds()

    @property
    def cores_used(self) -> Optional[float]:
        if self.cpu_seconds is None or not self.run_seconds:
            return None
        return self.cpu_seconds / self.run_seconds


def seconds(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    return None if start is None or end is None else (end - start).total_seconds()


def job_timing(events: List[Event]) -> JobTiming:
    """Summarise a job's events, including any DAGMan retries in the same log."""
    if not events:
        raise ValueError("No events")
    submitted = next((event.time for event in events if event.code == SUBMITTED), events[0].time)
    timing = JobTiming(submitted=submitted, attempts=0, wasted_cpu_seconds=0.0)
    run: Dict[str, object] = {}
    for event in events:
        if event.code == FILE_TRANSFER:
            if event.text.startswith("Started transferring input"):
                run = {"input_start": event.time}
            elif event.text.startswith("Finished transferring input"):
                run["input_end"] = event.time
            elif event.text.startswith("Started transferring output"):
                run["output_start"] = event.time
            elif event.text.startswith("Finished transferring output"):
                run["output_end"] = event.time
        elif event.code == EXECUTING:
            if "executing" in run:  # Restarted without a new input transfer.
                run = {}
            timing.attempts += 1
            run["executing"] = event.time
            host = HOST.search(event.text)
            run["host"] = host.group(1) if host else None
        elif event.code == EVICTED:
            timing.wasted_cpu_seconds += run_remote_cpu(event.body) or 0.0
            run = {}
        elif event.code == TERMINATED:
            match = next((RETURN_VALUE.search(line) for line in event.body if RETURN_VALUE.search(line)), None)
            timing.return_value = int(match.group(1)) if match else None
            if timing.return_value != 0:
                timing.wasted_cpu_seconds += run_remote_cpu(event.body) or 0.0
                run = {}
                continue
            timing.started = run.get("input_start") or run.get("executing")
            timing.input_seconds = seconds(run.get("input_start"), run.get("input_end"))
            timing.executing = run.get("executing")
            timing.run_seconds = seconds(run.get("executing"), run.get("output_start") or event.time)
            timing.output_seconds = seconds(run.get("output_start"), run.get("output_end"))
            timing.finished = event.time
            timing.cpu_seconds = run_remote_cpu(event.body)
            received = next((BYTES_RECEIVED.match(line) for line in event.body if BYTES_RECEIVED.match(line)), None)
            timing.bytes_received = int(received.group(1)) if received else None
            timing.host = run.get("host")
            timing.resources = resources(event.body)
            run = {}
    return timing


def dag_outcome(path) -> dict:
    """How a DAG ended, from the last status lines and node table in its dagman.out."""
    outcome = {"status": None, "status_name": None, "exit_status": None, "nodes": None}
    lines = Path(path).read_text(errors="replace").splitlines()
    for index, line in enumerate(lines):
        status = re.search(r"DAG status: (-?\d+) \((\w+)\)", line)
        if status:
            outcome["status"], outcome["status_name"] = int(status.group(1)), status.group(2)
        exiting = re.search(r"EXITING WITH STATUS (-?\d+)", line)
        if exiting:
            outcome["exit_status"] = int(exiting.group(1))
        total = re.search(r"Of (\d+) nodes total:", line)
        if total and index + 3 < len(lines):
            # Each line starts with the date and time; the node counts follow.
            names = [name.lower() for name in lines[index + 1].split()[2:]]
            values = [int(value) for value in lines[index + 3].split()[2:]]
            outcome["nodes"] = {"total": int(total.group(1)), **dict(zip(names, values))}
    return outcome


def dag_succeeded(outcome: dict) -> bool:
    nodes = outcome["nodes"]
    return (
        outcome["status"] == 0
        and outcome["exit_status"] == 0
        and nodes is not None
        and nodes["total"] > 0
        and nodes.get("done") == nodes["total"]
        and nodes.get("failed", 0) == 0
    )
