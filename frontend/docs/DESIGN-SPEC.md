# Design specification

## Direction
Quiet, institutional research workspace: warm off-white canvas, forest-green actions, sage panels, fine neutral borders, restrained typography and generous spacing. Use the supplied CSS exactly for fidelity. The compact BERΝ wordmark is text/CSS artwork, not an official institutional logo. No external fonts or photographic assets are required. Icons use lucide-react.

## Tokens

| Token | Value | Use |
|---|---|---|
| Ink | #202f2b | Main text |
| Muted | #68736d | Supporting text |
| Green | #315a48 | Primary actions and accents |
| Line | #dfe3dc | Borders |
| Paper | #fafbf7 | Canvas |
| Mint | #eaf0e7 | Supporting panels |
| Hero | #f1f3eb | Search introduction |
| Card | #ffffff | Result surfaces |
| Focus | #b58a39 | 3px keyboard outline, 4px offset |

Typography: Arial, Helvetica, sans-serif. Base 14px. Desktop hero 49px / 1.1, weight 500, -2px tracking; mobile hero 38px. Result names 20px, weight 500; result heading 22px; metadata 10–12px; eyebrow labels 10px with 1.8px tracking. Card corners 10px; search 9px; chips 4px. Avoid heavy shadows; search has a faint shadow and the detail panel has a stronger edge shadow.

## Page composition

1. Header: 88px high, white, bottom border, 5% horizontal padding. Brand at left, Discover and Shortlist navigation next, small ecosystem label on right. Saved count is inline.
2. Hero: sage background, 49px top and 35px bottom padding. Eyebrow, two-line heading “Find the expertise. / Make the connection.”, supporting sentence, search form and suggested queries. Search max width 850px. Input occupies remaining width; green Search button on right. Tiny “01 — DISCOVER” annotation at lower right on wide screens.
3. Workspace: max width 1500px, centered, 35px top and 5% horizontal padding. Two columns: 225px filters, flexible results, 43px gap.
4. Filters: Refine results + Reset. Institution checkboxes with counts and result-type radios, divided by thin lines. Shortlist session note. Do not add the removed evidence explainer box.
5. Result heading: eyebrow, query title, result count, compact streaming status. Demo banner immediately below when no backend is configured.
6. Results: single-column cards. Initial state offers suggested exploration; no-results state gives an explicit explanation.
7. Footer: small research tagline and small uppercase brand text.

## Result-card hierarchy

- Top: kind chip + institution; save bookmark aligned right.
- Identity: circular initials/category icon, name button, role beneath.
- Organisational unit line with building icon.
- Expertise chips, wrapping as needed.
- Two-column related information: projects/activities and infrastructure/services.
- Thin footer divider. Source count / View evidence left; View profile right.

Do not render match reasoning anywhere. The backend `reason` field remains in the contract for compatibility but is not displayed. Names, role, affiliation, unit, expertise, project and service content come from backend data. Source-less fields must not be invented.

## Evidence/profile panel

A native modal dialog anchored to the right, width min(590px, 100vw), full viewport height, internally scrollable. Dimmed, lightly blurred backdrop. Sticky header and close button. Contents: kind/institution, name, demo caveat when appropriate, labelled factual fields with source-number anchors, contact section, original-source cards with excerpts and retrieval date, and save action. Original links open a new tab. Source references scroll to their evidence blocks. Use explicit missing-data text.

## Responsive rules

- Above 1450px: center hero content with the wide-page calculation in CSS.
- At/below 1000px: hide right header label and hero annotation; filters become 200px; gap becomes 25px.
- At/below 700px: 72px header; 20px page gutters; 38px hero; filter panel hidden until Filters is toggled; one-column workspace; related information stacks; evidence panel fills the screen; result names 19px; suggestions wrap.

## Real-time interaction

Search starts on submit or suggestion click, not every keystroke. Keep editable input distinct from the submitted query. Clear prior results for a new search. Cancel the old subscription and ignore stale callbacks. Insert received cards without repeated reordering; replace matching IDs in place. Apply backend ordering on completion. Display progress and a Stop search action while streaming, plus a skeleton beneath received cards. The backend owns all relevance decisions.

On error, retain received results and show retry. On empty completion, show no supported matches. Filters apply locally to received results. A shortlist is session-memory only. Missing contacts render a clear message rather than a fabricated link. New queries retain filters and shortlist state.

## Accessibility

Semantic form with input label; skip link; visible focus outlines; aria-pressed save controls; radio/checkbox semantics; polite live status; alert for errors; modal dialog with accessible label, Escape dismissal and native focus handling. Honour prefers-reduced-motion. Validate keyboard behaviour and contrast in the receiving browser environment.

## Known implementation refinements for integration

The fictional person avatar currently reads AE; replace it with initials derived from real names when supplying real people. Initial institution filters are the three configured sources; centralise or receive them from the backend if adding institutions. Fixture filtering is intentionally simple text matching, not production semantic search. Backend sourceIds must reference actual entries in the result's sources array; validate this relationship server-side. These are integration considerations, not visual redesign requests.
