"""Evaluation utilities for variable option counts and inspectable W&B predictions."""

import json
import random

import torch
import torch.nn.functional as F


def concat_eval_logits(batches):
    """Pad absent options before concatenating batches with different widths."""
    width = max(batch.shape[1] for batch in batches)
    return torch.cat([
        F.pad(batch, (0, width - batch.shape[1]), value=-1e9)
        for batch in batches
    ], dim=0)


def prediction_rows(examples, logits, labels, *, limit=50, seed=42, epoch=None):
    """Sample stable, aligned evaluation examples and calculate their individual losses."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("wandb_eval_examples must be a non-negative integer")
    if len(examples) != logits.shape[0] or len(examples) != len(labels):
        raise ValueError("evaluation examples, logits, and labels must have matching lengths")

    indices = sorted(random.Random(seed).sample(range(len(examples)), min(limit, len(examples))))
    rows = []
    for index in indices:
        example = examples[index]
        options = example["options"]
        actual = int(labels[index].item())
        if actual != example["label"]:
            raise ValueError("evaluation labels do not match source example order; use shuffle=False")
        if logits.shape[1] < len(options):
            raise ValueError("evaluation logits have fewer columns than the source options")
        # Exclude padding options from both confidence and per-example cross entropy.
        scores = logits[index, :len(options)].detach().float().cpu()
        probabilities = scores.softmax(dim=-1)
        predicted = int(probabilities.argmax().item())
        loss = F.cross_entropy(scores.unsqueeze(0), torch.tensor([actual])).item()
        metadata = example.get("_meta") or {}
        rows.append({
            "epoch": epoch,
            "example_id": str(metadata.get("id", index)),
            "question_id": example.get("question_id", ""),
            "question_type": example.get("question_type", ""),
            "state": json.dumps(example["state"], ensure_ascii=False)
                     if not isinstance(example["state"], str) else example["state"],
            "question": example["question"],
            "options": json.dumps(options, ensure_ascii=False),
            "actual_index": actual,
            "actual": options[actual],
            "prediction_index": predicted,
            "prediction": options[predicted],
            "correct": predicted == actual,
            "loss": loss,
            "confidence": float(probabilities[predicted].item()),
        })
    return rows


def log_eval_examples(split, dataset, logits, labels, *, limit=50, seed=42, epoch=None):
    """Log a fresh table for each evaluation so W&B retains its versions."""
    rows = prediction_rows(dataset.examples, logits, labels, limit=limit, seed=seed, epoch=epoch)
    if not rows:
        return
    import wandb

    columns = list(rows[0])
    table = wandb.Table(columns=columns, data=[[row[column] for column in columns] for row in rows])
    wandb.log({f"{split}/examples": table})
