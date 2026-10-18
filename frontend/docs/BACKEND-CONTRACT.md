# Bern Research & Expertise Navigator

React + TypeScript using Next.js App Router conventions. The hosted preview builds with the supplied Vinext compatibility runtime; it is not a standard Next.js server deployment.

## UX
Search-first workspace. Stable result cards display identity, role, institutional affiliation, unit, expertise, projects, services and sources. A native modal side panel provides field-level evidence and public contact information. It supports Escape, focus containment and return focus. Mobile filters collapse; the evidence panel uses the full viewport. Use semantic HTML, keyboard focus indicators, reduced motion, explicit missing information and a polite status region. No invented confidence percentages or verified badges.

The demo is visibly labelled; all person/group profiles are fictional. Institutional links are entry points, not support for fictional claims. Shortlists are memory-only and reset on refresh.

## Backend integration
Set server environment variable SEARCH_STREAM_URL to a same-origin SSE endpoint (for example /api/search/stream). No backend was supplied or implemented. Without configuration the isolated demo adapter provides timed fixture events. The frontend does no extraction, enrichment, ranking, factual inference or LLM calls.

GET /api/search/stream?q=<URL-encoded query>
Content-Type: text/event-stream
Cache-Control: no-cache

Each default SSE message contains JSON validated against lib/navigator/schema.ts:

    data: {"type":"status","message":"Searching institutional sources…"}

    data: {"type":"result","result":{...Result}}

    data: {"type":"complete","orderedIds":["result-1","result-2"]}

    data: {"type":"error","message":"Search is temporarily unavailable"}

Result types and source/fact contracts are exported from schema.ts. Facts reference sourceIds; the backend must ensure references resolve, source passages support the facts, contact URLs are public professional contacts, and only safe URLs are provided. Null/empty fields render as not stated. The backend controls final ranking using orderedIds. During streaming, cards keep arrival order; duplicate IDs update in place. New queries close the prior connection and ignore stale callbacks. Completion closes the stream. Connection loss retains partial results with an explicit retry. Idle timeout is 45 seconds. Search cancellation is available.

Use a same-origin gateway for authentication via secure cookies. Native EventSource cannot attach arbitrary Authorization headers. If bearer headers or POST bodies are required, replace the transport with fetch streaming without changing components. Configure proxy buffering off and send heartbeat/status events more often than the timeout. Automatic reconnection is deliberately disabled to avoid silently duplicating a search; retry starts a new request.

## Production checks still required
Integrate the real endpoint, verify source referential integrity server-side, and browser-test streaming, keyboard navigation, connection loss, cancellation and responsive layouts. No live-search performance or factual correctness is claimed for the demo.
