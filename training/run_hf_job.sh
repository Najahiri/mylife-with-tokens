#!/usr/bin/env bash
set -euo pipefail

# The submitted source volume is read-only; Hydra needs a writable working copy.
job_source_dir=/tmp/apertus-training
mkdir -p "$job_source_dir"
cp -R /code/. "$job_source_dir/"
cd "$job_source_dir"

if ! command -v git >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends git
fi
python -m pip install -r requirements-hf.lock
python -m pip check

# Check compiled extensions and model-class support before model downloads or W&B.
python - <<'PY'
import numpy as np
import pyarrow as pa
import pandas as pd
import datasets
import torch
import peft
from transformers import AutoModelForMultimodalLM
from model import ApertusDecisionModel
from dataset import DecisionDataset

values = np.array([0, 1], dtype=np.int64)
assert pa.array(values).to_pylist() == [0, 1]
assert torch.from_numpy(values).tolist() == [0, 1]
print(f"HF environment check passed: NumPy {np.__version__}, PyArrow {pa.__version__}, "
      f"pandas {pd.__version__}, datasets {datasets.__version__}, torch {torch.__version__}", flush=True)
PY
exec python main.py "$@"
