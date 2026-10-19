# RAGlette

Built at Hack Apertus for the challenge "Research & Expertise Navigator" (Bern Economic Development Agency).
You chat with an agent (Apertus 70B) about a company, described by the buzzwords of its sales pitch. The agent searches
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

`data/` is not in the repository: crawl, index, traces, conversations and `settings.json` (API key) are local.

## Run

Requirements: Python 3.14 with [uv](https://docs.astral.sh/uv/), Node.js.

```sh
uv sync
cd frontend && npm install && npm run build && cd ..
uv run uvicorn api.main:app --port 8000     # http://localhost:8000
```

Then set the Apertus API (base URL, key, models) under Settings in the UI.

## Build the index

```sh
uv run python scraper/crawl.py sources.yaml data/crawl.sqlite
uv run python indexing/index.py prepare
uv run python indexing/embed.py --device cuda --fp16     # on a GPU machine if possible
uv run python indexing/index.py load
```

The search index (Qdrant, local mode) can only be opened by one process: stop the API while indexing.
