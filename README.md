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

Requirements: Python 3.14 with [uv](https://docs.astral.sh/uv/), Node.js.

```sh
uv sync
cd frontend && npm install && npm run build && cd ..
uv run uvicorn api.main:app --port 8000     # http://localhost:8000
```

Then set the Apertus API (base URL, key, models) under Settings in the UI.

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
