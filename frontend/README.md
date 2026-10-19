# RAGlette web UI

React + TypeScript (Vite), Tailwind CSS 4, Radix/shadcn components, TanStack Query, React Router. It talks to the FastAPI backend under `/api`; the project documentation is in the [README in the root](../README.md).

```sh
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000 (start the API first)
npm run build      # type check and production build into dist/, served by the API on port 8000
npm run lint       # ESLint
```

| Folder | Content |
|---|---|
| `src/pages/` | Chat (`ChatPage.tsx`), Sources, Settings |
| `src/components/` | slide panel, slide viewer, title slide editor, export menu, index update card, settings forms, animated background |
| `src/api/` | API client and types, including the server-sent events of the chat |
| `src/lib/` | small helpers (time, debounce, dismiss) |

The UI is in English and follows the system light or dark mode.
