"""Bounded, isolated task execution. Importing this module never starts a benchmark."""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import re
import signal
import time
import traceback


def _write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, default=str))
    temporary.replace(path)


def _execute(handler, job, directory):
    if os.name == "posix":
        os.setsid()
    try:
        result = handler(job, directory)
        outcome = {"status": "completed", "result": result}
    except BaseException as error:
        outcome = {
            "status": "error",
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        for key in ("api_key", "decision_api_key"):
            secret = job.get("runtime_settings", {}).get(key)
            if secret:
                for field in ("error", "traceback"):
                    outcome[field] = outcome[field].replace(secret, "[REDACTED]")
    _write(
        directory / "worker_result.json",
        {**outcome, "finished_monotonic": time.monotonic()},
    )


def _stop(process):
    # A process group also stops subprocesses created by the task on Unix.
    try:
        if os.name == "posix" and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGKILL)
        elif process.is_alive():
            process.kill()
    except ProcessLookupError:
        pass
    process.join()


def run_jobs(
    jobs, handler, output, *, concurrency=10, timeout_seconds=60, on_complete=None
):
    """Run a picklable handler(job, directory) within a hard deadline per job.

    The handler must write incremental telemetry to its directory; those files
    survive termination. The parent always writes outcome.json and returns an
    outcome, including errors and timeouts. This utility makes no API calls itself.
    Deadline accounting starts before spawning, so startup is included. Queueing
    before a slot is available is measured separately.
    """
    if concurrency < 1 or timeout_seconds <= 0:
        raise ValueError("Concurrency and timeout must be positive")
    jobs = list(jobs)
    ids = [job["id"] for job in jobs]
    if len(set(ids)) != len(ids) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]+", job_id) for job_id in ids
    ):
        raise ValueError("Job IDs must be unique safe directory names")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Refuse to replace telemetry from an earlier execution.
    if any((output / job_id).exists() for job_id in ids):
        raise FileExistsError(
            "A job directory already exists; select a new run directory"
        )
    context = multiprocessing.get_context("spawn")
    queued = time.monotonic()
    pending = iter(jobs)
    active, outcomes = {}, []
    exhausted = False
    try:
        while active or not exhausted:
            while not exhausted and len(active) < concurrency:
                job = next(pending, None)
                if job is None:
                    exhausted = True
                    break
                directory = output / job["id"]
                directory.mkdir()
                started = time.monotonic()
                started_unix = time.time()
                process = context.Process(
                    target=_execute, args=(handler, job, directory)
                )
                process.start()
                active[job["id"]] = (process, directory, started)
                _write(
                    directory / "started.json",
                    {
                        "id": job["id"],
                        "queue_seconds": started - queued,
                        "started_at_unix": started_unix,
                        "timeout_seconds": timeout_seconds,
                    },
                )
            for job_id, (process, directory, started) in list(active.items()):
                now = time.monotonic()
                result_path = directory / "worker_result.json"
                result = (
                    json.loads(result_path.read_text())
                    if result_path.exists()
                    else None
                )
                # Use the worker's finish time: delayed parent polling must not
                # turn a task completed within its budget into a timeout.
                timed_out = (
                    result["finished_monotonic"] - started > timeout_seconds
                    if result and not process.is_alive()
                    else now - started >= timeout_seconds
                )
                if not timed_out and process.is_alive():
                    continue
                if timed_out:
                    _stop(process)
                    outcome = {
                        "status": "timeout",
                        "error": "Task wall-clock deadline exceeded",
                    }
                    finished = now
                elif result:
                    process.join()
                    outcome = {
                        k: v for k, v in result.items() if k != "finished_monotonic"
                    }
                    finished = result["finished_monotonic"]
                else:
                    process.join()
                    outcome = {
                        "status": "error",
                        "error": "Worker exited without a result",
                    }
                    finished = now
                outcome.update(
                    id=job_id,
                    elapsed_seconds=finished - started,
                    queue_seconds=started - queued,
                    timeout_seconds=timeout_seconds,
                    exit_code=process.exitcode,
                    telemetry_directory=str(directory),
                )
                _write(directory / "outcome.json", outcome)
                outcomes.append(outcome)
                del active[job_id]
                if on_complete:
                    on_complete(outcome)
            if active:
                time.sleep(0.01)
    finally:
        for job_id, (process, directory, started) in active.items():
            _stop(process)
            _write(
                directory / "outcome.json",
                {
                    "id": job_id,
                    "status": "interrupted",
                    "elapsed_seconds": time.monotonic() - started,
                    "queue_seconds": started - queued,
                    "timeout_seconds": timeout_seconds,
                    "exit_code": process.exitcode,
                },
            )
    return outcomes
