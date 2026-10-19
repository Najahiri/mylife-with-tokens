# Business-case presentation template (Kanton Bern style)

This folder turns **one JSON file** into a PDF slide deck in the corporate design of the Kanton Bern.
You do not write or change any Typst code. Your job is to write a valid JSON file that follows the rules below,
then compile it.

```
result/
├── presentation.typ   builds the slides from the JSON (do not edit)
├── kanton-bern.typ    the Kanton Bern design template (do not edit)
├── data.json          complete example input, use it as a reference
├── assets/            logos and the title-slide photo
│   └── fonts/         Liberation Sans (Regular, Bold, Italic, Bold Italic) + LICENSE
└── README.md          this file
```

## 1. Workflow

1. Write a JSON file (for example `data.json`, or a new file such as `acme.json`) **inside this folder**.
2. Compile it (see section 5).
3. If compilation fails, read the error message (section 6), fix the JSON and compile again.

## 2. What the deck looks like

The deck always has this structure. You cannot add, remove or reorder slide types.

| Slide | Content |
|---|---|
| 1. Title slide | Full-page photo background. Red label "Business Case", the title **`<company> – Business Case Presentation`**, and at the bottom left `Referent/-in: <author>` with `<organizer>` on the line below. |
| 2 … n+1. One slide per expertise | The expertise `title` at the top. The `description` text on one side, and a grey box titled "Ansprechpersonen" (contact persons) with up to 3 contacts on the other side. An optional chart sits directly below the description. |

- The sides alternate automatically: the 1st, 3rd, 5th … expertise has its description on the left, the 2nd, 4th … on the right.
  The order of the `expertises` array is the order of the slides.
- The header of every slide shows the Kanton Bern logo, the `classification` text, the date and the slide number.
- The fixed labels are German: "Business Case", "Referent/-in", "Ansprechpersonen". So write the content in German too,
  unless you are told to use another language.

## 3. JSON format

The file must be strict JSON: UTF-8, double quotes, no comments, no trailing commas.
Fields that are not listed here are ignored.

### Top level

| Field | Type | Required | Meaning |
|---|---|---|---|
| `author` | string | yes | The speaker's name, shown as "Referent/-in: …" |
| `company` | string | yes | The company's name, used in the title |
| `organizer` | string | yes | The organiser (person or unit), shown below the author |
| `expertises` | array of objects | yes | One slide per entry, at least one entry |
| `subtitle` | string | no | Grey subtitle under the title on slide 1 |
| `classification` | string | no | Header text. Default: `"Klassifizierung: intern"`. Other usual values: `"Klassifizierung: vertraulich"`, `"Klassifizierung: geheim"` |
| `date` | string | no | Exactly `"YYYY-MM-DD"`, e.g. `"2026-10-18"`. It is shown as "18. Oktober 2026". Default: today |
| `title_image` | string | no | Path of the title-slide photo, relative to this folder. Default: `"assets/photo-light.jpg"`. Leave it out unless you were given another image. |

### Each entry of `expertises`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `title` | string | yes | Slide title, the name of the expertise |
| `description` | string | yes | Short description, plain text |
| `contacts` | array of objects | no | **0 to 3** contact persons. If empty or left out, the grey box is not drawn |
| `chart` | object | no | One bar chart or pie chart below the description |

### Each entry of `contacts`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | Full name |
| `function` | string | no | Role or job title (shown in grey) |
| `email` | string | no | Email address (becomes a clickable link) |
| `phone` | string | no | Phone number, e.g. `"+41 31 555 12 01"` (becomes a clickable link) |

Give every contact at least one way to reach them (`email` and/or `phone`).

### `chart`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | string | yes | `"bar"` or `"pie"`, nothing else |
| `title` | string | no | Bold heading above the chart. Put the unit here, e.g. `"Umsatz in Mio. CHF"` |
| `data` | array of objects | yes | At least one entry, each of the form `{ "label": string, "value": number }` |

- `"bar"`: red vertical bars with the value above each bar and the label below it. The y-axis is scaled automatically.
- `"pie"`: a ring chart in the template colours, with a legend on the right that lists every label and its value.
  The ring shows the proportions, so the values do not need to add up to 100.
- `value` must be a JSON number (`18` or `12.5`), not a string such as `"18"` or `"18 %"`. It must be greater than 0.
  Decimals are shown with a dot (`12.5`).

## 4. Limitations

Most layout problems are **not** reported as errors: text that is too long simply overlaps other elements.
The limits below were measured on the real output. Stay within them.

| Element | Limit | What happens if you exceed it |
|---|---|---|
| `company` | ≤ 20 characters | The title on slide 1 needs 3 lines and covers the red label. Use a short form of the name (e.g. "BEKB" instead of the full legal name). |
| `subtitle` | ≤ 25 characters (one line) | Runs into the speaker block |
| expertise `title` | ≤ 45 characters | Wraps onto a second line that overlaps the description |
| `description`, no chart | ideal 150–400 characters, max. ~1000 | Above ~400 characters the font shrinks step by step (26 pt → 13 pt). Above ~1000 the text overflows the slide. |
| `description`, with chart | ideal 80–200 characters, max. ~450 | The description only has room for about 5 lines at full size. Above that it shrinks, and very long text pushes the chart off the slide. |
| `contacts` | max. 3 entries | 4 or more causes a compile **error** |
| contact `name` | ≤ 25 characters | Wraps onto a second line. With 3 contacts the box can then run off the bottom of the slide. |
| contact `function` | ≤ 40 characters | Same as `name` |
| contact `email` | ≤ 35 characters | Same as `name` |
| bar chart | max. 6 bars, labels ≤ 10 characters | The labels under the bars overlap each other |
| pie chart | max. 6 entries, labels ≤ 25 characters | Legend rows overlap |
| number of expertises | no hard limit | 3 to 10 is a sensible deck length |

Further limitations:

- **Plain text only.** Strings are printed exactly as written. Markdown or Typst markup (`**bold**`, `_italic_`, `#…`)
  appears literally. Do not put line breaks (`\n`), bullet lists or HTML in any string.
- Only one chart per expertise, and only `bar` or `pie`. Other chart types (lines, stacked bars, several series) are not supported.
- You cannot change colours, fonts, the slide order or the fixed German labels from the JSON.
- The JSON file and any `title_image` must be inside this folder, because Typst cannot read files outside the folder it compiles in.
- Emails and phone numbers are not checked. Use realistic but clearly fictional data unless real data was provided.

## 5. How to compile

Requirements: [Typst](https://typst.app) **0.14 or newer** (tested with 0.15.1). No internet connection is needed
and no fonts have to be installed: the font is in `assets/fonts/`.
Run all commands **from inside this folder**, and always pass the two font options:

```sh
cd output_template/result

# default input data.json → presentation.pdf
typst compile --font-path assets/fonts --ignore-system-fonts presentation.typ

# another JSON file and a chosen output name
typst compile --font-path assets/fonts --ignore-system-fonts presentation.typ acme.pdf --input data=acme.json

# optional: one PNG per slide, to check the layout visually
typst compile --font-path assets/fonts --ignore-system-fonts presentation.typ "preview-{p}.png" --ppi 60 --input data=acme.json
```

- `--input data=<file>` picks the JSON file. Without it, `data.json` is used.
- `--font-path assets/fonts` loads the bundled font. `--ignore-system-fonts` makes Typst use only that font,
  so the PDF looks exactly the same on every machine.
- Exit code 0 means the PDF was written. Then check the limits in section 4, because overlapping text does not cause an error.

### Font

The Kanton Bern design uses **Arial**. Arial's licence does not allow it to be shared in this folder, so the
template ships **Liberation Sans** instead (SIL Open Font License 1.1, see `assets/fonts/LICENSE`, source:
[liberationfonts/liberation-fonts](https://github.com/liberationfonts/liberation-fonts) release 2.1.5).
Liberation Sans has exactly the same character widths as Arial, so text wraps in the same places and the limits in section 4 still hold.

- With the commands above, Typst prints `warning: unknown font family: arial`. This is expected and harmless:
  the template asks for Arial first and then uses Liberation Sans.
- If Arial is installed on the machine (on Debian: `sudo apt install ttf-mscorefonts-installer`) and you want to use it,
  leave out `--ignore-system-fonts`. Typst then picks Arial and keeps Liberation Sans as the fallback.

## 6. Error messages

Typst prints `error: …` followed by the location. The messages from the template's own checks are German:

| Message | Cause | Fix |
|---|---|---|
| `JSON: Feld «company» fehlt` (or another field) | A required top-level field is missing | Add `author`, `company`, `organizer` and `expertises` |
| `Expertise: Feld «title» fehlt` | An expertise has no title | Add `title` |
| `Expertise «X»: Feld «description» fehlt` | Expertise X has no description | Add `description` |
| `Kontakt: Feld «name» fehlt` | A contact has no name | Add `name` |
| `Expertise «X»: maximal 3 Kontakte erlaubt` | More than 3 contacts | Keep at most 3 |
| `Expertise «X», Diagramm: Feld «data» fehlt` (or `«type»`) | The chart is incomplete | Add `type` and `data` |
| `Expertise «X»: Diagrammtyp muss «bar» oder «pie» sein, nicht «…»` | Unknown chart type | Use `"bar"` or `"pie"` |
| `string contains invalid digits` | `date` is not in `YYYY-MM-DD` format | Use e.g. `"2026-10-18"`, or remove `date` |
| `cannot divide string by integer` | A chart `value` is a string | Write the number without quotes |
| `value must be strictly positive` or `cannot divide by zero` | A chart `value` is 0 or negative | Use positive numbers only |
| `failed to parse JSON` | Invalid JSON syntax | Check quotes, commas and brackets |
| `file not found` | Wrong file name, or the file is outside this folder | Check `--input data=…` and `title_image` |
| text in a serif font, or `warning: unknown font family: liberation sans` | The bundled font was not loaded | Run the command from inside this folder with `--font-path assets/fonts` |

## 7. Minimal valid example

```json
{
  "author": "Anna Müller",
  "company": "Alpenwerk AG",
  "organizer": "Amt für Wirtschaft, Kanton Bern",
  "date": "2026-10-18",
  "expertises": [
    {
      "title": "Datenanalyse & KI",
      "description": "Aus Daten werden Entscheidungsgrundlagen: Dashboards, Prognosemodelle und KI-Anwendungen.",
      "contacts": [
        { "name": "Julia Brunner", "function": "Head of Data", "email": "julia.brunner@alpenwerk.ch", "phone": "+41 31 555 13 10" }
      ],
      "chart": {
        "type": "bar",
        "title": "Abgeschlossene KI-Projekte pro Jahr",
        "data": [
          { "label": "2023", "value": 12 },
          { "label": "2024", "value": 18 },
          { "label": "2025", "value": 25 }
        ]
      }
    },
    {
      "title": "Finanzen & Controlling",
      "description": "Budgetplanung, Kostenrechnung und Wirkungscontrolling für öffentliche Verwaltungen.",
      "contacts": [
        { "name": "Patrick Wyss", "email": "patrick.wyss@alpenwerk.ch" },
        { "name": "Andrea Kunz", "function": "Finanzanalystin", "phone": "+41 31 555 19 31" }
      ],
      "chart": {
        "type": "pie",
        "title": "Mandate nach Kundengruppe",
        "data": [
          { "label": "Kanton", "value": 14 },
          { "label": "Gemeinden", "value": 22 },
          { "label": "KMU", "value": 31 }
        ]
      }
    }
  ]
}
```

`data.json` in this folder is a larger example with nine expertises, both chart types and contacts with missing optional fields.

## 8. Checklist before you compile

- [ ] `author`, `company`, `organizer` and `expertises` are present, and `expertises` has at least one entry
- [ ] `company` ≤ 20 characters, every expertise `title` ≤ 45 characters
- [ ] every expertise has a `title` and a `description` within the length limits (shorter if it has a chart)
- [ ] at most 3 contacts per expertise, each with a `name` and an `email` or `phone`
- [ ] charts: `type` is `"bar"` or `"pie"`, at most 6 entries, short labels, positive numeric values
- [ ] `date` (if present) is `YYYY-MM-DD`
- [ ] no markup or line breaks inside strings, and the file is valid JSON
- [ ] the compile command includes `--font-path assets/fonts --ignore-system-fonts`
