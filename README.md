# RAGlette

Built at Hack Apertus for the challenge "Research & Expertise Navigator" (Bern Economic Development Agency).
You chat with an agent using instruction-tuned Apertus 1.5 8B for generation and our fine-tuned decision model
for action selection and ranking, about a company described by its sales-pitch buzzwords. The agent searches
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

Then configure both the chat API (base URL, key, models) and decision API (URL, key, model)
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

Logs include the exact decision request (state, question, ordered options), the
returned model/revision and probabilities, action-to-probability pairs, full chat
prompts and raw replies (including tool arguments and usage metadata), retrieval
ranking, and complete tool results, including page texts. Requests and results are
written immediately, so a failed or unfinished turn still has a trace. Entries
have session, turn, step and call IDs; repeated calls and errors are recorded too.
Credentials are redacted. The files stay in the gitignored `data/` directory.

For repeated `search` decisions, compare `decision_request.request.state`
(especially `unfinished_step` and `recent_messages`) with `action_selected` and
its `action_probabilities`. Decision context includes 400 request characters,
page/read/item counts, unread/read page numbers, page titles, existing item titles,
and bounded excerpts from the last three messages with roles, tool names and
results. Unfinished reading/composition is carried into a follow-up turn. Chat
context is logged separately in `chat_request` and contains the full conversation
and presentation.

The backend recovers native calls and complete Apertus/OpenAI tool-call JSON,
including fenced JSON and a tool-call suffix after prose. It checks every call
against the decision-selected action and retries incompatible chat output up to
`llm.json_attempts` times. If an attempted answer contains calls, the decision
model gets one reconsideration with `answer` excluded; chat's proposed call is
never executed unless the decision model selects that action. Further formatting
errors are retried. Logs include `generation_rejected` and `decision_reconsidered`.

`read_pages` is available only while unread pages exist. Research started during
a turn must proceed to reading and an `add_items` attempt before answering or
searching again. After one successful reading batch, further reading is excluded
until composition has been attempted, even if more results remain unread. The
last two steps reserve composition of pending research and a final summary.
Chat receives only the selected tool, with current unread page numbers in the
reading schema and read-page citations in the item schema. Identical successful
calls are skipped once and their action is
then excluded for the rest of that turn (`action_blocked` in logs). Failed calls
remain retryable. `action_options` records the eligible actions before each
decision, so probabilities can be interpreted against the actual option set.

Slides use checked items, not search passages: the agent must read retrieved pages
and call `add_items` before the slide preview and PDF have content. Search
passages are hypothetical queries and do not establish facts about institutions
or people. Only items accepted by the evidence checks reach the presentation.

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
