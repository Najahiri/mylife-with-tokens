# Research & Expertise Navigator – Frontend

Statische SPA (Vite + React + TypeScript, Tailwind CSS 4, Radix/shadcn-Komponenten, TanStack Query, React Router).
Läuft vollständig mit Mock-Daten und wird durch eine Umgebungsvariable auf die echte FastAPI umgestellt.

## Start

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, Mock-Modus
```

Weitere Skripte:

| Befehl | Zweck |
|---|---|
| `npm run build` | Typecheck (`tsc -b`) und Produktions-Build nach `dist/` |
| `npm run typecheck` | nur TypeScript prüfen |
| `npm run lint` | ESLint |
| `npm run preview` | gebauten Stand lokal ausliefern |

## Umgebungsvariablen

Siehe `.env.example`. Für lokale Overrides `.env.local` anlegen (wird nicht eingecheckt).

| Variable | Default | Bedeutung |
|---|---|---|
| `VITE_API_MODE` | `mock` | `mock` = eingebaute Beispieldaten, `live` = echte API |
| `VITE_API_BASE_URL` | `/api` | Basis-URL der API |

Die Variablen werden beim Build eingesetzt, eine Änderung braucht also einen Neustart von `npm run dev` bzw. einen neuen Build.

## Umstellen auf das echte Backend

1. FastAPI auf `http://localhost:8000` starten (Endpunkte unter `/api/...`).
2. Frontend im Live-Modus starten:
   ```bash
   VITE_API_MODE=live npm run dev
   ```
   Der Vite-Dev-Server leitet `/api` an `http://localhost:8000` weiter (`vite.config.ts`).
3. Für den Betrieb: `VITE_API_MODE=live npm run build` und `dist/` statisch ausliefern, z.B. von FastAPI (`StaticFiles`) oder nginx. Wichtig ist ein SPA-Fallback: unbekannte Pfade wie `/search` oder `/about` müssen `index.html` zurückgeben, und `/api` muss auf das Backend zeigen.

Läuft das Backend nicht, zeigt die Suche einen Fehlerzustand mit "Erneut versuchen".

Im Mock-Modus erscheint in der Kopfleiste das Badge "Mock-Daten". Die Mock-Implementierung (`src/api/mock.ts`, `mockData.ts`) wird nur per dynamischem Import geladen und landet in einem eigenen Chunk.

## Mock-Szenarien

| Anfrage enthält | Suche | Zusammenfassung |
|---|---|---|
| `glucose`, `glukose`, `diabet`, `cgm` | `ok`, 12 Treffer (ARTORG, DCB, DBMR) | `ok` mit 3 Zitaten |
| `xyz`, `quantum banana` | `no_results` | `insufficient_evidence` (nicht angezeigt) |
| `vage`, `vague` | `low_confidence`, 3 Treffer | `insufficient_evidence` |
| `error` | HTTP 500 | HTTP 500 |
| Bildgebung/KI, Klima, Mikroskopie, Spine/Robotik | `ok`, 5–6 themenbezogene Treffer | `ok` mit 2 Zitaten |
| alles andere | `ok`, 6 generische Treffer | `ok` mit 2 Zitaten |

Alle Personen sind frei erfunden ("Dr. Beispiel Muster", "Prof. Anna Platzhalter" …). Die Mock-URLs zeigen auf echte Domains, die Seiten existieren aber nicht. Die Quellenliste entspricht `../sources.yaml`, die Seitenzahlen sind geschätzt.

Das Diabetes-Set hat 12 statt etwa 8 Treffer. Die UI lädt 10 pro Seite (`limit: 10`), so lässt sich "Mehr laden" im Mock ausprobieren.

## URL-Zustand

`/search?q=glucose%20sensors&type=project,person&source=artorg.unibe.ch&lang=en`

Mehrfachwerte sind kommagetrennt (wiederholte Parameter werden ebenfalls verstanden). `lang` ist der Filter für die Sprache der Quelle. Die Sprache der Oberfläche (DE/EN) und hell/dunkel werden im `localStorage` gespeichert, ebenso der eingeklappte Zustand der KI-Zusammenfassung.

## Struktur

```
src/
  api/        types.ts (Vertrag), client.ts (einziger API-Zugang), errors.ts, mock.ts, mockData.ts
  i18n/       de.ts, en.ts, index.tsx (Provider, Datums-/Zahlenformat de-CH / en-GB)
  pages/      HomePage, SearchPage, AboutPage, NotFoundPage
  components/ SearchBar, ExampleQueries, ExpandedTerms, AnswerPanel, CitationMarker, ResultCard,
              ResultDetailSheet, FilterPanel, EmptyState, ErrorState, Highlight, ThemeToggle, …
    ui/       Button, Badge, Checkbox, Popover, Sheet, Skeleton, Tooltip (shadcn-Stil, Radix)
  lib/        highlight.ts, parseCitations.ts, searchParams.ts, entityTypes.ts, utils.ts
  hooks/      useTheme.ts, queries.ts
```

## Gestaltung (Swiss Style, reduziert)

- **Raster und Ausrichtung:** Suchfeld, Zusammenfassung und Ergebnisliste beginnen an derselben Kante, rechts von der Filterspalte. Alles ist linksbündig gesetzt.
- **Schrift:** Inter Tight für Überschriften, Inter für Fliesstext, beide lokal eingebunden.
- **Formen:** keine Rundungen, feine Linien statt Kartenboxen, Schwarz/Weiss mit Grautönen.
- **Hervorhebungen:** Suchtreffer im Text erscheinen fett, nicht farbig.
- **Signalfarbe:** Es gibt genau eine, ein Blau. Sie kennzeichnet nur die KI-Zusammenfassung, die Zitate und den Tastaturfokus. Definiert ist sie als `--signal` in `src/index.css` (hell und dunkel). Rot ist bewusst nicht gewählt (Vorgabe: kein UniBE-Rot).

## Umsetzung der Vorgaben

- **Nachvollziehbarkeit:** Jede Karte zeigt mindestens eine Quelle mit Link und Stand. Die KI-Zusammenfassung erscheint nur zusammen mit ihrer nummerierten Quellenliste. Ohne Zitate wird sie nicht angezeigt, auch wenn `status = ok` wäre.
- **Kein HTML aus Daten:** Antworttext und Hervorhebungen werden geparst und als React-Text bzw. `<mark>`-Elemente gerendert. `dangerouslySetInnerHTML` kommt nicht vor.
- **Fairness:** Die Reihenfolge kommt unverändert von der API. Es gibt keine Scores, Badges oder Logos. Die Quellentabelle auf `/about` ist nach Gruppe und dann alphabetisch sortiert, nicht nach Grösse.
- **Souveränität:** Die Schriften (Inter, Inter Tight) kommen lokal über `@fontsource-variable/*`. Es gibt keine CDNs, keine Analytics und keine externen Requests. Im Browser geprüft: Alle Requests gehen an localhost.
- **Barrierefreiheit:** `/` fokussiert die Suche. Es gibt einen Skip-Link und sichtbare Fokus-Ringe. Zitat-Popover öffnen bei Hover und bei Tastaturfokus, Escape schliesst sie, Enter öffnet die Quelle. Sheets haben eine Fokusfalle. `prefers-reduced-motion` wird respektiert.

## Vorschläge zum API-Vertrag

Der Vertrag ist unverändert umgesetzt (`src/api/types.ts`). Folgende Ergänzungen würden der UI helfen:

1. **`facets.languages: { value: "de" | "en" | "fr"; count: number }[]`**: Der Sprachfilter zeigt derzeit keine Anzahlen, weil die Facette fehlt.
2. **`facets.units` oder `unit_count: number` in `SearchResponse`**: Die Zeile "37 Ergebnisse aus 9 Einheiten" berechnet die Zahl der Einheiten im Moment aus den *geladenen* Treffern (`unit_path`, die ersten drei Ebenen). Bei mehr Treffern als einer Seite ist sie deshalb zu niedrig. Das Backend kennt die korrekte Zahl.
3. **Semantik der Facetten festlegen:** Die UI geht davon aus, dass Facetten-Zahlen *ohne* den jeweils eigenen Filter berechnet werden (disjunktive Facetten). Sonst verschwinden Optionen, sobald man eine anklickt. Der Mock berechnet sie auf der ungefilterten Treffermenge.
4. **`answer_lang?: "de" | "en"` in `AnswerRequest`**: Damit Apertus in der Sprache der Oberfläche antwortet, nicht nur in der Sprache der Anfrage.
5. **`source_id` und `lang` in `Citation`**: Das wäre konsistent mit `SourceRef` und erlaubt im Zitat-Popover dieselbe Darstellung wie auf den Karten (`lang`-Attribut am Zitat für Screenreader).
6. **Leere Anfrage:** Bitte mit HTTP 422 und `detail` beantworten. Die UI sendet leere Anfragen ohnehin nicht.
