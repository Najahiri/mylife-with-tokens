// Business-Case-Präsentation – wird vollständig aus einer JSON-Datei erzeugt.
//
//   typst compile presentation.typ                          // liest data.json
//   typst compile presentation.typ --input data=other.json  // andere Datei
//
// Aufbau der JSON-Datei: siehe README.md bzw. data.json.
#import "kanton-bern.typ": *

#let data = json(sys.inputs.at("data", default: "data.json"))

#let _require(dict, key, where) = {
  assert(key in dict, message: where + ": Feld «" + key + "» fehlt")
  dict.at(key)
}
#for key in ("author", "company", "organizer", "expertises") { let _ = _require(data, key, "JSON") }

#let date = if "date" in data {
  let (y, m, d) = data.date.split("-").map(int)
  datetime(year: y, month: m, day: d)
} else { auto }

#show: kanton-bern.with(
  classification: data.at("classification", default: "Klassifizierung: intern"),
  date: date,
)

/// Text verkleinern, bis er in die Box passt (26 pt → 13 pt).
#let fit-text(width, height, sizes: (26pt, 22pt, 20pt, 18pt, 16pt, 13pt), body) = context {
  let chosen = sizes.last()
  for s in sizes {
    let m = measure(block(width: width, { set text(size: s); show: lines; body }))
    if m.height <= height { chosen = s; break }
  }
  set text(size: chosen)
  show: lines
  body
}

/// Eine Kontaktperson: Name 26 pt, Funktion und Erreichbarkeit 13 pt.
#let contact-card(c) = {
  let name = _require(c, "name", "Kontakt")
  let details = ()
  if "function" in c { details.push(text(fill: tx2, c.function)) }
  if "email" in c { details.push(link("mailto:" + c.email, c.email)) }
  if "phone" in c { details.push(link("tel:" + c.phone.replace(" ", ""), c.phone)) }
  block(breakable: false, {
    text(size: 20pt, name)
    if details.len() > 0 {
      block(above: 0.2cm, {
        set text(size: 13pt)
        show: lines
        details.join(linebreak())
      })
    }
  })
}

// Aufteilung der Expertise-Folien: Beschreibung ~60 %, Kontaktspalte ~36 %.
// Die Seiten wechseln von Folie zu Folie; beide Spalten schliessen am Inhaltsrand ab.
#let content-x = 2.33cm
#let content-w = 30.51cm
#let desc-w = 18.0cm
#let panel-w = 11.0cm
#let content-y = 5.15cm
#let content-h = 12.98cm

/// Kontaktspalte: hell hinterlegte Fläche (Akzent 1, heller 80 %), Kontakte mit Trennlinien.
#let contact-panel(contacts) = block(
  width: panel-w,
  fill: lum(accent1, 20%, off: 80%),
  inset: (x: 0.6cm, top: 0.55cm, bottom: 0.6cm),
  {
    block(below: 0.45cm, text(size: 13pt, weight: "bold", fill: accent6)[Ansprechpersonen])
    contacts.map(contact-card).join(line(length: 100%, stroke: 0.75pt + bg2))
  },
)

/// Diagramm unter der Beschreibung.
/// chart: (type: "bar" | "pie", title: optional, data: ((label: …, value: …), …))
#let chart-h = 6.2cm
#let chart-gap = 0.6cm

#let expertise-chart(chart, where) = {
  let kind = _require(chart, "type", where + ", Diagramm")
  assert(kind in ("bar", "pie"), message: where + ": Diagrammtyp muss «bar» oder «pie» sein, nicht «" + kind + "»")
  let rows = _require(chart, "data", where + ", Diagramm").map(d => (d.label, d.value))
  let caption = chart.at("title", default: none)
  let cap-h = if caption != none { 0.75cm } else { 0cm }
  let h = chart-h - cap-h
  let body = if kind == "bar" {
    // ~5 Gitterlinien statt 10 (die Diagrammhöhe ist halb so gross wie in der Vorlage)
    let step = _nice-step(calc.max(..rows.map(r => r.at(1))) * 2)
    bar-chart(rows, width: desc-w, height: h, colors: accent6, step: step, inset: (left: 0cm, right: 0cm, top: 0.42cm))
  } else {
    // Ring wie «Kreisdiagramm» der Vorlage, Werte in der Legende
    let size = h - 0.3cm
    let swatch(i) = box(width: 0.4cm, height: 0.4cm, fill: chart-colors.at(calc.rem(i, chart-colors.len())), baseline: 0.05cm)
    grid(
      columns: (size, auto),
      column-gutter: 1.2cm,
      align: (left + top, left + horizon),
      pad(top: 0.3cm, donut-chart(rows, size: size, hole: 55%, value-labels: false)),
      {
        set text(size: 13pt)
        grid(
          columns: (auto, auto, auto),
          column-gutter: (0.3cm, 1.2cm),
          row-gutter: 0.35cm,
          align: (left, left, right),
          ..rows.enumerate().map(((i, (l, v))) => (swatch(i), [#l], [#v])).flatten(),
        )
      },
    )
  }
  block(width: desc-w, height: chart-h, breakable: false, stack(
    if caption != none { box(height: cap-h, text(size: 13pt, weight: "bold", top-edge: 0.905em, bottom-edge: "descender", caption)) },
    body,
  ))
}

// 1 ─ Titelfolie (Layout «Titelfolie mit Bild (hell)»)
#title-slide(
  photo: image(data.at("title_image", default: "assets/photo-light.jpg")),
  kicker: [Business Case],
  title: [#data.company – Business Case Presentation],
  subtitle: data.at("subtitle", default: none),
  author: [Referent/-in: #data.author \ #data.organizer],
)

// 2… ─ Eine Folie pro Expertise: Beschreibung und Kontakte, Seiten abwechselnd
#for (i, e) in data.expertises.enumerate() {
  let title = _require(e, "title", "Expertise")
  let contacts = e.at("contacts", default: ())
  assert(contacts.len() <= 3, message: "Expertise «" + title + "»: maximal 3 Kontakte erlaubt")

  // gerade Folien: Beschreibung links, ungerade: Beschreibung rechts
  let desc-left = calc.even(i)
  let desc-x = if desc-left { content-x } else { content-x + content-w - desc-w }
  let panel-x = if desc-left { content-x + content-w - panel-w } else { content-x }

  blank-slide(title: title)[
    #let where = "Expertise «" + title + "»"
    #let chart = e.at("chart", default: none)
    #let desc-h = if chart == none { content-h } else { content-h - chart-h - chart-gap }
    #place(top + left, dx: desc-x, dy: content-y, block(width: desc-w, {
      fit-text(desc-w, desc-h, _require(e, "description", where))
      if chart != none { block(above: chart-gap, expertise-chart(chart, where)) }
    }))
    #if contacts.len() > 0 {
      place(top + left, dx: panel-x, dy: content-y + 0.2cm, {
        set block(spacing: 0.45cm)
        contact-panel(contacts)
      })
    }
  ]
}
