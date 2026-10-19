"""Preview or run the production-pipeline resource benchmark.

python -m eval.run                    # preview only; no model calls
python -m eval.run --execute          # run configured question/configuration matrix
"""

import argparse
from contextlib import closing
import copy
import fcntl
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import threading
import time

import yaml

from eval.execution import run_jobs
from eval.report import read_rows, write_report

ROOT = Path(__file__).resolve().parent.parent


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def plan(config, tasks, configurations):
    runs = len(tasks) * len(configurations) * config["execution"].get("repetitions", 1)
    workers = config["execution"]["concurrency"]
    seconds = config["execution"]["scenario_timeout_seconds"]
    return {
        "questions": len(tasks),
        "configurations": configurations,
        "runs": runs,
        "workers": workers,
        "timeout_seconds_per_run": seconds,
        "timeout_waves_minutes_excluding_setup": ((runs + workers - 1) // workers)
        * seconds
        / 60,
        "metrics": config["measurement"]["metrics"],
        "reference_answers": False,
        "judge_calls": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "eval/config.yaml")
    parser.add_argument(
        "--execute", action="store_true", help="Explicitly start model/API calls"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without setup or API calls"
    )
    parser.add_argument("--limit", type=int, help="Use only the first N questions")
    parser.add_argument(
        "--configuration",
        action="append",
        help="Run only this configuration ID; repeatable",
    )
    parser.add_argument("--output", type=Path, help="New output directory")
    parser.add_argument(
        "--resume", type=Path, help="Resume unstarted jobs in an existing run directory"
    )
    args = parser.parse_args(argv)
    if args.resume and (args.output or args.limit or args.configuration):
        parser.error(
            "--resume uses its frozen settings; do not combine it with output/limit/configuration"
        )
    config_path = args.resume / "frozen_settings.yaml" if args.resume else args.config
    config = yaml.safe_load(config_path.read_text())
    if (
        config["execution"]["concurrency"] < 1
        or config["execution"]["scenario_timeout_seconds"] <= 0
    ):
        parser.error("Worker count and deadline must be positive")
    tasks = read_rows(
        args.resume / "tasks.jsonl"
        if args.resume
        else ROOT / config["dataset"]["tasks_path"]
    )
    if not tasks:
        parser.error(
            "Question dataset is missing or empty; run python -m eval.questions first"
        )
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        tasks = tasks[: args.limit]
    configurations = config["configurations"]
    if args.configuration:
        known = {configuration["id"] for configuration in configurations}
        if not set(args.configuration) <= known:
            parser.error(f"Valid configurations: {', '.join(sorted(known))}")
        configurations = [c for c in configurations if c["id"] in args.configuration]
    if args.resume:
        configurations = config["configurations"]
    # Persist exactly the selected matrix for reproducible resume.
    config["configurations"] = configurations
    preview = plan(config, tasks, configurations)
    print(json.dumps(preview, indent=2), flush=True)
    if args.dry_run or not (args.execute or config["execution"]["enabled"]):
        print("Preview only. Start with: python -m eval.run --execute", flush=True)
        return preview

    os.environ["HAYSTACK_TELEMETRY_ENABLED"] = "false"
    from rag_model import config as pipeline_settings, llm
    from eval.corpus import Corpus, CorpusManager
    from eval.runtime import run_pipeline

    runtime_settings = llm.load_settings()
    if not runtime_settings.get("api_key"):
        parser.error(
            "Set KEERA_API_KEY/APERTUS_API_KEY or configure the application's API key"
        )
    if any(c["id"] == "finetuned_router" for c in configurations) and not all(
        runtime_settings.get(key) for key in ("decision_url", "decision_api_key")
    ):
        parser.error(
            "Set APERTUS_DECISION_URL and APERTUS_DECISION_API_KEY, or configure them in the application"
        )
    setup_started = time.monotonic()
    database = (ROOT / config["dataset"]["frozen_sqlite"]).resolve()
    if not database.exists():
        source = (ROOT / config["dataset"]["source_sqlite"]).resolve()
        if not source.exists():
            parser.error(f"Production index not found: {source}")
        database.parent.mkdir(parents=True, exist_ok=True)
        with closing(
            sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        ) as original, closing(sqlite3.connect(database)) as snapshot:
            original.backup(snapshot)
    if args.resume:
        output = args.resume.resolve()
        frozen = yaml.safe_load((output / "frozen_pipeline.yaml").read_text())
        manifest = json.loads((output / "manifest.json").read_text())
        runtime_settings.update(manifest["provider_config"])
        config["pipeline"] = manifest["pipeline"]
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        output = (args.output or ROOT / "eval/runs" / stamp).resolve()
        output.mkdir(parents=True, exist_ok=False)
        frozen = copy.deepcopy(pipeline_settings.load())
        frozen["llm"].update(
            temperature=config["pipeline"]["temperature"],
            max_tokens=config["pipeline"]["max_output_tokens_per_call"],
            timeout=config["pipeline"]["llm_timeout_seconds"],
            max_retries=config["pipeline"]["transport_retries"],
            json_attempts=config["pipeline"]["output_repair_attempts"],
            stream=True,
        )
        frozen["agent"]["max_steps"] = config["pipeline"]["max_agent_steps"]
        runtime_settings.update(
            base_url=config["models"]["chat_base_url"],
            model_8b=config["models"]["generation_8b"],
            model_70b=config["models"]["generation_70b"],
            decision_model=config["models"]["decision_model"],
        )
        (output / "frozen_settings.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False)
        )
        (output / "frozen_pipeline.yaml").write_text(
            yaml.safe_dump(frozen, sort_keys=False)
        )
        (output / "tasks.jsonl").write_text(
            "".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks)
        )
        shutil.copytree(ROOT / "prompts", output / "prompts")
        safe_provider = {
            key: value
            for key, value in runtime_settings.items()
            if key
            in (
                "base_url",
                "model_8b",
                "model_70b",
                "decision_model",
                "decision_url",
                "model_agent",
                "model_brief",
                "model_queries",
            )
        }
        manifest = {
            "provider_config": safe_provider,
            "pipeline": config["pipeline"],
            "question_sha256": hashlib.sha256(
                (output / "tasks.jsonl").read_bytes()
            ).hexdigest(),
            "corpus_database": str(database),
            "corpus_sha256": hash_file(database),
            "code_sha256": {
                str(path.relative_to(ROOT)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for folder in ("rag_model", "eval")
                for path in sorted((ROOT / folder).glob("*.py"))
            },
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if (
        str(database) != manifest["corpus_database"]
        or hash_file(database) != manifest["corpus_sha256"]
    ):
        parser.error("Frozen corpus changed; use the original snapshot for this run")
    if hash_file(output / "tasks.jsonl") != manifest["question_sha256"]:
        parser.error("Frozen question dataset changed")
    if args.resume and any(
        not (ROOT / name).exists() or hash_file(ROOT / name) != digest
        for name, digest in manifest["code_sha256"].items()
    ):
        parser.error(
            "Benchmark/pipeline code changed; start a new run to keep configurations comparable"
        )
    lock_stream = (output / ".run.lock").open("a")
    try:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("This benchmark directory already has an active runner")
    print(
        "Building isolated retrieval service from the SQLite snapshot; the application may remain running.",
        flush=True,
    )
    corpus = Corpus(database, frozen)
    CorpusManager.register(
        "corpus", callable=lambda: corpus, exposed=("search", "embed")
    )
    authkey = os.urandom(32)
    server = CorpusManager(address=("127.0.0.1", 0), authkey=authkey).get_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    jobs, public_jobs = [], []
    for task in tasks:
        for configuration in configurations:
            for repetition in range(config["execution"].get("repetitions", 1)):
                identifier = f"{configuration['id']}_{task['id']}_{repetition}"
                public_jobs.append(
                    {
                        "id": identifier,
                        "configuration_id": configuration["id"],
                        "task_id": task["id"],
                        "task_type": task["type"],
                    }
                )
                job_directory = output / "jobs" / identifier
                if (
                    job_directory.exists()
                    and not (job_directory / "outcome.json").exists()
                ):
                    started_path = job_directory / "started.json"
                    started = (
                        json.loads(started_path.read_text())
                        if started_path.exists()
                        else {}
                    )
                    if not started_path.exists():
                        started_path.write_text(
                            json.dumps({"started_at_unix": time.time()})
                        )
                    (job_directory / "outcome.json").write_text(
                        json.dumps(
                            {
                                "id": identifier,
                                "status": "interrupted",
                                "elapsed_seconds": min(
                                    config["execution"]["scenario_timeout_seconds"],
                                    max(
                                        0,
                                        time.time()
                                        - started.get("started_at_unix", time.time()),
                                    ),
                                ),
                                "queue_seconds": started.get("queue_seconds", 0),
                                "error": "Previous runner exited before writing an outcome; partial usage retained",
                            }
                        )
                    )
                if (output / "jobs" / identifier / "outcome.json").exists():
                    continue
                jobs.append(
                    {
                        "id": identifier,
                        "task": task,
                        "configuration": configuration,
                        "runtime_settings": runtime_settings,
                        "pipeline_config": frozen,
                        "corpus_database": str(database),
                        "prompts_directory": str(output / "prompts"),
                        "corpus_address": server.address,
                        "corpus_authkey": authkey,
                    }
                )
    (output / "jobs.jsonl").write_text(
        "".join(json.dumps(job) + "\n" for job in public_jobs)
    )
    random.Random(config["execution"]["seed"]).shuffle(jobs)
    progress = {"done": len(public_jobs) - len(jobs)}

    def completed(outcome):
        progress["done"] += 1
        print(
            f"[{progress['done']}/{len(public_jobs)}] {outcome['id']}: {outcome['status']} ({outcome['elapsed_seconds']:.1f}s)",
            flush=True,
        )

    manifest["setup_seconds"] = time.monotonic() - setup_started
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        f"Output: {output}\nStarting {len(jobs)} pending runs with {config['execution']['concurrency']} workers.",
        flush=True,
    )
    began = time.monotonic()
    try:
        run_jobs(
            jobs,
            run_pipeline,
            output / "jobs",
            concurrency=config["execution"]["concurrency"],
            timeout_seconds=config["execution"]["scenario_timeout_seconds"],
            on_complete=completed,
        )
    finally:
        print(json.dumps(write_report(output), indent=2), flush=True)
        manifest["latest_execution_wall_seconds"] = time.monotonic() - began
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        server.stop_event.set()
        server.listener.close()
        corpus.close()
        lock_stream.close()
    return {"output": str(output)}


if __name__ == "__main__":
    main()
