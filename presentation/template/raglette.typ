// RAGlette deck in the Kanton Bern design (kanton-bern.typ, unchanged team template).
// Built from one JSON by rag_model/presentation.py:
//   typst compile raglette.typ --input json='{...}'      (without input: raglette-example.json)
//
// Slides: title · at a glance (table of all partners) · one slide per item · contacts (table)
// Item slide: category and organisation, "what it is", "why it matters", key facts; contacts and the original
// quote on the right; sources at the bottom.
#import "kanton-bern.typ": *

#let data = json(bytes(sys.inputs.at("json", default: read("raglette-example.json"))))
#let L = data.labels
#let items = data.items

#let date = if "date" in data {
  let (y, m, d) = data.date.split("-").map(int)
  datetime(year: y, month: m, day: d)
} else { auto }

#show: kanton-bern.with(classification: data.at("classification", default: "Klassifizierung: intern"), date: date)

/// Shrink text until it fits the box.
#let fit(width, height, sizes, body) = context {
  let chosen = sizes.last()
  for s in sizes {
    let m = measure(block(width: width, { set text(size: s); show: lines; body }))
    if m.height <= height { chosen = s; break }
  }
  set text(size: chosen)
  show: lines
  body
}

// one accent colour per category (order of data.categories)
#let colours = (accent6, accent1, accent5, accent3, accent2)
#let colour(cat) = colours.at(calc.rem(data.categories.position(c => c == cat), colours.len()))
#let swatch(cat) = box(width: 0.34cm, height: 0.34cm, fill: colour(cat), baseline: 0.02cm)
#let label(body) = text(size: 13pt, weight: "bold", fill: accent6, body)

#let panel-w = 11.0cm
#let left-w = 18.2cm
#let top-y = 5.95cm
#let body-h = 11.9cm

// ─ 1 title
#title-slide(
  photo: image(data.at("title_image", default: "assets/photo-light.jpg")),
  kicker: L.kicker,
  title: fit(23.6cm, 4.33cm, (51pt, 44pt, 38pt, 32pt), [#data.company]),
  subtitle: L.subtitle,
  author: [#L.speaker: #data.author \ #data.organizer],
)

// ─ 2 at a glance
#if items.len() > 0 and data.at("show_overview", default: true) {
  let big = items.len() <= 7
  slide(title: L.overview)[
    #data-table(
      columns: (8.2cm, 1fr, 9.6cm),
      header: L.overview_cols,
      size: if big { 20pt } else { 13pt },
      row-height: if big { 1.15cm } else { 0.72cm },
      ..items.map(it => (
        [#swatch(it.category) #h(0.25cm) #it.category_label],
        it.title,
        text(fill: tx2, it.at("organisation", default: "")),
      )).flatten(),
    )
  ]
}

// ─ 3… one slide per item
#let contact-card(c) = block(breakable: false, {
  text(size: 18pt, c.name)
  let details = ()
  if "function" in c { details.push(text(fill: tx2, c.function)) }
  if "email" in c { details.push(link("mailto:" + c.email, c.email)) }
  if "phone" in c { details.push(link("tel:" + c.phone.replace(" ", ""), c.phone)) }
  if "url" in c { details.push(link(c.url, c.at("url_label", default: c.url))) }
  if details.len() > 0 {
    block(above: 0.15cm, { set text(size: 12pt); show: lines; details.join(linebreak()) })
  }
})

#for it in items {
  blank-slide(title: fit(30.51cm, 1.72cm, (34pt, 30pt, 26pt, 22pt), it.title))[
    // category · organisation
    #place(top + left, dx: 2.33cm, dy: 4.85cm, block(width: 30.51cm, {
      set text(size: 13pt)
      swatch(it.category)
      h(0.25cm)
      text(weight: "bold", fill: colour(it.category), it.category_label)
      if it.at("organisation", default: "") != "" { h(0.4cm); text(fill: tx2, it.organisation) }
    }))

    // left: what, why, facts
    #place(top + left, dx: 2.33cm, dy: top-y, block(width: left-w, fit(left-w, body-h, (22pt, 20pt, 18pt, 16pt, 14pt), {
      // each part: red label, the text right below it, then space to the next part
      let part(name, body) = block(below: 0.75cm, stack(dir: ttb, spacing: 0.25cm, label(name), block(body)))
      part(L.what, it.summary)
      if it.at("relevance", default: "") != "" { part(L.why, it.relevance) }
      let facts = it.at("facts", default: ())
      if facts.len() > 0 { part(L.facts, facts.map(f => [– #f]).join(linebreak())) }
    })))

    // right: contacts, then the quote that backs the item
    #place(top + left, dx: 2.33cm + 30.51cm - panel-w, dy: top-y, block(width: panel-w, {
      let contacts = it.at("contacts", default: ())
      if contacts.len() > 0 {
        block(width: panel-w, fill: lum(accent1, 20%, off: 80%), inset: (x: 0.55cm, top: 0.5cm, bottom: 0.55cm), {
          stack(dir: ttb, spacing: 0.35cm, label(L.contacts),
                ..contacts.map(contact-card).intersperse(line(length: 100%, stroke: 0.75pt + bg2)))
        })
      }
      if it.at("evidence", default: "") != "" {
        block(above: 0.6cm, width: panel-w, inset: (left: 0.45cm, y: 0.1cm), stroke: (left: 2.25pt + accent6), {
          set text(size: 12pt, style: "italic", fill: tx2)
          show: lines
          [«#it.evidence»]
        })
      }
    }))

    // sources
    #let sources = it.at("sources", default: ())
    #if sources.len() > 0 {
      place(top + left, dx: 2.33cm, dy: 18.2cm, block(width: 30.51cm, {
        set text(size: 9pt, fill: tx2)
        [#L.source: ]
        sources.map(s => link(s.url, s.at("label", default: s.url))).join(" · ")
      }))
    }
  ]
}

// ─ last: everyone to contact
#let people = ()
#for it in items {
  for c in it.at("contacts", default: ()) { if "url" not in c { people.push((c, it)) } }
}
#if people.len() > 0 and data.at("show_contacts", default: true) {
  let rows = people.slice(0, calc.min(people.len(), 14))
  slide(title: L.contacts_title)[
    #data-table(
      columns: (7.5cm, 7.5cm, 1fr, 7.2cm),
      header: L.contacts_cols,
      size: 13pt,
      row-height: 0.72cm,
      ..rows.map(((c, it)) => (
        c.name,
        text(fill: tx2, c.at("function", default: "")),
        it.title,
        if "email" in c { link("mailto:" + c.email, c.email) } else if "phone" in c { c.phone } else { "" },
      )).flatten(),
    )
  ]
}
