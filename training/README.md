# Training configuration

Install Hydra alongside the existing training dependencies:

```sh
python -m pip install 'hydra-core>=1.3,<1.4'
```

All former parser options live in `config.yaml`. Run these commands from the
repository root. Hydra accepts `key=value` overrides instead of `--key value`.
`hub_model_id` is required because each training run uploads its checkpoint to
that Hugging Face repository.

```sh
# Inspect the configuration without loading the model.
python training/main.py --cfg job

# Check loading only, without downloading the tokenizer.
python training/main.py dry_run=true dry_run_tokenize=false dry_run_samples=5

# Also validate the training schema, tokenize, and build a CPU batch per split.
python training/main.py dry_run=true

# Run one training job.
python training/main.py hub_model_id=your-user/your-model epochs=2

# Select a CUDA GPU on the machine running training (default gpu_id=0).
python training/main.py gpu_id=1

# Sweep four combinations of learning rate and seed, sequentially.
python training/main.py --multirun hub_model_id=your-user/your-model \
  lr=5.0e-5,1.0e-4 seed=42,43
```

Training runs on the machine where this command executes. Running Python locally
does not submit an HF Job. The base model is downloaded from the Hub, checkpoints
are saved on the training machine, and the final checkpoint is uploaded to
`hub_model_id` after training and evaluation.

Set `gpu_id` in `config.yaml` or override it on the command line. The backbone,
pointer head, and batches all use this selected CUDA GPU. The index is relative
to devices exposed by `CUDA_VISIBLE_DEVICES`; for example, with
`CUDA_VISIBLE_DEVICES=2`, use `gpu_id=0` to select physical GPU 2. Training fails
early if CUDA or the requested GPU is unavailable. Dataset dry runs remain CPU
compatible and do not require a CUDA GPU.

For remote HF training, select the rented hardware with `hf jobs run --flavor ...`
when launching your packaged training code. That flag chooses the machine;
`gpu_id` chooses a GPU within that machine. A single-GPU HF Job uses `gpu_id=0`.
GPU selection in this configuration does not provision hardware or start billing.

To run on HF Jobs, use the included launcher. It reads `hf_job.flavor`, `timeout`,
`image`, and optional organization `namespace` from `config.yaml`. The default is
one A100 80 GB with a four-hour timeout. Set up compute credits in HF billing,
authenticate with `hf auth login`, and export `WANDB_API_KEY` in your terminal.
The HF token needs permission to submit Jobs and write to `hub_model_id`.

```sh
# Inspect the source package and command without uploading or starting anything.
python training/launch_hf.py --preview

# Submit a paid job with the current config; returns a Job ID.
python training/launch_hf.py

# Override training settings or HF hardware before submission.
python training/launch_hf.py epochs=1 batch_size=4 hf_job.timeout=2h

# Follow logs or stop a running job.
hf jobs logs -f JOB_ID
hf jobs cancel JOB_ID
```

The launcher stages only the listed Python files, `config.yaml`, the pinned HF
requirements, and a job startup script. It excludes `.env`, outputs, caches,
tests, and frontend dependencies. HF uploads that temporary source directory as
a read-only volume; the job copies it into a writable directory, installs the
dependencies, and runs `main.py`. `HF_TOKEN` and `WANDB_API_KEY` are passed by
secret name; the HF CLI resolves their values from your environment (and can
resolve `HF_TOKEN` from `hf auth login`). The launcher does not read `.env`.

The HF requirements use the official Swiss AI Transformers fork pinned in the
[Apertus model card](https://huggingface.co/swiss-ai/Apertus-v1.5-8B-base).
Apertus 1.5 loads through its multimodal model class, with the decision head using
the text configuration's hidden size. Stock Transformers does not currently
support this checkpoint. Other causal-LM checkpoints retain their causal loader.
The full CUDA run and this container's dependency installation still need to be
verified on an HF GPU; local dataset checks do not exercise model loading.

The job pins NumPy 2.2.6 with PyArrow 26.0.0 and requires pandas 2.2.2 or newer.
PyArrow 26's NumPy integration needs NumPy 2+, so leaving the image's NumPy 1.26
installed causes an import error. After dependency installation, startup runs
`pip check` and checks imports plus NumPy-to-Arrow/PyTorch conversion before
downloading model weights or initializing W&B. Relaunch with `launch_hf.py` after
changing requirements; retrying an old Job uses its previously staged source.

The Transformers audio extra is intentionally excluded. Text decision training
does not use ASR decoding, and that extra pulls `pyctcdecode`, which requires
NumPy below 2 and conflicts with PyArrow 26. The torch and vision extras remain
enabled, and the image's torchaudio version stays pinned to match PyTorch.

Startup installs `requirements-hf.lock`, whose complete dependency set was
resolved for Linux x86-64 / Python 3.11. To change dependencies, edit
`requirements-hf.txt`, then regenerate the lock before launching:

```sh
uv pip compile training/requirements-hf.txt \
  --python-version 3.11 --python-platform x86_64-manylinux_2_28 \
  --output-file training/requirements-hf.lock
```

Regenerate for the matching Python/platform if you change the job image. Resolving
the dependency set does not verify CUDA execution; the GPU startup checks still
run in the actual job.

Checkpoints live on the job's temporary disk until the final Hub upload succeeds.
If the job fails or reaches its timeout first, local checkpoints are lost. Mount
an HF Storage Bucket and use it as `output_dir` when checkpoint persistence across
failed jobs is required; the current launcher does not mount one automatically.

Each validation epoch logs a `dev/examples` W&B Table, and final test evaluation
logs `test/examples`. By default, each table contains up to 50 retained question
samples selected with `seed`; repeated validation epochs use the same selection.
Columns include source/example ID, question ID/type, state, question, options,
actual/predicted option text and indices, correct/wrong flag, per-example
cross-entropy loss, confidence, and epoch. Loss and confidence use the logits from
that evaluation (including temperature calibration during the final test).
W&B retains a new table version for each evaluation. Configure the count with
`wandb_eval_examples=50`, or disable example tables with `wandb_eval_examples=0`.

The dataset dry run needs `torch`, `datasets`, `transformers`, and `hydra-core`.
It streams at most `dry_run_samples` rows from each split, reports tokenization
drops and batch tensor shapes when tokenization is enabled, then exits. It does
not load model weights, initialize W&B, train, or upload anything. Source/loading
errors fail the check; the dry run never substitutes synthetic data. The configured
`dataset_data_files` select the actual `v7/decision-v7` JSONL files and map
`development.jsonl` to `dev`. They are file paths, not a Hub configuration named
`decision-v7`. To check a different Hub dataset with named configurations, override
`dataset_repo=... dataset_config=... dataset_data_files=null`. Authenticate
with `hf auth login` first if the dataset or tokenizer is private or gated.

If a tokenizer download fails inside `httpx2/_decoders.py` with
`TypeError: process() takes no keyword arguments`, check your Brotli version.
Recent `httpx2` requires Brotli 1.2+ for its optional Brotli decoder; an older
installed version can cause Transformers to report a misleading model-config
loading error. Upgrade using the same Python interpreter used for training:

```sh
python -m pip install --upgrade 'brotli>=1.2.0,<2'
python training/main.py dry_run=true
```

`dataset.py` expands each nested decision-v7 `questions` object into one training
sample per question. Choice labels map to the insertion order of named criteria;
score labels remain zero-based level indices; noul uses no/yes options with
false/true mapped to 0/1. Structured instructions and descriptions are serialized
as JSON. Source metadata and question IDs are preserved by the adapter but are not
included in the model prompt. Existing flat records are also accepted. Malformed
records and unsupported soft targets raise errors instead of silently losing
training samples. Both dry-run modes validate this adaptation; tokenization mode
also reports dropped question samples and tensor shapes.

Run the adapter and CPU batching regression tests without network access:

```sh
python -m unittest discover -s training -p 'test_*.py' -v
```

Alternatively, set ranges under `hydra.sweeper.params` in `config.yaml` and run
with `--multirun`. A regular invocation runs a single job using the scalar values.

Hydra changes into a separate output directory for each job: `outputs/...` for a
single run or `multirun/.../<job-number>` for a sweep. The default
`./jevpertus_checkpoints` is relative to that directory, so jobs keep separate
checkpoints and W&B artifacts. Each W&B run records the resolved job configuration.

The sweep example uploads every job to the same `hub_model_id`, so later jobs can
overwrite earlier Hub artifacts. To keep them separate, use an interpolated ID,
for example `'hub_model_id=your-user/model-lr-${lr}-seed-${seed}'`.
