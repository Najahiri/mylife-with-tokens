// RAGlette README as an A4 document, in the look of the RAGlette web app and pitch deck.
// The text is the repository's README.md, rendered with cmarker, so the PDF never drifts from it.
// The Mermaid flowchart of the README is drawn here with fletcher (Typst cannot run Mermaid).
//
// Build from the repository root:
//   typst compile --root . --font-path presentation/typst/fonts presentation/typst/readme.typ presentation/typst/README.pdf
#import "@preview/cmarker:0.1.6"
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge

#let navy = rgb("#0E1C2F")       // header band, Apertus boxes
#let heading-navy = rgb("#082F5E")
#let red = rgb("#E50611")        // accent, reserved for real emphasis
#let cream = rgb("#F7F4EE")      // panels
#let rule = rgb("#E6E1D6")
#let body = rgb("#4A4A4A")
#let muted = rgb("#5C5C5C")

#let md = read("../../README.md")
#let intro = md.split("## Contents").at(0).replace(regex("^# RAGlette\s*"), "")
#let rest = "## The problem" + md.split("## The problem").slice(1).join("## The problem")

#set document(title: "RAGlette", author: ("Daniele", "Han", "Marc"))
#set text(font: ("Inter", "Liberation Sans"), size: 10pt, fill: body, lang: "en")
#set par(leading: 0.68em, spacing: 1.1em)
#set page(
  paper: "a4",
  margin: (x: 2.2cm, top: 2.8cm, bottom: 2.4cm),
  header: context if counter(page).get().first() > 1 [
    #set text(size: 8.5pt, fill: muted)
    #text(font: "Abhaya Libre", weight: "extrabold", size: 13pt, fill: heading-navy)[#text(fill: red)[RAG]lette]
    #h(1fr) README · Research & Expertise Navigator for Bern
    #v(-4pt)
    #line(length: 100%, stroke: 0.6pt + rule)
  ],
  footer: context [
    #set text(size: 8.5pt, fill: muted)
    Built at Hack Apertus · Mylife with Tokens #h(1fr) #counter(page).display()
  ],
)

// ---------------------------------------------------------------- headings
#show heading: set text(font: "Abhaya Libre", weight: "extrabold", fill: heading-navy)
#show heading.where(level: 2): it => {
  v(1.4em, weak: true)
  block(below: 0.9em, {
    text(size: 21pt, it.body)
    v(-0.55em)
    line(length: 2.2cm, stroke: 2.5pt + red)
  })
}
#show heading.where(level: 3): it => block(above: 1.4em, below: 0.7em, text(size: 14pt, it.body))

// ---------------------------------------------------------------- body elements
#show strong: set text(fill: heading-navy)
#show link: set text(fill: red)
#set list(marker: text(fill: red)[•], indent: 0.2em, body-indent: 0.6em)
#set enum(numbering: n => text(fill: red, weight: "bold")[#n.], indent: 0.2em)

#show raw: set text(font: ("DejaVu Sans Mono",), size: 8.6pt)
#show raw.where(block: false): it => box(fill: cream, inset: (x: 2pt, y: 0pt), outset: (y: 2.5pt), radius: 3pt, text(fill: heading-navy, it))
#show raw.where(block: true): it => block(fill: cream, inset: 10pt, radius: 8pt, width: 100%, text(fill: heading-navy, it))

#set table(
  stroke: (x, y) => (bottom: if y == 0 { none } else { 0.5pt + rule }),
  fill: (x, y) => if y == 0 { navy },
  inset: (x: 7pt, y: 6pt),
)
#show table.cell.where(y: 0): set text(fill: white, weight: "bold")
#show table: set text(size: 9pt)
#show table: it => block(radius: 6pt, clip: true, stroke: 0.5pt + rule, it)

// ---------------------------------------------------------------- the flowchart
// Four columns as on the deck's "How it works" slide: indexing, RAG, Apertus, check and export; the web app on top.
#let flowchart = {
  let w = 3.3cm
  let box-node(pos, label, name, ..args) = node(pos, label, name: name, width: w, fill: white, stroke: 0.8pt + rule,
    corner-radius: 5pt, inset: 6pt, ..args)
  let apertus(pos, label, name) = node(pos, text(fill: white, label), name: name, width: w, fill: navy, stroke: none,
    corner-radius: 5pt, inset: 6pt)
  let caption(pos, label, name) = node(pos, text(size: 7pt, weight: "bold", tracking: 0.8pt, fill: muted, label), name: name,
    stroke: none, inset: 2pt)
  let group(nodes) = node(enclose: nodes, fill: cream, stroke: none, corner-radius: 8pt, inset: 7pt, snap: false)
  set text(font: ("Inter", "Liberation Sans"), size: 8pt, fill: body)
  set par(leading: 0.45em)
  align(center, diagram(
    spacing: (5mm, 6mm),
    edge-stroke: 0.8pt + muted,
    mark-scale: 70%,
    label-size: 7.5pt,
    // the cream groups first, so the boxes paint on top of them
    group((<sources>, <preview>)),
    group((<web>, <cap1>)),
    group((<search>, <cap2>)),
    group((<orch>, <cap3>)),

    node((2, -1), text(weight: "bold", fill: heading-navy)[You], name: <you>, stroke: none),
    box-node((0, 0), [Sources and Settings], <sources>),
    caption((1, 0), [WEB APP], <capweb>),
    box-node((2, 0), [Chat], <chat>),
    box-node((3, 0), [Slide preview \ PDF · PowerPoint], <preview>),

    box-node((0, 1.3), [41 websites \ UniBE, ARTORG, DCB], <web>),
    box-node((0, 2.3), [Crawl], <crawl>),
    box-node((0, 3.3), [Clean and split into passages], <clean>),
    box-node((0, 4.3), [Embed \ BGE-M3], <embed>),
    caption((0, 5.05), [1 · INDEXING, OFFLINE], <cap1>),

    box-node((1, 2.3), [Search by meaning], <search>),
    box-node((1, 3.3), [Read full pages], <read>),
    box-node((1, 4.3), [Search index, local], <index>),
    caption((1, 5.05), [2 · RAG], <cap2>),

    apertus((2, 1.3), [Orchestrator \ picks the next tool], <orch>),
    apertus((2, 3.3), [Compose \ items with quotes], <compose>),
    caption((2, 5.05), [3 · APERTUS 70B], <cap3>),

    box-node((3, 1.3), [5 · Export \ Typst, Kanton Bern design], <export>),
    node((3, 3.3), text(fill: white)[4 · Quote check \ every fact \ on its page?], name: <check>,
      shape: fletcher.shapes.diamond, fill: red, stroke: none, inset: 9pt),

    edge(<you>, <chat>, "-|>", [describes a company], label-side: left),
    edge(<sources>, <web>, "-|>", [update index], label-side: left),
    edge(<web>, <crawl>, "-|>"), edge(<crawl>, <clean>, "-|>"), edge(<clean>, <embed>, "-|>"),
    edge(<embed>, <index>, "-|>"),
    edge(<index>, <read>, "-|>"),
    edge(<chat>, <orch>, "<|-|>", [message · answer], label-side: left),
    edge(<orch>, <search>, "-|>", [search · read], label-side: right),
    edge(<read>, <compose>, "-|>"),
    edge(<compose>, <check>, "-|>"),
    edge(<check>, <export>, "-|>", [yes], label-side: right),
    edge(<check>, <orch>, "-|>", [no: rejected, \ told why], label-side: left, label-pos: 45%),
    edge(<export>, <preview>, "-|>"),
  ))
}
#show raw.where(lang: "mermaid"): _ => block(above: 1.2em, below: 1.2em, flowchart)

// ---------------------------------------------------------------- title
#block(width: 100%, fill: navy, inset: (x: 18pt, top: 14pt, bottom: 14pt), radius: 12pt, {
  text(font: "Abhaya Libre", weight: "extrabold", size: 42pt, fill: white)[#text(fill: red)[RAG]lette]
  v(-8pt)
  text(size: 13pt, fill: rgb("#C9D1DC"))[Raclette + RAG · a Research & Expertise Navigator for Bern]
  v(2pt)
  text(size: 9pt, weight: "bold", tracking: 1.5pt, fill: rgb("#A9B1BD"))[BUILT AT HACK APERTUS · MYLIFE WITH TOKENS: DANIELE, HAN, MARC]
})
#v(0.4em)

#cmarker.render(intro)

#v(0.2em)
#block(fill: cream, inset: 12pt, radius: 10pt, width: 100%, {
  set block(spacing: 0.42em)
  set text(size: 9.5pt)
  show outline.entry: it => {
    set text(fill: if it.level == 2 { heading-navy } else { body }, weight: if it.level == 2 { "bold" } else { "regular" })
    it
  }
  outline(title: text(font: "Abhaya Libre", weight: "extrabold", size: 16pt, fill: heading-navy)[Contents],
    target: heading.where(level: 2).or(heading.where(level: 3)), indent: 1.2em)
})

#cmarker.render(rest)
