"""Resource totals from durable logs, including interrupted API calls."""

from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics


def read_rows(path):
    path = Path(path)
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A killed writer may leave its final line incomplete.
                continue
    return rows


def tokens(usage, classifier=False):
    usage = usage or {}
    input_count = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_count = usage.get("completion_tokens", usage.get("output_tokens"))
    if classifier:
        output_count = 0
    total = usage.get("total_tokens")
    if total is None and input_count is not None and output_count is not None:
        total = input_count + output_count
    return {
        "input_tokens": input_count,
        "output_tokens": output_count,
        "total_tokens": total,
    }


def collect_calls(directory, outcome):
    directory = Path(directory)
    entries = [
        row
        for path in sorted((directory / "pipeline").glob("*.jsonl"))
        for row in read_rows(path)
    ]
    requests, ends = {}, {}
    for entry in entries:
        event = entry.get("event", "")
        if event in ("chat_request", "decision_http_request"):
            requests[entry["call_id"]] = entry
        elif event in (
            "chat_response",
            "chat_error",
            "decision_http_response",
            "decision_http_error",
        ):
            ends[entry["call_id"]] = entry
    started = json.loads((directory / "started.json").read_text())
    ended_at = started.get("started_at_unix", 0) + outcome["elapsed_seconds"]
    calls = []
    for identifier, request in requests.items():
        end = ends.get(identifier)
        classifier = request["event"] == "decision_http_request"
        replies = ((end or {}).get("output") or {}).get("replies") or []
        usage = (
            (end or {}).get("usage")
            if classifier
            else (replies[0].get("meta", {}).get("usage") if replies else None)
        )
        status = (
            "interrupted"
            if end is None
            else "error"
            if end["event"].endswith("_error")
            else "completed"
        )
        if end and end.get("http_status", 200) >= 400:
            status = "error"
        elapsed = (end or {}).get("elapsed_s")
        if elapsed is None:
            elapsed = max(
                0, ended_at - datetime.fromisoformat(request["timestamp"]).timestamp()
            )
        calls.append(
            {
                "run_id": outcome["id"],
                "call_id": identifier,
                "model": request.get("model") or "unknown",
                "purpose": request.get("purpose"),
                "category": "finetuned_routing"
                if classifier
                else "llm_routing"
                if request.get("purpose") == "capacity_routing"
                else "generation",
                "status": status,
                "elapsed_seconds": elapsed,
                "usage_source": "provider_reported" if usage else "missing",
                "model_revision": (end or {}).get("model_revision"),
                **tokens(usage, classifier),
            }
        )
    return calls


def write_report(output):
    output = Path(output)
    jobs = {job["id"]: job for job in read_rows(output / "jobs.jsonl")}
    runs, calls = [], []
    for path in sorted((output / "jobs").glob("*/outcome.json")):
        outcome = json.loads(path.read_text())
        job = jobs[outcome["id"]]
        run_calls = collect_calls(path.parent, outcome)
        for call in run_calls:
            call.update(
                configuration_id=job["configuration_id"], task_type=job["task_type"]
            )
        calls.extend(run_calls)
        runs.append(
            {
                "id": outcome["id"],
                "task_id": job["task_id"],
                "task_type": job["task_type"],
                "configuration_id": job["configuration_id"],
                "status": outcome["status"],
                "elapsed_seconds": outcome["elapsed_seconds"],
                "queue_seconds": outcome["queue_seconds"],
                "model_calls": len(run_calls),
                "error": outcome.get("error"),
            }
        )
    for filename, rows in (("runs.jsonl", runs), ("calls.jsonl", calls)):
        (output / filename).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        )
    grouped = defaultdict(list)
    for call in calls:
        grouped[(call["configuration_id"], call["model"])].append(call)
        grouped[(call["configuration_id"], "ALL_MODELS")].append(call)
        grouped[("ALL_CONFIGURATIONS", call["model"])].append(call)
        grouped[("ALL_CONFIGURATIONS", "ALL_MODELS")].append(call)
    summary = []
    for config_id in sorted(
        {job["configuration_id"] for job in jobs.values()} | {"ALL_CONFIGURATIONS"}
    ):
        config_runs = [
            run
            for run in runs
            if config_id == "ALL_CONFIGURATIONS" or run["configuration_id"] == config_id
        ]
        model_names = {model for cfg, model in grouped if cfg == config_id} | {
            "ALL_MODELS"
        }
        for model in sorted(model_names):
            model_calls = grouped[(config_id, model)]
            elapsed = [run["elapsed_seconds"] for run in config_runs]
            row = {
                "configuration_id": config_id,
                "model": model,
                "runs": len(config_runs),
                "completed_runs": sum(
                    run["status"] == "completed" for run in config_runs
                ),
                "timeout_runs": sum(run["status"] == "timeout" for run in config_runs),
                "failed_or_interrupted_runs": sum(
                    run["status"] not in ("completed", "timeout") for run in config_runs
                ),
                "model_calls": len(model_calls),
                "failed_calls": sum(call["status"] == "error" for call in model_calls),
                "interrupted_calls": sum(
                    call["status"] == "interrupted" for call in model_calls
                ),
                "sum_model_call_seconds": sum(
                    call["elapsed_seconds"] for call in model_calls
                ),
                "sum_run_wall_seconds": sum(elapsed) if model == "ALL_MODELS" else None,
                "mean_run_wall_seconds": statistics.mean(elapsed)
                if elapsed and model == "ALL_MODELS"
                else None,
                "missing_usage_calls": sum(
                    call["total_tokens"] is None for call in model_calls
                ),
            }
            for field in ("input_tokens", "output_tokens", "total_tokens"):
                known = sum(
                    call[field] for call in model_calls if call[field] is not None
                )
                row["known_" + field] = known
                row[field] = (
                    known
                    if all(call[field] is not None for call in model_calls)
                    else None
                )
            summary.append(row)
    with (output / "summary.csv").open("w", newline="") as stream:
        if summary:
            writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
    lines = [
        "# Resource benchmark",
        "",
        f"Finished runs: {len(runs)}/{len(jobs)}. Model/API calls: {len(calls)}.",
        "",
        "Tokens are provider-reported. `unknown` is missing usage; known subtotals are in summary.csv.",
        "The fine-tuned classifier currently returns no input-token usage; its input/total tokens remain unknown.",
        "Local embedding calls are excluded from LLM call/token counts; retrieval time is included in run wall time.",
        "",
        "| Configuration | Model | Calls | Total tokens | Missing usage calls | Sum call seconds |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            f"| {row['configuration_id']} | {row['model']} | {row['model_calls']} | {row['total_tokens'] if row['total_tokens'] is not None else 'unknown'} | {row['missing_usage_calls']} | {row['sum_model_call_seconds']:.2f} |"
        )
    lines += [
        "",
        "| Configuration | Runs | Mean run seconds | Sum run seconds | Timeouts |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        if row["model"] == "ALL_MODELS":
            mean = row["mean_run_wall_seconds"]
            lines.append(
                f"| {row['configuration_id']} | {row['runs']} | {mean if mean is not None else 'n/a'} | {row['sum_run_wall_seconds']:.2f} | {row['timeout_runs']} |"
            )
    lines += [
        "",
        "Combined calls/tokens include routing, generation, repairs, failures and interrupted requests.",
        "Sum call durations and sum run wall times measure different things; concurrent durations overlap.",
        "No reference answers, quality metrics or evaluator calls are used.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return {"runs": len(runs), "calls": len(calls), "output": str(output)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(write_report(parser.parse_args().output), indent=2))
