"""Export questions and source metadata from cached candidates; no model calls."""

import hashlib
import json

import yaml

from eval.common import ROOT, write_json
from eval.prepare import select_tasks


def run():
    config = yaml.safe_load((ROOT / "eval/config.yaml").read_text())
    out = ROOT / "eval/data"
    candidates = []
    for path in sorted((out / "candidates").glob("*.json")):
        if path.name.endswith((".questions.json", ".keypoints.json")):
            continue
        for task in json.loads(path.read_text())["accepted"]:
            review_path = out / "quality_reviews_v2" / f"{task['id']}.json"
            if review_path.exists():
                review = json.loads(review_path.read_text())
                if not review["accept"]:
                    continue
                task["question"] = review["question"]
            candidates.append(task)
    tasks, counts = select_tasks(
        candidates, config["dataset"]["task_type_targets"], config["execution"]["seed"]
    )
    if counts != config["dataset"]["task_type_targets"]:
        raise SystemExit(f"Not enough cached questions to fill task types: {counts}")
    questions = []
    for task in tasks:
        source = task["reference_passages"][0]
        questions.append(
            {
                "id": task["id"],
                "question": f"Regarding the page ‘{source['title']}’ ({source['url']}): {task['question']}",
                "type": task["type"],
                "document_id": task["document_id"],
                "source_url": source["url"],
                "source_title": source["title"],
                "source": task["source"],
                "source_language": task["source_language"],
            }
        )
    target = ROOT / config["dataset"]["tasks_path"]
    temporary = target.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions)
    )
    temporary.replace(target)
    provenance = {
        "tasks": len(questions),
        "task_types": counts,
        "source_documents": len({q["document_id"] for q in questions}),
        "sources": len({q["source"] for q in questions}),
        "dataset_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "contents": "questions_and_source_metadata_only",
        "reference_answers_included": False,
        "additional_generation_or_judging_calls": 0,
        "benchmark_runs_started": 0,
        "source": "existing_synthetic_production_corpus_question_candidates",
        "human_reviewed": False,
    }
    write_json(out / "task_provenance.json", provenance)
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    run()
