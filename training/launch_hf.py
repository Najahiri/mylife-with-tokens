#!/usr/bin/env python3
"""Submit the training source to HF Jobs; --preview never submits or uploads."""

import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from omegaconf import OmegaConf


SOURCE_FILES = (
    "main.py", "model.py", "backbone.py", "dataset.py", "constants.py", "evaluation.py",
    "requirements-hf.txt", "run_hf_job.sh",
)


def build_job_command(cfg, source_dir, overrides):
    command = [
        "hf", "jobs", "run", "--detach",
        "--flavor", cfg.hf_job.flavor, "--timeout", cfg.hf_job.timeout,
        "--secrets", "HF_TOKEN", "--secrets", "WANDB_API_KEY",
        "--volume", f"{source_dir}:/code:ro",
    ]
    if cfg.hf_job.namespace:
        command.extend(["--namespace", cfg.hf_job.namespace])
    command.extend([cfg.hf_job.image, "--", "bash", "/code/run_hf_job.sh", *overrides])
    return command


def main():
    source_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--preview", action="store_true", help="Print the Job command without uploading or submitting")
    parser.add_argument("--config", type=Path, default=source_dir / "config.yaml")
    args, overrides = parser.parse_known_args()
    cfg = OmegaConf.load(args.config)
    
    # Apply allocation overrides before submitting, rather than only inside training.
    job_overrides = [item for item in overrides if item.startswith("hf_job.") and "=" in item]
    cfg = OmegaConf.merge(cfg, OmegaConf.from_dotlist(job_overrides))
    
    with tempfile.TemporaryDirectory(prefix="apertus-hf-source-") as staged_dir:
        for filename in SOURCE_FILES:
            shutil.copy2(source_dir / filename, Path(staged_dir) / filename)
        OmegaConf.save(cfg, Path(staged_dir) / "config.yaml")
        command = build_job_command(cfg, staged_dir, overrides)
        print("Source files: " + ", ".join((*SOURCE_FILES, "config.yaml")), flush=True)
        print(shlex.join(command), flush=True)
        
        if args.preview:
            print("Preview only. Run again without --preview to submit a paid HF Job.")
            return
        if shutil.which("hf") is None:
            parser.error("hf CLI not found. Install huggingface-hub and run hf auth login.")
            
        subprocess.run(command, check=True)

if __name__ == "__main__":
    main()
