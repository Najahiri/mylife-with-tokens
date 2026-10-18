# Reproduction checklist

- [ ] Desktop at 1440px: header, sage hero, narrow filters and single-column cards match supplied CSS.
- [ ] Mobile at 390px: no horizontal overflow; filters toggle; related information stacks; dialog fits screen.
- [ ] “Why this matches” is absent from cards and profile details.
- [ ] “Follow the evidence” box is absent from the search page.
- [ ] Search suggestions and Enter submit work; blank submissions do nothing.
- [ ] Cards appear progressively; repeated result IDs update without duplication.
- [ ] A second query cancels the first and stale events cannot overwrite it.
- [ ] Completion applies backend ranking; stop/error retains partial results.
- [ ] No-results, filtered-empty, timeout and retry states work.
- [ ] Save toggles update the shortlist and its count.
- [ ] Profile opens with mouse/keyboard; Escape closes; focus returns to trigger.
- [ ] Source anchors and external links work; missing fields remain explicit.
- [ ] Demo fixtures remain labelled, including the distinction between illustrative links and evidence.
- [ ] Valid real SSE data is rendered; malformed payloads produce an error.
- [ ] No frontend enrichment, inferred contact data or invented confidence scores.
- [ ] Standard Next.js typecheck/build succeeds after installing dependencies.

Previously verified: hosted Vinext production build passed for the exported source revision. Export checks: source-file hashes match the original revision; ZIP integrity checked. Browser and fresh standard Next.js runtime checks remain for the receiving agent.
