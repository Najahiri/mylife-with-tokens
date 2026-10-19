# RAGlette pitch deck: handoff

This is the state of the pitch deck for **RAGlette** (Hack Apertus, team *Mylife with Tokens*: Daniele, Han, Marc) as of 2026-10-19, and what you need to keep working on it.

## Where the deck lives

- **Live deck (source of truth since 2026-10-19):** https://claude.ai/artifact/LjXY2Q3CYjX8XjoizWVMKc
  - It is a Claude artifact of the type "Slides", owned by Daniele's account (najahiri@gmail.com).
  - It is a copy of Marc's deck (https://claude.ai/artifact/DF5dWwQ6cRKhW765f9QU1T, version 1792400666-abd4). Daniele's account could read Marc's deck but not edit it. Marc's deck is no longer updated.
  - It is private. Only the owner can share it, from the page's Share menu. An agent cannot share it.
- **Snapshot in this repo:** `pitch/deck/project/` holds `deck.json` and `slides/*.html`, copied at handoff time.
  - The user also edits the deck by hand in the slide editor, so the snapshot can be behind.
  - **Always read the live files first** before you change anything.
- **Video for slide 2:** `pitch/deck/raglette-demo.mp4` (local copy) and its still frame `raglette-demo-still.jpg`. Both are already uploaded to the deck (see Assets).

## How to edit the deck (artifact mechanics)

1. **Read the live file.** Use `Artifact` with `action: "read"`, the deck `url`, and `path` set to `project/slides/<id>.html`; `paths` reads several at once. The saved copy lands under `<scratchpad>/artifact-files/<uuid>/project/...`.
2. **Edit a copy.**
   - Work in one root folder, for example `<scratchpad>/pitch/`, with the same layout: `project/deck.json` and `project/slides/<id>.html`.
   - Make the edit with a file tool or a small Python script.
   - **Do not use the `edits` parameter of the Artifact publish call.** A hook in this environment refuses it.
3. **Publish only the changed files.**
   - Set `url` to the deck, `root` to your folder, and `file_path` to the absolute path of one changed file.
   - Pass the other changed files in `files` as `{"project/slides/x.html": "project/slides/x.html"}`.
   - Send `deck.json` only when the order, title, sections or fonts change.
4. **If a publish is refused** because someone saved in the meantime, re-read the files it names, redo the edit on them, and publish again.
5. **Assets** (images, video): publish with `asset: true` and use the returned `/_blob/<id>` verbatim. Delete an asset only when it is replaced and nothing references it.

### Slide format rules

- Each slide is one `<section id="…">` on a 1920×1080 canvas, with inline styles only.
- Allowed: px units, `<x-shape>`, `<x-icon>`, `<x-connector x1 y1 x2 y2>`, `<x-embed>` (sandboxed live HTML, ≤16 KB), and inline `<svg>` (≤52 KB, no `<text>`).
- Use at least 24 px text everywhere.
- Animations:
  - `data-build-in="fade|rise|pop N auto"` goes on pinned elements.
  - **The user wants everything to appear automatically**, so always add `auto` and never wait for a click.
- Video: `<img src="/_blob/<still>" data-video="/_blob/<clip>">`. It plays in a loop when the slide is presented. In the editor it plays only after a click.
- Magic move between slides uses the same `id` on matching pinned elements: `mark` (the RAGlette wordmark) and `bar` (the red progress bar).
- The full reference is in the artifact under `artifact-type/reference/*.md`, especially `format.md` and `diagrams.md`.

## Design system (copied from the RAGlette web UI, which the user asked for)

| Token | Value |
|---|---|
| Navy (header band, dark panels) | `#0E1C2F` |
| Heading navy | `#082F5E` |
| Red accent | `#E50611` |
| Cream panels | `#F7F4EE` |
| Body text | `#4A4A4A` |
| Muted text | `#5C5C5C` |
| Light text on navy | `#C9D1DC` |
| Muted nav | `#A9B1BD` |
| Headings font | Abhaya Libre 800 |
| Text font | Inter |

- **Header band on every slide** (pinned, identical markup):
  - navy band, 120 px high;
  - small wordmark "**RAG**lette" with RAG in red (`id="mark"`);
  - nav "01 PROBLEM · 02 HOW IT WORKS · 03 MERCI": the active item is white with a red underline;
  - "BUILT AT HACK APERTUS" on the right;
  - the red bar `id="bar"` at `top:114px`.
- **Bar width per slide:** 480 → 960 → 1440 → 1920 px. It grows like a progress bar through the magic transition.
- **Background animation:** slides 1 and 4 have an `<x-embed>` canvas with drifting nodes that link and unlink, the same as the web app background.
  - The embed's `<html>` and `<body>` must be painted in the slide colour: white on slides 1 and 4.
  - A transparent embed once rendered the whole of slide 4 white.
- **Card style:** cream, `border-radius:24px`, a navy number square, an Abhaya heading.
- **Red is reserved for real emphasis.** The user objected to a red "Sovereignty" card for no reason.

## The case (what the pitch must answer)

**Challenge:** Bern Economic Development Agency, "Research & Expertise Navigator".

- **The problem:** expertise is spread across faculty, institute, research-group, centre, researcher and project pages. People must know *where* to look before *what*, and the terminology differs: "glucose sensors" vs. CGM, biosensing, wearable sensing.
- **The goal:** one natural-language and keyword search over the public sources.
- **The sources:** the UniBE subdomain ecosystem, ARTORG and the Diabetes Center Berne. The design must be easy to extend.

**RAGlette's answer:**

- You chat with an agent: Apertus 70B with tools, via an OpenAI-compatible gateway.
- It searches a local index of 41 websites: HyDE passages, embedded with BGE-M3 and searched in Qdrant by meaning (no keyword/BM25 search), with RRF across passages.
- It reads full pages and composes items: research groups, infrastructure, programmes, networks, education, contacts.
- Plain code checks every quote and fact against its page.
- Typst renders the slides in the Kanton Bern design (PDF/PPTX), with a preview next to the chat.
- The user has the last word: they can remove, restore or edit items in the chat.

## Current slides (state at handoff)

1. **cover**
   - Large "RAGlette" wordmark with a tagline: "Ask in your own words. RAGlette finds the people and expertise across Bern’s research websites, with the source for every hit."
   - Under it the tagline (Abhaya, 88 px, one line): "Cheesy name, solid sources." with "solid sources." in red. The user chose it.
   - The SVG raclette logo was removed at the user's request (2026-10-19). Taglines they turned down: "What Bern brings to the table" and "Hungry for expertise? …".
   - Footer columns:
     - TEAM: "Mylife with Tokens / Daniele, Han, Marc", which the user typed on two lines;
     - CHALLENGE;
     - EVENT: Hack Apertus.
2. **problem**
   - Headline: "A **company** with a need. / **Research** that could meet it."
     - The heading is Abhaya at weight 500, with only "company" and "Research" in bold (700). The user asked for this.
     - That is why `deck.json` loads Abhaya at weights 500;600;700;800.
   - Body text: "Building an interface between the two. Matching a company…" (the user edited this by hand).
   - Top right: the **screen recording** of the real app (dark mode). A company is typed in, the agent steps run and the slides appear; it is sped up to 31 s, from a real 95 s run.
   - Caption: "A real run, sped up: 95 seconds from question to slides."
   - The recording and its caption share **one click step** (`data-build-in="fade 9"`, no `auto`). After the three cards, they appear on the presenter's next press. This is the one deliberate exception to "everything automatic", at the user's request. The speaker note marks the moment with "[Next]".
   - "WHY IT IS HARD": three cards, all navy, appearing automatically:
     1. **Scattered and convoluted:** 41 websites, 18,332 pages, three languages.
     2. **Contained run time:** minutes, not hours; capped agent steps.
     3. **Sovereignty:** Apertus, the open Swiss model, and a search database we build and run ourselves.
3. **solution**
   - **No headline.** The user had "Five parts, one conversation." removed. The eyebrow "02 · HOW IT WORKS" stays.
   - Reworked on 2026-10-19 after the user's feedback: too many colours and styles, texts not fitting, boxes not equal or equidistant, an arrow overlapping its box. The "1 Interface" title used to take a full row inside its band.
   - Each part's title (30 px Abhaya heading, `white-space:nowrap`, title box 280 px wide) sits **above** its box. There are **no number squares**: the user found part numbers misleading.
     - "Interface" is at top 340.
     - "Indexing", "RAG", "Apertus 70B/8B" and "Export" are at top 520.
   - No overlays any more: the plain diagram. The examples moved to slide 4, `examples`.
   - Earlier overlay versions were all rejected: numbered flow badges, code snippets, full prompt quotes, dark cards, and light cards on the arrows.
   - Interface:
     - one cream band, 1664 × 76 px at top 400;
     - inside it, three white buttons, 296 × 52 px at top 412 and lane x + 24, each above its lane: Sources · Settings, Chat, Slide preview.
     - The user rejected a version with three separate cream boxes and no band.
   - Lanes:
     - four equal cream lanes, 344 × 320 px at top 580 (ending at 900), with 96 px gaps, at x = 128, 568, 1008 and 1448;
     - each lane holds three white two-line items: a bold navy title over a grey detail, each line at most about 18 characters.
   - Lane 5 is "Export" (Typst / Download / Preview).
     - The user had the "Quote check" item removed. The quote check still exists in the code (`rag_model/brief.py`); it is just not on the slide.
   - Lane 4's title is "Apertus 70B/8B": the 8B is the alternative, as the user asked.
   - Arrows: one colour, #5c6b80.
     - The vertical arrows run at lane x + 300 (x = 428, 1308, 1748): inside the buttons, and 20 px to the right of the titles, which end at lane x + 280. They have no labels.
     - Chat ↔ Apertus is a single arrow with two heads.
     - The horizontal arrows are at lane mid-height (y 740). Between RAG and Apertus there are two arrows: "calls" at y 710 and "hits" at y 770.
   - There is no red inside the diagram and no legend.
4. **examples** (added 2026-10-19)
   - **The same diagram as slide 3, in the same place.** Every diagram element has the same `id` on both slides, so the magic transition keeps it still:
     - `t-int` (Interface title), `band`, the buttons `b-src`, `b-chat`, `b-prev`;
     - the lane titles `t-idx`, `t-rag`, `t-ap`, `t-exp` and the lanes `l-idx`, `l-rag`, `l-ap`, `l-exp`;
     - the connectors `c-src`, `c-idx`, `c-chat`, `c-calls`, `c-hits`, `c-exp`, `c-prev`, and the labels `lbl-calls`, `lbl-hits`.
     - **Keep these ids on both slides when you edit either one.**
   - On slide 4 the diagram has no build-in. The eyebrow reads "02 · HOW IT WORKS · ONE EXAMPLE".
   - The lanes are emptied and 360 px high (580–940).
   - **Eight white example cards** (296 × 150 px) are pinned in the lanes, two per lane at top 604 and 766, next to the exchange they show. They rise in automatically, 1–8:
     - Indexing: SCRAPED HTML (real, JetBrains Mono, at most 18 characters per line), CLEANED TEXT (real, trafilatura).
     - RAG: SEARCH PASSAGES (example; three entries on three lines, `white-space:nowrap`, so it reads as an array: “Wearable sensors …”, “Glucose monitors …”, “Biosensor patches …”), PAGES FOUND ("[1] dcberne.com · Four DCB professorships …", an example).
     - Apertus: FROM THE CHAT ("Start-up developing wearable glucose sensors"), ITEM + QUOTE (a real quote, p. [1]).
     - Export: SLIDE (one text block of three lines: **DCB professorships** / diabetes technology / Source: dcberne.com).
       - **The cause of "smaller text":** the cards have a fixed height of 150 px. Content taller than that makes the deck shrink the card's text automatically.
       - Keep every card to a label plus **one text block of at most three lines**. Two blocks, or a bold title that wraps to three lines, overflow., FILES (preview · PDF · PowerPoint).
   - The source page is https://www.dcberne.com/en/four-dcb-professorships-advance-research-in-diabetes-technology/
   - The user rejected a version laid out as a grid of 7 cards: "not reshuffled". The examples must sit **where the communication happens in slide 3**.

5. **merci**
   - Light theme since 2026-10-19, at the user's request:
     - white background with the same light node animation as the cover;
     - the navy header band like the other slides;
     - a huge navy "Merci." with a red full stop.
   - "DANKE · GRAZIE · GRAZIA · THANK YOU": with Merci, these are the four national languages (German, Italian, Romansh) plus English.
   - Then "Questions? Bring us a company’s need, and we’ll find the research to meet it." This echoes the slide 2 headline. The user rejected "Let’s try it live".
   - Footer with the team.
6. **bonus** (added 2026-10-19)
   - Comes after Merci in `order`. It has no section in `sections`. The header nav shows 01–03 with none highlighted, so the earlier slides don't mention it. The user wants it kept out of the nav ("hidden throughout the presentation").
   - It does **not** carry the `hidden` attribute, so Present mode shows it after Merci. Add `hidden` to its `<section>` to skip it.
   - Headline: "Bonus 🧀". The user chose this wording and asked for the emoji.
   - Ten cheese puns in cream cards: 2 columns × 5 rows, each 816 × 100 px, at top 352 + row × 120. They have **no** build-in: the user wants them all on screen as soon as the slide appears. (Automatic steps are always 0.52 s apart, `buildMs` 380 + 140, and can't be slowed down.)
     - Text is Abhaya 34 px, line-height 1.1. Two lines fit; three would not.
     - The last two are the user's own: "Scrape it till you make it." and "Fitting industry’s appetite for expertise."
   - The same footer as Merci, at `bottom:64px`: "RAGlette · Mylife with Tokens: Daniele, Han, Marc · built at Hack Apertus …".

All slides have English speaker notes in an `<aside>`.

## The user's feedback so far (do not repeat these mistakes)

- **Stay on the case.** The first version framed RAGlette as a pitch-deck generator. The user pasted the case and asked for the Research & Expertise Navigator framing.
- **Show the true app.** The app runs in **dark mode**. A light screenshot was rejected, and the cover screenshot was later removed in favour of the logo.
- **No made-up animations.** A "tiles" animation and a page-feed animation were rejected as meaningless. A JS replay of the chat was replaced with a real video.
- **Diagram content:**
  - The user wants the *interacting components*, not four abstract steps.
  - Chunk counts are not wanted ("we don't care about those").
  - **RAG sits between scraping/indexing and Apertus.** It is not "the backend".
- **Geometry:** the user checks alignment. Boxes must not overflow their frames, and arrows must hit box edges. Compute heights:
  - 24 px text gives about 31 px per line;
  - heading 30 px × 1.1;
  - add the padding.
- **Accuracy:** no confidentiality claim. Company descriptions are sent to the Apertus API through the gateway (gateway.keera.ch); only the index and search run locally. Never invent statistics.
- **Language:** the slides and notes are in English; the user chats in German.

## Facts you may use (real, from the project)

- 41 enabled websites; 18,332 indexed pages; 66,637 chunks. Avoid chunk counts on slides.
- Pages by language: 8,588 English, 8,246 German, 1,451 French.
- Keyword "glucose sensor" appears on 22 pages, while 83 more pages on 8 sites use other words: continuous glucose monitoring 51, biosensor 29, Glukosesensor 13, metabolic monitoring 5, wearable sensing 4. These are SQLite `LIKE` page counts. "CGM" is excluded because substring matches inflate it.
- Agent runs:
  - the recorded wearable glucose sensor run answered in 95 s, with 5 items and 7 slides;
  - the diabetes pump run answered in 220 s, with 9 items and 11 slides.
- Agent step limit: `agent.max_steps` 15 in `config.yaml`.

## Assets in the deck

These are the IDs in the new deck. Marc's deck uses other IDs for the same files.

- `/_blob/2235d53f1c61bb27e413963029aeebfc`: demo video, MP4, 1280×800, 31 s.
- `/_blob/b84528431d606e1ea4a11c915118afc8`: the video's still frame (the final state).

## Re-recording the video or a screenshot

Scripts are in `pitch/tools/`. They drive headless Chromium over the DevTools protocol and need the Python package `websockets`, which is in the project `.venv`.

- **`record.py <scratchpad> "<query>"`:**
  1. Opens http://localhost:5173 in dark mode at 1280×800 @1.5x.
  2. Types the query and presses Enter.
  3. Captures frames until "answered in" appears.
  4. Writes `rec/frames/*.jpg` and `rec/frames.json`.

  Assemble with an ffmpeg concat list:
  - real-time durations for idle, typing and sent;
  - working ÷6;
  - `-vf fps=30,scale=1280:800 -c:v libx264 -crf 24 -movflags +faststart`.
- **`screenshot.py <scratchpad> <out.png>`:** a single screenshot after 25 s.
  - It opens `/_shot.html`, a temporary file you put into `frontend/public/` that sets `sessionStorage["raglette-chat"]` to a conversation id and redirects to `/`.
  - Delete that file afterwards.
  - Switch the colour scheme in the script (`"dark"` / `"light"`).
- **Before recording:**
  - The API (port 8000) and Vite (port 5173) must run.
  - The chat model is set in Settings, stored as `model_agent` in `data/settings.json`. Record with `apertus-v1-5-70b`; the 8B writes tool calls as text and works worse.
  - Switch the model back if you change it. At handoff it is set to **8B**, the user's choice.
  - Never print or commit the API key.

## Open points

- **Nobody has visually checked the latest slides.** The last agent never rendered them.
- Things to verify in Present mode:
  - the slide 2 video plays once it has been revealed by the click;
  - the "calls" / "results" labels on slide 3 fit the 112 px gap;
- A demo conversation, "Start-up developing wearable glucose sensors", exists in the app from the recording. Its title slide shows the placeholder "Company".
- The user is going through the slides one by one with feedback. Slide 4 has not been reviewed yet.
- Changed in the copy (2026-10-19):
  - Slide 2, card 3 now reads "Apertus, the open Swiss model, and a search index we build and run ourselves." The shorter text makes the three cards the same height.
  - The slide 4 speaker note now uses the Research Navigator framing; it no longer says "build its pitch deck live".
  - The snapshot now includes the hand edit of slide 3 ("by meaning, with HyDE").
