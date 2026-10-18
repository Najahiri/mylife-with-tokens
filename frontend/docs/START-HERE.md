# Bern Navigator — coding-agent handoff

Reproduce the current frontend using the included source as the visual and behavioural reference. This package incorporates the latest user changes: **no “Why this matches” section on cards or in profile details**, and **no “Follow the evidence” box on the search page**. Do not reintroduce either.

## Agent instruction

Build a responsive TypeScript + React + Next.js App Router research-discovery interface. Preserve the supplied composition, copy, CSS tokens, component structure and interactions. Treat every factual field and final ranking as backend-owned. Use the source files directly when possible instead of approximating the interface. Read DESIGN-SPEC.md and BACKEND-CONTRACT.md first. Do not add a chatbot, LLM calls, crawling, extraction, invented confidence scores, researcher portraits or unverified badges. Keep fictional demo data explicitly labelled until a backend is connected.

## Contents

- `app/navigator.tsx`: complete interactive client interface.
- `app/globals.css`: authoritative styles, responsive breakpoints and motion.
- `app/page.tsx`: server entry, passes SEARCH_STREAM_URL to the client.
- `app/layout.tsx`: page metadata and root layout.
- `lib/navigator/schema.ts`: Zod schemas and TypeScript data types.
- `lib/navigator/stream.ts`: SSE subscription and cancellation, plus isolated demo transport.
- `lib/navigator/demo.ts`: fictional fixtures; never treat as verified people.
- `DESIGN-SPEC.md`: visual and interaction specification.
- `BACKEND-CONTRACT.md`: streaming integration and known limitations.
- `ACCEPTANCE.md`: reproduction checklist.
- `SOURCE-HASHES.json`: SHA-256 of exported app/lib source files.

## Run as standard Next.js

Use Node.js 22 or newer and an npm registry with the pinned package versions available.

```sh
npm install
npm run dev
npm run typecheck
npm run build
npm start
```

`npm start` is for the production build; do not run it at the same time as the dev server on the same port. Create `.env.local` with `SEARCH_STREAM_URL` only when a real SSE endpoint exists. Without it, the demonstration transport is used. The endpoint is browser-visible; never put credentials or secrets in its URL. Use a same-origin gateway for cookie authentication. The backend itself is outside this deliverable.

The package uses ordinary Next.js scripts. The original hosted version used Vinext's Next.js compatibility runtime; its production build passed. A fresh standard Next.js install/build and browser QA of this exported package have **not** been performed. The UI source is unchanged from the deployed revision; runtime scaffolding has been simplified for portability. No lockfile is included; resolve dependencies and commit a lockfile in the receiving project.

## Reference

Current design: https://bern-expertise-navigator.divineplum129.chatgpt.site (owner access may be required).
Source revision: 3834d5d200805e32cd103974d0c0b1c3badcfd6d.
Export date: 18 October 2026.
No screenshot is included; CSS and TSX are the authoritative reproduction reference. No Site credentials, deployment identity, dependencies or generated build output are included.
