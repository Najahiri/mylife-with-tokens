# Kanton Bern – Typst presentation template

A Typst rebuild of the Kanton Bern PowerPoint template (16:9, 33.867 × 19.05 cm).
All positions, font sizes, colours and line spacing come straight from the slide master and layouts of the `.pptx`.

```
kanton-bern.typ        the template (import this)
assets/logo-*.svg      logo, black and white versions (taken from the .pptx)
example.typ            rebuild of all 19 example slides
assets/example/        pictures used only by the example
```

Compile: `typst compile example.typ` (works with Typst 0.14 and 0.15).
Font: Arial, or Liberation Sans if Arial is missing (it has the same metrics).
Typst prints a warning for whichever of the two fonts it can't find. You can ignore it.

## Quick start

```typst
#import "kanton-bern.typ": *
#show: kanton-bern.with(
  classification: [Klassifizierung: intern],
  date: auto,                         // today, e.g. "18. Oktober 2026"
)

#title-slide(kicker: [Spitzmarke], title: [Titel], subtitle: [Untertitel],
             author: [Referent/-in \ Organisationseinheit])
#title-slide(photo: image("bild.jpg"), dark: true, title: [Titel])
#section-slide([Kapitel], subtitle: [Untertitel], style: "red")   // white | black | bluegray | red

#slide(title: [Titel und Inhalt])[
  Absatz = Textebene 1

  - Textebene 2
    - Textebene 3
]
#slide(title: [Titel], subtitle: [Untertitel])[…]
#two-content-slide(title: [Zwei Inhalte])[links][rechts]
#image-slide(title: [Bild rechts], photo: image("bild.jpg"), side: right)[Text]
#title-image-slide(title: [Titel und Bild], photo: image("bild.jpg"))
#blank-slide(title: [Nur Titel])[ #place(top + left, dx: 5cm, dy: 8cm)[frei] ]
```

| PowerPoint layout | Typst |
|---|---|
| Titelfolie / mit Bild (hell / dunkel) | `title-slide(…)`, `photo:`, `dark:` |
| Kapiteltitel Weiss / Schwarz / Blaugrau / Rot | `section-slide(style: …)` |
| Titel und Inhalt / Titel, Untertitel und Inhalt | `slide(title:, subtitle:)` |
| Zwei Inhalte | `two-content-slide` |
| Titel, Inhalt und Bild rechts / links | `image-slide(side: right / left)` |
| Titel und Bild | `title-image-slide` |
| Nur Titel / Leer | `blank-slide(title: …)` |

Every slide function also takes `overlay:` for extra elements you position yourself.
`overlay` coordinates are measured from the top-left corner of the slide.

## Building blocks

- **Colours:** `tx1`, `bg1`, `tx2`, `bg2`, `accent1` … `accent6`. Use `lum(c, 60%, off: 40%)` for a PowerPoint-style lighter or darker variant, and `tints(c)` for the five variants on the palette slide.
- **Tables:** `data-table(columns:, align:, header: (…), size: 26pt | 13pt, ..cells)`. Grey rules between rows, header in 13 pt.
- **Charts:** `bar-chart(data, colors: accent6 | chart-colors, max:, step:)` and `donut-chart(data, hole: 70%)`. `data` is a list of `(label, value)` pairs.
- **Lists:** a plain paragraph is text level 1. `-` items get the template's "‒" dash with a 1 cm indent, and `+` gives "1." numbering.
