# Two independent model APIs

## Start the decision service on HF

From the repository root, with Docker Desktop running, replace `YOUR_DOCKER_USER`
with your Docker Hub username. The image must be accessible to HF (these commands
assume a public image):

```sh
docker login
docker build --platform linux/amd64 -f serving/Dockerfile.decision \
  -t YOUR_DOCKER_USER/apertus-decision:v1 .
docker push YOUR_DOCKER_USER/apertus-decision:v1
```

Generate the decision API key in the terminal you will also use for the backend.
The helper uses `HF_TOKEN` or your cached `hf auth login` token for HF access.
The Keera key is separate and stays with the backend:

```sh
export DECISION_API_KEY="$(openssl rand -hex 32)"
uv run python -m serving.start_decision --image YOUR_DOCKER_USER/apertus-decision:v1
```

That command only previews. To create the paid L4 decision endpoint (approximately
$0.80 per active hour at the checked rate), explicitly add `--deploy`:

```sh
uv run python -m serving.start_decision --image YOUR_DOCKER_USER/apertus-decision:v1 --deploy
hf endpoints describe apertus-decision-8b --namespace HX-Tfd
```

Wait for the endpoint to be running and copy its URL from HF. The network endpoint
is publicly reachable, while `/decide` requires the generated decision API key.
The backend sends it in `X-Decision-API-Key`, separately from gateway authentication.
Bearer authentication is also accepted for existing clients.
Set backend variables in the same terminal and restart the backend:

```sh
export APERTUS_DECISION_URL="https://YOUR-HF-ENDPOINT/decide"
export APERTUS_DECISION_API_KEY="$DECISION_API_KEY"
uv run uvicorn api.main:app --port 8000
```

This creates one decision endpoint only; stock chat continues through Keera.
The startup helper's deployment call is covered with mocks; actual container
startup and GPU inference still need a live smoke test.

## Available configurations

Three pinned HF deployment options are available in [profiles/](profiles/).
See [HF hosting options and the allowance check](../docs/hf-hosting-options.md).
The fine-tuned generation option shares the adapter-loaded backbone between both
APIs; stock instruction 8B and 70B generation uses CSCS through Keera at
`https://gateway.keera.ch/api/v1`, with aliases `apertus-v1-5-8b` and
`apertus-v1-5-70b`. Only the fine-tuned decision model needs an HF endpoint for
these stock options. No chat container build or HF generation GPU is needed.

| Service | Weights | HTTP interface |
| --- | --- | --- |
| Stock chat | Keera `apertus-v1-5-8b` or `apertus-v1-5-70b` | Existing gateway `/api/v1/models`, `/api/v1/chat/completions` |
| Decision | `HX-Tfd/Apertus-1.5-8B-Decision` adapter + saved pointer head | `/health`, `/decide` |

Chat writes text and tool arguments. Decision scores the supplied options. The
decision adapter was trained on the `-base` backbone, so its loader reads that
backbone from `adapter_config.json`; it does not attach it to the chat model.
In the separate-endpoint options each service loads its own weights and has its own API key. The Hub token used
to download weights is separate from these API keys.

For optional self-hosting only, the chat launcher follows the [official model card](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)
and uses Swiss AI's vLLM fork/image with the Apertus tool parser. Thinking mode
is left off so tool calling is supported. Set `CHAT_REVISION` to pin model weights
and override the `CHAT_IMAGE` Docker build argument with an image digest for a
repeatable deployment. Image builds and GPU execution remain unverified locally.

## Build and run

Build from the repository root. The serving environments are independent of the
Python >=3.14 application environment.
The decision image installs `serving/requirements.lock`, resolved for Linux
x86-64/Python 3.11, preserving the training dependency pins. Regenerate after
changing `serving/requirements.txt`:

```sh
uv pip compile serving/requirements.txt --python-version 3.11 \
  --python-platform x86_64-manylinux_2_28 --output-file serving/requirements.lock
```

```sh
docker build -f serving/Dockerfile.chat -t apertus-chat .
docker build -f serving/Dockerfile.decision -t apertus-decision .
```

Skip the chat image for the stock presets: CSCS already serves those models
through Keera. The chat build/run commands below are optional self-hosting examples.

Run these on separate GPU hosts, or explicitly allocate different GPUs on the
same host. Both examples use all GPUs visible to their container. Supply secrets
through environment variables or the hosting platform's secret settings.

```sh
# Chat host: set HF_TOKEN and CHAT_API_KEY in the host environment first.
docker run --gpus all -p 8001:8000 --env HF_TOKEN --env CHAT_API_KEY apertus-chat

# Decision host: set HF_TOKEN, DECISION_API_KEY, and the exact checkpoint commit.
docker run --gpus all -p 8002:8000 \
  --env HF_TOKEN --env DECISION_API_KEY --env DECISION_REVISION \
  --env DECISION_MODEL_ID=HX-Tfd/Apertus-1.5-8B-Decision \
  --env DECISION_SUBFOLDER= apertus-decision
```

Start with one GPU per service and measure memory, latency, and concurrency.
The chat context defaults to 8192 tokens (`CHAT_MAX_MODEL_LEN`). Decision context
defaults to the training length, 2048 (`DECISION_MAX_LENGTH`), with 4-bit loading
and one inference request at a time. Do not assume both models fit one GPU.

Decision inference restores the saved tokenizer, resized embeddings, LoRA adapter,
and `head.pt`, and returns the resolved Hub commit and base-model commit with
each prediction. `DECISION_BASE_REVISION` can pin the backbone independently.
It intentionally uses the matching uncalibrated `head.pt`, not the potentially
mismatched final `head_calibrated.pt` described in the hosting plan.

For the stock presets, build/push the decision image and create just the decision
HF endpoint. Optional self-hosted generation would need its own endpoint.
Set port 8000 and health route `/health`. The optional chat image
uses vLLM's health route. For mounted HF artifacts, set `CHAT_MODEL_PATH=/repository`
on chat and `DECISION_MODEL_PATH=/repository` on decision. The decision endpoint's
mounted revision must match `DECISION_REVISION`, which must be a full commit SHA.
The decision base model is downloaded separately using `HF_TOKEN`.
The decision service accepts `X-Decision-API-Key` so application authentication
does not depend on the hosting gateway forwarding `Authorization`. The backend
also sends the same key as Bearer for compatibility with older service images.
The supplied decision deployment uses a public gateway and authenticates in the
container; a protected HF gateway would additionally need its own HF credential.

## Configure RAGlette

Use Settings in the frontend or set these backend environment variables:

```sh
export APERTUS_BASE_URL=https://gateway.keera.ch/api/v1
export APERTUS_API_KEY=your-keera-key
export APERTUS_CHAT_MODEL=apertus-v1-5-8b
export APERTUS_DECISION_URL=https://your-decision-service/decide
export APERTUS_DECISION_API_KEY=your-decision-key
export APERTUS_DECISION_MODEL=HX-Tfd/Apertus-1.5-8B-Decision
```

Existing `model_queries`, `model_brief`, and `model_agent` settings remain explicit
overrides. Set all three to `apertus-v1-5-8b` (or `apertus-v1-5-70b`) in Settings.
Known HF stock model names are mapped to Keera aliases only when using the Keera
URL. Custom model endpoints keep their own model names. Connection testing includes decision inference
when its URL is configured. Both API keys are omitted from settings responses.

The agent uses the decision endpoint at every step to choose the next tool or
`answer`. Chat then generates exactly one selected tool's arguments, or a final
answer with tool calling disabled. Calls to a different tool are rejected before
execution. Search results are reranked with the decision model: the first eight
retrieved pages form a shortlist, and the remaining pages retain retrieval order.
`agent.rank_candidates` controls the shortlist size (2–8). Empty/single-result
searches skip scoring. Each action choice and ranking records model revisions and
probabilities in the existing session traces. There is no chat-only fallback if
the decision API is missing or fails.

Custom pipeline code can also call the decision client independently:

```python
from rag_model.decision import decide

result = decide(
    state={"request": "Find a research partner", "candidates": []},
    question="Which candidate should we inspect next?",
    options=["Candidate A", "Candidate B", "Search again"],
)
selected_index = result["prediction_index"]
```

The decision endpoint accepts the same JSON body, with an optional `model` name
check. It returns `prediction_index`, `prediction`, `probabilities` (input order),
`model`, `revision`, `subfolder`, `base_model`, and `base_revision`. It rejects
empty options, mismatched models, conflicting delimiters, and overlength inputs;
it never truncates away the decision token. No target label is required.

Decision context uses bounded excerpts of the user request, recent messages, and
candidate descriptions to fit the training context. Validate end-to-end quality
on representative agent tasks; generic decision-v7 accuracy does not establish
action-selection or partner-ranking quality in this application.

## Local checks without weights or paid hosting

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s training -p 'test_*.py' -q
```

API tests use fake inference and HTTP responses; they do not establish GPU loading,
live tool-parser compatibility, or prediction quality of the real checkpoint.
