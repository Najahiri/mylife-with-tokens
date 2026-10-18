// ─────────────────────────────────────────────────────────────
//  RAGlette · HackApertus 2026 · team "Mylife with Tokens"
//  Compile:  typst compile raglette.typ
// ─────────────────────────────────────────────────────────────

// ── Palette (Apertus / Swiss AI: deep black + Swiss red, cyan as tech accent)
#let bg       = rgb("#07080D")
#let surface  = rgb("#10131B")
#let surface2 = rgb("#161A25")
#let line-c   = rgb("#232838")
#let red      = rgb("#E5323B")
#let red-glow = rgb("#FF4D5A")
#let cyan     = rgb("#4FD1FF")
#let ink      = rgb("#F2F3F7")
#let muted    = rgb("#8A90A2")

#let sans = ("Inter", "DejaVu Sans")
#let display = ("Inter Display", "Inter", "DejaVu Sans")
#let mono = ("DejaVu Sans Mono",)

#let event = "HackApertus"
#let team = "Mylife with Tokens"
#let product = "RAGlette"
#let date = datetime(year: 2026, month: 10, day: 18)
#let total = 4

#let accent-grad = gradient.linear(red, red-glow, cyan)

// ── Background: grid tiling + soft red glow + chrome
#let grid-tile = tiling(size: (1.2cm, 1.2cm))[
  #place(line(start: (0pt, 0pt), end: (1.2cm, 0pt), stroke: 0.3pt + rgb("#151925")))
  #place(line(start: (0pt, 0pt), end: (0pt, 1.2cm), stroke: 0.3pt + rgb("#151925")))
]

#let corner(pos, size: 0.6cm, c: red) = {
  let s = 1.2pt + c
  let (dx, dy) = pos
  place(
    if dx == 0 and dy == 0 { top + left } else if dx == 1 and dy == 0 { top + right }
    else if dx == 0 { bottom + left } else { bottom + right },
    dx: if dx == 0 { 1cm } else { -1cm },
    dy: if dy == 0 { 1cm } else { -1cm },
    box(width: size, height: size, {
      let x0 = if dx == 0 { 0pt } else { size }
      let y0 = if dy == 0 { 0pt } else { size }
      let x1 = if dx == 0 { size } else { 0pt }
      let y1 = if dy == 0 { size } else { 0pt }
      place(line(start: (x0, y0), end: (x1, y0), stroke: s))
      place(line(start: (x0, y0), end: (x0, y1), stroke: s))
    }),
  )
}

#let chrome = context {
  let n = counter(page).get().first()
  // grid
  place(rect(width: 100%, height: 100%, fill: grid-tile))
  // glows
  place(top + right, dx: 6cm, dy: -7cm,
    circle(radius: 11cm, fill: gradient.radial(red.transparentize(78%), bg.transparentize(100%))))
  place(bottom + left, dx: -6cm, dy: 7cm,
    circle(radius: 9cm, fill: gradient.radial(cyan.transparentize(88%), bg.transparentize(100%))))
  // corners
  corner((0, 0)); corner((1, 0), c: cyan); corner((0, 1), c: cyan); corner((1, 1))
  // header
  place(top + left, dx: 2cm, dy: 1.05cm, text(font: mono, size: 8pt, fill: muted, tracking: 1.5pt)[
    #text(fill: red)[●] #upper(event) #h(0.4em) \/\/ #h(0.4em) #date.display("[year].[month].[day]")
  ])
  place(top + right, dx: -2cm, dy: 1.05cm, text(font: mono, size: 8pt, fill: muted, tracking: 1.5pt)[
    #upper(product) #h(0.6em) #text(fill: cyan)[◆] #h(0.4em) POWERED BY APERTUS
  ])
  // footer
  place(bottom + left, dx: 2cm, dy: -1.05cm, text(font: mono, size: 8pt, fill: muted, tracking: 1.5pt)[
    TEAM · #upper(team)
  ])
  place(bottom + right, dx: -2cm, dy: -1.05cm, text(font: mono, size: 8pt, fill: muted, tracking: 1.5pt)[
    #text(fill: ink)[#if n < 10 [0]#n] / 0#total
  ])
  place(bottom + left, dx: 2cm, dy: -1.6cm, rect(width: 100% - 4cm, height: 1.2pt, fill: accent-grad))
}

#set page(
  paper: "presentation-16-9",
  margin: (x: 2cm, top: 2.2cm, bottom: 2.3cm),
  fill: bg,
  background: chrome,
)
#set text(font: sans, fill: ink, size: 16pt)
#set par(leading: 0.6em)

// ── Helpers
#let kicker(body) = text(font: mono, size: 9.5pt, fill: red, tracking: 3pt, weight: "bold", upper(body))
#let slide-title(k, t) = block(spacing: 0pt, {
  set par(spacing: 0pt)
  kicker(k)
  v(0.3cm)
  text(font: display, size: 28pt, weight: "bold", tracking: -0.5pt, t)
  v(0.42cm)
  rect(width: 2.4cm, height: 2.5pt, fill: accent-grad)
})
#let tag(body, c: cyan) = box(
  inset: (x: 0.28cm, y: 0.16cm), radius: 2pt, stroke: 0.7pt + c, fill: c.transparentize(90%),
  text(font: mono, size: 8.5pt, fill: c, tracking: 1.2pt, upper(body)),
)

// ═════════════════════════════════════════════════════════════
//  01 · TITLE
// ═════════════════════════════════════════════════════════════
#{
  // decorative orbit rings on the right
  place(right + horizon, dx: 0.6cm, {
    for (r, c, w) in ((6.2cm, line-c, 0.6pt), (4.8cm, red.transparentize(40%), 0.9pt),
                      (3.4cm, line-c, 0.6pt), (2.0cm, cyan.transparentize(40%), 0.9pt)) {
      place(center + horizon, circle(radius: r, stroke: (paint: c, thickness: w, dash: if c == line-c { "dotted" } else { "solid" })))
    }
    place(center + horizon, circle(radius: 0.55cm, fill: gradient.radial(red-glow, red, red.darken(40%))))
    place(center + horizon, dx: 4.8cm, circle(radius: 0.14cm, fill: red-glow))
    place(center + horizon, dx: -2.0cm * calc.cos(35deg), dy: -2.0cm * calc.sin(35deg), circle(radius: 0.11cm, fill: cyan))
    place(center + horizon, dx: 3.4cm * calc.cos(200deg), dy: 3.4cm * calc.sin(200deg), circle(radius: 0.09cm, fill: ink))
  })

  v(1fr)
  tag[#event · Hackathon]
  h(0.25cm)
  tag(c: red)[#date.display("[day] [month repr:long] [year]")]
  v(0.5cm)
  box(text(font: display, size: 66pt, weight: "black", tracking: -2.5pt, fill: accent-grad)[#product])
  v(0.1cm)
  block(width: 15cm, text(size: 15pt, fill: muted)[
    Retrieval-augmented answers, grounded in your documents — powered by the open Swiss model *#text(fill: ink)[Apertus]*.
  ])
  v(0.6cm)
  grid(columns: 2, column-gutter: 0.35cm, align: horizon,
    rect(width: 3pt, height: 1.1cm, fill: red),
    [
      #text(font: mono, size: 8.5pt, fill: muted, tracking: 2pt)[PRESENTED BY] \
      #text(size: 16pt, weight: "semibold")[#team]
    ],
  )
  v(1fr)
}

// ═════════════════════════════════════════════════════════════
//  02 · TEAM
// ═════════════════════════════════════════════════════════════
#pagebreak()
#let member(n) = rect(
  width: 100%, inset: 0.45cm, radius: 4pt, fill: surface, stroke: 0.6pt + line-c,
  {
    // photo placeholder — replace the rect with: image("photos/name.jpg", width: 100%, height: 5cm, fit: "cover")
    let ph = rect(
      width: 100%, height: 5cm, radius: 3pt, fill: surface2,
      stroke: (paint: cyan.transparentize(55%), thickness: 0.8pt, dash: "dashed"),
      align(center + horizon, {
        circle(radius: 0.75cm, stroke: 1pt + muted.transparentize(30%),
          align(center + horizon, text(font: mono, size: 14pt, fill: muted)[0#n]))
        v(0.2cm)
        text(font: mono, size: 8pt, fill: muted, tracking: 2pt)[PHOTO PLACEHOLDER]
      }),
    )
    box(ph)
    v(0.35cm)
    text(font: mono, size: 8pt, fill: red, tracking: 2pt)[MEMBER · 0#n]
    v(0.1cm)
    text(size: 17pt, weight: "bold")[[Name Surname #n]]
    linebreak()
    text(size: 11pt, fill: muted)[[Role / focus area]]
  },
)

#slide-title[02 \/\/ The Team][#team]
#v(0.55cm)
#grid(columns: (1fr, 1fr, 1fr), column-gutter: 0.6cm, member(1), member(2), member(3))

// ═════════════════════════════════════════════════════════════
//  03 · AGENDA
// ═════════════════════════════════════════════════════════════
#pagebreak()
#slide-title[03 \/\/ Overview][What's coming up]
#v(0.7cm)

#let agenda = (
  ([The Challenge], [Why answers from internal documents are hard to trust]),
  ([Meet #product], [Our idea and what it does for the user]),
  ([Architecture], [Ingest → index → retrieve → generate with Apertus]),
  ([Live Demo], [#product answering real questions, with sources]),
  ([Results & Next Steps], [What worked, what we learned, where it goes next]),
)

#grid(
  columns: (1fr, 1fr), column-gutter: 0.8cm, row-gutter: 0.45cm,
  ..agenda.enumerate().map(((i, item)) => {
    let (title, desc) = item
    let hot = i == 2
    rect(width: 100%, inset: (x: 0.5cm, y: 0.55cm), radius: 3pt,
      fill: if hot { red.transparentize(88%) } else { surface },
      stroke: (left: 2.5pt + (if hot { red } else { cyan.transparentize(40%) }), rest: 0.5pt + line-c),
      grid(columns: (1.4cm, 1fr), align: (left + horizon, left + horizon),
        text(font: mono, size: 20pt, weight: "bold", fill: if hot { red } else { cyan })[0#(i + 1)],
        [
          #text(size: 15pt, weight: "semibold")[#title] \
          #text(size: 10.5pt, fill: muted)[#desc]
        ],
      ),
    )
  }),
  // closing cell: Q&A hint
  rect(width: 100%, inset: (x: 0.5cm, y: 0.55cm), radius: 3pt, stroke: (paint: line-c, dash: "dashed"),
    grid(columns: (1.4cm, 1fr), align: (left + horizon, left + horizon),
      text(font: mono, size: 20pt, weight: "bold", fill: muted)[?\_],
      [
        #text(size: 15pt, weight: "semibold", fill: muted)[Q & A] \
        #text(size: 10.5pt, fill: muted)[Questions from the jury]
      ],
    ),
  ),
)

// ═════════════════════════════════════════════════════════════
//  04 · ARCHITECTURE (Mermaid)
// ═════════════════════════════════════════════════════════════
#pagebreak()
#grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
  slide-title[04 \/\/ Architecture][The #product pipeline],
  {
    tag[Hybrid retrieval]
    h(0.2cm)
    tag(c: red)[Apertus LLM]
  },
)
#v(0.45cm)
#align(center, image("architecture.png", height: 1fr))
