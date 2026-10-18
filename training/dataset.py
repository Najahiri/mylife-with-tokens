
# ==============================================================================
# DATA PROCESSING & TOKENIZATION
# ==============================================================================

import json
from itertools import islice
from numbers import Integral
from typing import List, Dict, Any, Iterable, Iterator

import torch
from torch.utils.data import Dataset, DataLoader
from datasets import load_dataset
from transformers import AutoTokenizer

from constants import DELIMITERS


def _render_text(value: Any) -> str:
    """Retain structured instructions and descriptions as readable JSON."""
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _option_text(name: str, description: Any) -> str:
    text = _render_text(description)
    return f"{name}: {text}" if text else name


def _validate_flat_record(row: Dict[str, Any]) -> None:
    missing = {"state", "question", "options", "label"} - row.keys()
    if missing:
        raise ValueError(f"missing fields {sorted(missing)}")
    options, label = row["options"], row["label"]
    if not isinstance(row["question"], str):
        raise ValueError("question must be a string")
    if not isinstance(options, list) or not options or not all(isinstance(x, str) for x in options):
        raise ValueError("options must be a non-empty list of strings")
    if not isinstance(label, Integral) or isinstance(label, bool) or not 0 <= label < len(options):
        raise ValueError("label must be an integer option index within range")


def adapt_record(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand a Kev request into one flat training record per named question.

    Choice labels name a criteria key; score labels index ordered criteria;
    noul labels map false/true to 0/1. Existing flat records remain supported.
    Source metadata and question IDs stay outside the text sent to the model.
    """
    if not isinstance(row, dict):
        raise ValueError("record must be an object")
    if "questions" not in row:
        _validate_flat_record(row)
        return [dict(row)]
    if "state" not in row:
        raise ValueError("missing field 'state'")
    questions = row["questions"]
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a non-empty object")

    records = []
    for question_id, spec in questions.items():
        # Arrow may add null fields for questions that occur only in other rows.
        if spec is None:
            continue
        try:
            if not isinstance(spec, dict) or "label" not in spec:
                raise ValueError("each question needs an object with a label")
            if spec.get("target") is not None:
                raise ValueError("soft targets are unsupported by the current hard-label training loss")
            kind, label, criteria = spec.get("type"), spec["label"], spec.get("criteria")
            if kind == "choice":
                if not isinstance(criteria, dict) or not criteria:
                    raise ValueError("choice criteria must be a non-empty object")
                keys = list(criteria)
                if not all(isinstance(key, str) for key in keys):
                    raise ValueError("choice option names must be strings")
                if not isinstance(label, str) or label not in criteria:
                    raise ValueError("choice label must name a criteria key")
                options = [_option_text(key, criteria[key]) for key in keys]
                label = keys.index(label)
            elif kind == "score":
                if not isinstance(criteria, list) or not criteria:
                    raise ValueError("score criteria must be a non-empty list")
                keys = [str(index) for index in range(len(criteria))]
                options = [_render_text(level) for level in criteria]
            elif kind == "noul":
                if criteria is None:
                    criteria = {}
                if not isinstance(criteria, dict) or set(criteria) - {"false", "true"}:
                    raise ValueError("noul criteria may only describe false and true")
                if not isinstance(label, (bool, Integral)) or label not in (0, 1):
                    raise ValueError("noul label must be false/true or 0/1")
                keys = ["false", "true"]
                options = [_option_text("no", criteria.get("false")),
                           _option_text("yes", criteria.get("true"))]
                label = int(label)
            else:
                raise ValueError(f"unsupported question type {kind!r}")

            flat = {key: value for key, value in row.items() if key != "questions"}
            flat.update(
                question=_render_text(spec.get("instructions")), options=options, label=label,
                question_id=question_id, question_type=kind, option_keys=keys,
            )
            if "src" in spec:
                flat["src"] = spec["src"]
            _validate_flat_record(flat)
        except ValueError as error:
            raise ValueError(f"question {question_id!r}: {error}") from error
        records.append(flat)
    if not records:
        raise ValueError("record contains no questions")
    return records


def adapt_records(rows: Iterable[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """Adapt a list, HF Dataset, or streamed rows without materializing a split."""
    for index, row in enumerate(rows):
        try:
            yield from adapt_record(row)
        except ValueError as error:
            raise ValueError(f"record {index}: {error}") from error


def load_decision_splits(repo: str, config: str | None, *, data_files=None, streaming: bool = False):
    """Load the configured source and normalize validation/dev split names."""
    raw = load_dataset(repo, config, data_files=data_files, streaming=streaming)
    dev_split = "validation" if "validation" in raw else "dev"
    missing = {"train", dev_split, "test"} - raw.keys()
    if missing:
        raise ValueError(f"Missing dataset splits: {sorted(missing)}; available: {list(raw)}")
    return {"train": raw["train"], "dev": raw[dev_split], "test": raw["test"]}


def check_dataset(cfg) -> None:
    """Check real dataset samples on CPU, without model weights or training services."""
    if cfg.dry_run_samples < 1 or cfg.batch_size < 1:
        raise ValueError("dry_run_samples and batch_size must be positive")
    from omegaconf import OmegaConf

    print(f"Checking {cfg.dataset_repo} (config={cfg.dataset_config})")
    splits = load_decision_splits(
        cfg.dataset_repo, cfg.dataset_config,
        data_files=(OmegaConf.to_container(cfg.dataset_data_files, resolve=True)
                    if cfg.dataset_data_files is not None else None),
        streaming=True,
    )
    tokenizer = None

    for split_name, split in splits.items():
        rows = list(islice(split, cfg.dry_run_samples))
        if not rows:
            raise ValueError(f"{split_name}: split is empty")
        print(f"{split_name}: loaded {len(rows)} sample rows; fields={sorted(rows[0])}")
        try:
            flat_rows = list(adapt_records(rows))
        except ValueError as error:
            raise ValueError(f"{split_name}: {error}") from error
        print(f"  adapted={len(flat_rows)} question samples")
        if not cfg.dry_run_tokenize:
            continue
        
        if tokenizer is None:
            tokenizer = AutoTokenizer.from_pretrained(cfg.model_id, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            tokenizer.add_special_tokens({"additional_special_tokens": list(DELIMITERS.values())})
            
        dataset = DecisionDataset(flat_rows, tokenizer, max_length=cfg.max_length)
        print(f"  tokenized={len(dataset)}, dropped={len(flat_rows) - len(dataset)} "
              f"(missing/truncated delimiters, max_length={cfg.max_length})")
        if not dataset:
            raise ValueError(f"{split_name}: no usable rows after tokenization")
        batch = next(iter(DataLoader(
            dataset, batch_size=cfg.batch_size,
            collate_fn=lambda items: collate_fn(items, tokenizer.pad_token_id),
        )))
        print(f"  batch shapes: { {key: list(value.shape) for key, value in batch.items()} }")
    print("Dataset dry run passed. No training or model upload was performed.")


def format_record(state: Any, question: str, options: List[str]) -> str:
    """Serializes structured state objects and options into Decision model text."""
    if isinstance(state, (dict, list)):
        state_str = json.dumps(state, ensure_ascii=False)
    else:
        state_str = str(state).strip()

    text = f"{DELIMITERS['state']} {state_str} {DELIMITERS['question']} {question.strip()} "
    for opt in options:
        opt_text = str(opt).strip()
        text += f"{DELIMITERS['opt_open']} {opt_text} {DELIMITERS['opt_close']} "
    text += f"{DELIMITERS['decide']}"
    return text


class DecisionDataset(Dataset):
    def __init__(self, data_split, tokenizer: AutoTokenizer, max_length: int = 2048):
        self.samples = []
        # Keep source examples aligned with retained tokenized samples for evaluation tables.
        self.examples = []
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        opt_close_id = tokenizer.convert_tokens_to_ids(DELIMITERS["opt_close"])
        decide_id = tokenizer.convert_tokens_to_ids(DELIMITERS["decide"])

        for row in adapt_records(data_split):
            state = row["state"]
            question = row["question"]
            options = row["options"]
            label = row["label"]

            full_text = format_record(state, question, options)
            encoded = tokenizer(
                full_text,
                truncation=True,
                max_length=max_length,
                return_tensors=None,
            )
            input_ids = encoded["input_ids"]

            # Locate [/OPTION] and [DECIDE] token positions
            opt_positions = [i for i, tok in enumerate(input_ids) if tok == opt_close_id]
            decide_positions = [i for i, tok in enumerate(input_ids) if tok == decide_id]

            if not decide_positions or len(opt_positions) != len(options):
                # Dropped if delimiters were truncated or count mismatched
                continue

            self.samples.append({
                "input_ids": input_ids,
                "attention_mask": encoded["attention_mask"],
                "decide_idx": decide_positions[-1],
                "opt_indices": opt_positions,
                "label": int(label),
            })
            self.examples.append(row)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch: List[Dict[str, Any]], pad_token_id: int) -> Dict[str, torch.Tensor]:
    """Pads sequences and aligns variable-length option indices."""
    max_len = max(len(x["input_ids"]) for x in batch)
    max_k = max(len(x["opt_indices"]) for x in batch)
    B = len(batch)

    padded_ids = torch.full((B, max_len), pad_token_id, dtype=torch.long)
    padded_mask = torch.zeros((B, max_len), dtype=torch.long)
    decide_indices = torch.zeros(B, dtype=torch.long)
    opt_indices = torch.zeros((B, max_k), dtype=torch.long)
    opt_mask = torch.zeros((B, max_k), dtype=torch.bool)
    labels = torch.zeros(B, dtype=torch.long)

    for i, item in enumerate(batch):
        seq_len = len(item["input_ids"])
        padded_ids[i, :seq_len] = torch.tensor(item["input_ids"], dtype=torch.long)
        padded_mask[i, :seq_len] = torch.tensor(item["attention_mask"], dtype=torch.long)
        decide_indices[i] = item["decide_idx"]
        
        k = len(item["opt_indices"])
        opt_indices[i, :k] = torch.tensor(item["opt_indices"], dtype=torch.long)
        opt_mask[i, :k] = True
        labels[i] = item["label"]

    return {
        "input_ids": padded_ids,
        "attention_mask": padded_mask,
        "decide_indices": decide_indices,
        "opt_indices": opt_indices,
        "opt_mask": opt_mask,
        "labels": labels,
    }
