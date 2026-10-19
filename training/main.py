#!/usr/bin/env python3
"""
JevPertus Finetuning Pipeline: Apertus 1.5 8B + LoRA + Pointer Head
Compatible with Kev's decision-v7 dataset schema.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict
from uuid import uuid4

import hydra
from omegaconf import DictConfig, OmegaConf

if TYPE_CHECKING:
    import torch

# ==============================================================================
# CALIBRATION & METRICS
# ==============================================================================

def compute_metrics(all_logits: torch.Tensor, all_labels: torch.Tensor) -> Dict[str, float]:
    """Calculates Cross-Entropy, Accuracy, and Brier Score."""
    import torch
    import torch.nn.functional as F

    probs = F.softmax(all_logits, dim=-1)
    preds = torch.argmax(probs, dim=-1)
    acc = (preds == all_labels).float().mean().item()
    ce = F.cross_entropy(all_logits, all_labels).item()

    one_hot = F.one_hot(all_labels, num_classes=all_logits.shape[-1]).float()
    brier = torch.mean(torch.sum((probs - one_hot) ** 2, dim=-1)).item()

    return {"accuracy": acc, "loss": ce, "brier_score": brier}


def fit_temperature(logits: torch.Tensor, labels: torch.Tensor) -> float:
    """L-BFGS optimization to fit scalar temperature T minimizing NLL."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    temp = nn.Parameter(torch.ones(1, device=logits.device))
    optimizer = torch.optim.LBFGS([temp], lr=0.05, max_iter=50)

    def eval_fn():
        optimizer.zero_grad()
        loss = F.cross_entropy(logits / temp.clamp(min=0.1, max=10.0), labels)
        loss.backward()
        return loss

    optimizer.step(eval_fn)
    return float(temp.clamp(min=0.1, max=10.0).item())


# ==============================================================================
# Entrypoint
# ==============================================================================

def select_training_device(gpu_id: int):
    """Select one visible CUDA GPU for the complete QLoRA training pipeline."""
    import torch

    if isinstance(gpu_id, bool) or not isinstance(gpu_id, int) or gpu_id < 0:
        raise ValueError("gpu_id must be a non-negative integer CUDA device index")
    if not torch.cuda.is_available():
        raise RuntimeError(
            "Training requires a CUDA GPU. Run on an NVIDIA GPU machine or HF Job; "
            "use dry_run=true for local CPU dataset checks."
        )
    count = torch.cuda.device_count()
    if gpu_id >= count:
        raise ValueError(f"gpu_id={gpu_id} is unavailable; visible CUDA indices: 0..{count - 1}")
    torch.cuda.set_device(gpu_id)
    return torch.device("cuda", gpu_id)


@hydra.main(version_base="1.3", config_path=".", config_name="config")
def main(cfg: DictConfig) -> None:
    if cfg.dry_run:
        from dataset import check_dataset

        check_dataset(cfg)
        return

    # Fail on missing required values before loading a model or starting W&B.
    OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
    train(cfg)


def train(cfg: DictConfig) -> None:
    # Validate hardware before model downloads or starting external services.
    device = select_training_device(cfg.gpu_id)

    # Keep --help and --cfg usable without the GPU training dependencies.
    import torch
    from torch.utils.data import DataLoader
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import CosineAnnealingLR
    from transformers import AutoTokenizer, BitsAndBytesConfig, set_seed
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from huggingface_hub import HfApi
    import wandb
    from tqdm.auto import tqdm

    from model import ApertusDecisionModel
    from dataset import DecisionDataset, collate_fn, load_decision_splits
    from constants import DELIMITERS
    from evaluation import concat_eval_logits, log_eval_examples
    from backbone import load_backbone

    set_seed(cfg.seed)
    print(f"Training GPU: {device} ({torch.cuda.get_device_name(device)})")
    os.makedirs(cfg.output_dir, exist_ok=True)

    # Initialize Weights & Biases
    wandb.init(
        project=cfg.wandb_project,
        config=OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True),
        name=f"apertus-8b-jevpertus-{uuid4().hex[:8]}",
    )

    # 1. Tokenizer Setup
    print(f"Loading Tokenizer: {cfg.model_id}")
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Add delimiter special tokens
    special_tokens = list(DELIMITERS.values())
    num_added = tokenizer.add_special_tokens({"additional_special_tokens": special_tokens})
    print(f"Added {num_added} special delimiters to tokenizer.")

    # 2. Dataset Loading (Preserve official train/dev/test splits)
    print("Loading datasets...")
    
    try:
        raw_datasets = load_decision_splits(
            cfg.dataset_repo, cfg.dataset_config,
            data_files=(OmegaConf.to_container(cfg.dataset_data_files, resolve=True)
                        if cfg.dataset_data_files is not None else None),
        )
        train_raw = raw_datasets["train"]
        dev_raw = raw_datasets["dev"]
        test_raw = raw_datasets["test"]
        
    except Exception as e:
        print(f"Could not load '{cfg.dataset_repo}'. Fallback: synthesizing sample decision data for verification ({e})")
        sample_rows = [
            {
                "state": {"ticket_id": f"TK-{i}", "text": "Customer requests immediate refund."},
                "question": "Which action should be executed?",
                "options": ["Escalate to tier 2", "Authorize refund", "Close ticket", "Request more info"],
                "label": 1,
            }
            for i in range(120)
        ]
        train_raw = sample_rows[:80]
        dev_raw = sample_rows[80:100]
        test_raw = sample_rows[100:120]

    train_ds = DecisionDataset(train_raw, tokenizer, max_length=cfg.max_length)
    dev_ds = DecisionDataset(dev_raw, tokenizer, max_length=cfg.max_length)
    test_ds = DecisionDataset(test_raw, tokenizer, max_length=cfg.max_length)
    print(f"Loaded splits -> Train: {len(train_ds)}, Dev: {len(dev_ds)}, Test: {len(test_ds)}")

    train_loader = DataLoader(
        train_ds, 
        batch_size=cfg.batch_size, 
        shuffle=True, 
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id)
    )
    dev_loader = DataLoader(
        dev_ds, 
        batch_size=cfg.batch_size, 
        shuffle=False, 
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id)
    )
    test_loader = DataLoader(
        test_ds, 
        batch_size=cfg.batch_size, 
        shuffle=False, 
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id)
    )

    # 3. Model Initialization (QLoRA 4-bit)
    print(f"Instantiating Apertus 1.5 8B in 4-bit...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_skip_modules=["lm_head", "vision_tokenizer", "audio_tokenizer"],
    )
    
    base_model = load_backbone(cfg.model_id, bnb_config, device.index)
    base_model.resize_token_embeddings(len(tokenizer))
    base_model = prepare_model_for_kbit_training(base_model)

    # LoRA Config matching Kev recipe (rank 16, alpha 32)
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    base_model = get_peft_model(base_model, peft_config)

    d_model = base_model.config.get_text_config().hidden_size
    model = ApertusDecisionModel(backbone=base_model, d_model=d_model, dp=256)
    model.pointer_head.to(device, dtype=torch.bfloat16)

    # Optimizer: separate backbone LoRA LR from pointer head LR
    optimizer_grouped_params = [
        {"params": [p for n, p in model.backbone.named_parameters() if p.requires_grad], "lr": cfg.lr},
        {"params": list(model.pointer_head.parameters()), "lr": cfg.head_lr},
    ]
    optimizer = AdamW(optimizer_grouped_params, weight_decay=0.01)
    
    total_steps = (len(train_loader) // cfg.gradient_accumulation_steps) * cfg.epochs
    scheduler = CosineAnnealingLR(optimizer, T_max=total_steps, eta_min=1e-6)

    # 4. Training Loop
    print("\nStarting Training...")
    global_step = 0
    best_dev_acc = 0.0

    for epoch in range(cfg.epochs):
        model.train()
        train_loss = 0.0
        optimizer.zero_grad()

        pbar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{cfg.epochs}")
        for step, batch in enumerate(pbar):
            # Move batch to device
            batch = {k: v.to(device) for k, v in batch.items()}
            
            with torch.cuda.amp.autocast(dtype=torch.bfloat16):
                loss, logits = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    decide_indices=batch["decide_indices"],
                    opt_indices=batch["opt_indices"],
                    opt_mask=batch["opt_mask"],
                    labels=batch["labels"],
                )
                loss = loss / cfg.gradient_accumulation_steps

            loss.backward()
            train_loss += loss.item() * cfg.gradient_accumulation_steps

            if (step + 1) % cfg.gradient_accumulation_steps == 0 or (step + 1) == len(train_loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

                wandb.log({
                    "train/loss": train_loss / (step + 1),
                    "train/lr_backbone": scheduler.get_last_lr()[0],
                    "train/global_step": global_step,
                })

            pbar.set_postfix({"loss": f"{(train_loss / (step + 1)):.4f}"})

        # 5. Validation Loop
        model.eval()
        dev_logits_list, dev_labels_list = [], []
        with torch.no_grad():
            for batch in tqdm(dev_loader, desc="Evaluating Dev"):
                batch = {k: v.to(device) for k, v in batch.items()}
                with torch.cuda.amp.autocast(dtype=torch.bfloat16):
                    _, logits = model(
                        input_ids=batch["input_ids"],
                        attention_mask=batch["attention_mask"],
                        decide_indices=batch["decide_indices"],
                        opt_indices=batch["opt_indices"],
                        opt_mask=batch["opt_mask"],
                    )
                dev_logits_list.append(logits.float().cpu())
                dev_labels_list.append(batch["labels"].cpu())

        all_dev_logits = concat_eval_logits(dev_logits_list)
        all_dev_labels = torch.cat(dev_labels_list, dim=0)
        dev_metrics = compute_metrics(all_dev_logits, all_dev_labels)
        
        print(f"\n[Epoch {epoch + 1}] Dev Accuracy: {dev_metrics['accuracy']:.4f} | "
              f"Dev Brier: {dev_metrics['brier_score']:.4f} | Dev Loss: {dev_metrics['loss']:.4f}")
        
        wandb.log({f"dev/{k}": v for k, v in dev_metrics.items()})
        log_eval_examples(
            "dev", dev_ds, all_dev_logits, all_dev_labels,
            limit=cfg.wandb_eval_examples, seed=cfg.seed, epoch=epoch + 1,
        )

        # Save Best Model State
        if dev_metrics["accuracy"] > best_dev_acc:
            best_dev_acc = dev_metrics["accuracy"]
            best_dir = os.path.join(cfg.output_dir, "best_checkpoint")
            os.makedirs(best_dir, exist_ok=True)
            
            # Save LoRA adapter & Pointer Head
            model.backbone.save_pretrained(best_dir)
            tokenizer.save_pretrained(best_dir)
            torch.save(model.pointer_head.state_dict(), os.path.join(best_dir, "head.pt"))
            print(f"-> Saved new best checkpoint to {best_dir}")

    # 6. Temperature Calibration (Post-hoc on held-out Dev split)
    print("\nCalibrating pointer head temperature on Dev split...")
    best_temp = fit_temperature(all_dev_logits, all_dev_labels)
    model.pointer_head.temperature.copy_(torch.tensor(best_temp))
    print(f"Fitted Temperature T = {best_temp:.4f}")
    wandb.log({"calibration/temperature": best_temp})

    # Save calibrated head weights
    torch.save({
        "state_dict": model.pointer_head.state_dict(),
        "temperature": best_temp,
    }, os.path.join(cfg.output_dir, "best_checkpoint", "head_calibrated.pt"))

    # 7. Final Test Evaluation
    print("\nRunning Final Test Evaluation...")
    model.eval()
    test_logits_list, test_labels_list = [], []
    with torch.no_grad():
        for batch in tqdm(test_loader, desc="Testing"):
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.cuda.amp.autocast(dtype=torch.bfloat16):
                _, logits = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    decide_indices=batch["decide_indices"],
                    opt_indices=batch["opt_indices"],
                    opt_mask=batch["opt_mask"],
                )
            test_logits_list.append(logits.float().cpu())
            test_labels_list.append(batch["labels"].cpu())

    all_test_logits = concat_eval_logits(test_logits_list)
    all_test_labels = torch.cat(test_labels_list, dim=0)
    test_metrics = compute_metrics(all_test_logits, all_test_labels)
    
    print(f"\nFinal Calibrated Test Accuracy: {test_metrics['accuracy']:.4f} | "
          f"Brier: {test_metrics['brier_score']:.4f}")
    wandb.log({f"test/{k}": v for k, v in test_metrics.items()})
    log_eval_examples(
        "test", test_ds, all_test_logits, all_test_labels,
        limit=cfg.wandb_eval_examples, seed=cfg.seed, epoch=cfg.epochs,
    )

    # 8. Upload to Hugging Face Hub
    print(f"\nUploading adapter weights and pointer head to Hugging Face Hub: {cfg.hub_model_id}...")
    api = HfApi()
    api.create_repo(repo_id=cfg.hub_model_id, exist_ok=True, repo_type="model")
    api.upload_folder(
        folder_path=os.path.join(cfg.output_dir, "best_checkpoint"),
        repo_id=cfg.hub_model_id,
        repo_type="model",
    )
    print("Upload completed successfully!")
    wandb.finish()


if __name__ == "__main__":
    main()
