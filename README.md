# RAGlette

Built at Hack Apertus for the challenge "Research & Expertise Navigator" (Bern Economic Development Agency).
You chat with an agent using instruction-tuned Apertus 1.5 8B and 70B, with our fine-tuned decision model
choosing which model handles each LLM call, about a company described by its sales-pitch buzzwords. The agent searches
the indexed websites of Bern's research institutions, reads the matching pages in full and builds a presentation in
the Kanton Bern design, one slide per partner. Every slide is backed by a quote that is checked against its source page.

## Layout

| Folder | What it does |
|---|---|
| `scraper/` | crawls the websites in `sources.yaml` into `data/crawl.sqlite` |
| `indexing/` | Haystack pipeline: clean, split into chunks, embed (BGE-M3), load into Qdrant |
| `rag_model/` | search, the agent loop (`agent.py`), checks, presentation builder |
| `prompts/` | the Apertus prompts (`agent.yaml`, `brief.yaml`, `queries.yaml`) |
| `api/` | FastAPI backend, also serves the built web UI |
| `frontend/` | web UI (React, Vite, Tailwind): chat, slide preview, sources, settings |
| `presentation/template/` | Typst deck: `raglette.typ` on top of the team's `kanton-bern.typ` |
| `config.yaml` | defaults of every parameter; changes are made in the UI (Settings) |
| `tools/apertus_chat.py` | small standalone chat client for the Apertus API |
| `training/` | Apertus decision model definition, fine-tuning, and HF job launcher |
| `serving/` | separate instruction chat and fine-tuned decision APIs, containers, and launch instructions |

For hosting the trained model alongside the agent, see the
[model hosting plan](docs/model-hosting.md).
Build and configure both APIs using the [serving instructions](serving/README.md).

`data/` is not in the repository: crawl, index, traces, conversations and `settings.json` (API key) are local.

## Data

The search index is too large for git. Download it from the release
[raglette-data-v1](https://github.com/Najahiri/mylife-with-tokens/releases/tag/raglette-data-v1) and unzip it into `data/`:

```sh
mkdir -p data && cd data
curl -LO https://github.com/Najahiri/mylife-with-tokens/releases/download/raglette-data-v1/index.sqlite.zip
unzip index.sqlite.zip && rm index.sqlite.zip && cd ..
```

`index.sqlite` holds the pages, the chunks and their BGE-M3 vectors. On the first start the API builds the vector
store `data/qdrant` from it (about a minute) and downloads the embedding model BGE-M3 (about 2 GB) from Hugging Face.
`crawl.sqlite.zip` in the same release is the raw crawl, only needed to rebuild the index without crawling again.

## Run

Requirements: Python 3.14 with [uv](https://docs.astral.sh/uv/), Node.js >=22.22.0
(version recorded in `frontend/.nvmrc`).

```sh
uv sync
cd frontend && npm install && npm run build && cd ..
uv run uvicorn api.main:app --port 8000     # http://localhost:8000
```

Then configure the chat API (base URL, key, 8B and 70B models) and decision API (URL, key, model)
under Settings in the UI. Both are required for the agent.
Stock 8B/70B generation uses CSCS through `https://gateway.keera.ch/api/v1`;
only the fine-tuned decision model needs our own HF endpoint for those options.

The chat includes saved conversations, a stop button, and a slide drawer with PDF and PowerPoint export.
Removed slides can be restored through the agent. Settings keeps generation and decision access separate,
and lets you rebuild and switch the search index without restarting the backend.

## Inspect the pipeline locally

Every chat turn automatically appends to `data/logs/pipeline/<session-id>.log`
(readable text) and `<session-id>.jsonl` (structured events). Restart the backend
after updating the code, then send a message in the frontend. The session ID is
returned when the conversation is created (`POST /api/agent`). To follow the most
recent conversation's log from the project directory:

```sh
tail -f "$(ls -t data/logs/pipeline/*.log | head -1)"
```

Every user turn starts with an LLM assessment of whether new source retrieval is needed. Greetings,
clarifications, general explanations, presentation edits, and answers supported by the existing conversation
can skip retrieval. The agent LLM chooses its own tools; the decision model no longer selects actions or
reranks search results.

Before every pipeline LLM call, including retrieval assessment, agent steps, repairs, query generation,
slide composition and fact checking, the decision service selects the 8B or 70B instruction model.
Both run through the configured chat gateway (normally Keera). Configure their IDs with Settings or
`APERTUS_MODEL_8B` / `APERTUS_MODEL_70B` (defaults `apertus-v1-5-8b` / `apertus-v1-5-70b`).
The router sees the call's purpose, bounded prompt excerpts, context size, and available tools. Its current
checkpoint is reused for this new task; model-routing quality should be evaluated separately from API correctness.

Logs include the exact decision request, ordered model options and probabilities (`model_selected`),
retrieval assessment (`retrieval_assessed`), actual generation model, full prompts and raw replies,
and complete tool results including page texts. Each request and result is written immediately with session,
turn, step and call IDs. Credentials are redacted. Logs stay in the gitignored `data/` directory.

The backend recovers native calls and complete Apertus/OpenAI tool-call JSON, including fenced JSON and
a call suffix after prose. Calls must use an available tool with valid arguments; malformed output is repaired
up to `llm.json_attempts` times. Each repair gets a fresh model-routing decision.

`read_pages` is available only for unread pages and only when the initial assessment allows retrieval.
After a successful reading batch, further research waits for an `add_items` attempt. The last steps reserve
composition and a final summary. Identical successful calls are skipped and their tool is excluded for the
rest of the turn. Failed calls remain retryable. No-retrieval turns can still edit, remove or restore slides.

Slides use checked items, not search passages: the agent must read retrieved pages
and call `add_items` before the slide preview and PDF have content. Search
passages are hypothetical queries and do not establish facts about institutions
or people. Only items accepted by the evidence checks reach the presentation.

Facts are verified by a separate LLM call, independently routed to 8B or 70B, with only the
item's cited page texts as evidence. Supported paraphrases are kept; unsupported facts are removed with
the checker's reason. Evidence quotations still require a source-text match. Fact-check prompts, replies
and verdicts appear in the local pipeline logs. Invalid checker output is retried up to `llm.json_attempts`;
if verification fails, the item is not added. Existing saved slides keep their original results until regenerated.

Malformed tool-call JSON triggers regeneration instead of becoming an answer in
chat. `add_items` accepts at most five items per call; each item must match the
slide schema, include an evidence quote, and cite pages already read. Nested slide
objects inside `contacts` are rejected. Repair attempts are bounded by
`llm.json_attempts`; if they fail, the UI receives an error rather than raw JSON.

The HF decision endpoint can sleep after 15 idle minutes. While a replica starts,
HF can return HTTP 503. The backend sends `X-Scale-Up-Timeout` and retries 503
responses with backoff within the decision request's timeout (300 seconds by
default). Waits appear as `decision_wait` in the local pipeline logs. If it remains
unavailable, the error asks you to inspect the HF endpoint status and container
logs. Authentication and invalid-input errors fail immediately.

## Build the index yourself

Only needed for other websites or a fresh crawl.

```sh
uv run python scraper/crawl.py sources.yaml data/crawl.sqlite --max-pages 5000   # pages per website, unless sources.yaml sets max_pages
uv run python indexing/index.py prepare
uv run python indexing/embed.py --device cuda --fp16     # on a GPU machine if possible
uv run python indexing/index.py load
```

Crawling takes hours (one request per second per website). Embedding all chunks takes minutes on a GPU and many
hours on a CPU (about one chunk per second). The search index (Qdrant, local mode) can only be opened by one process:
stop the API while indexing.
