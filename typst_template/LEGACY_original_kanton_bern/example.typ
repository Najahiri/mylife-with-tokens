// Beispielpräsentation – reproduziert alle 19 Folien der PowerPoint-Vorlage.
#import "kanton-bern.typ": *

#show: kanton-bern.with(
  classification: [Klassifizierung: intern / vertraulich / geheim],
  date: datetime(year: 2026, month: 10, day: 18),
)

// Hinweis-Sprechblase der Vorlage (nur für die Beispielfolien 2 und 3)
#let callout(body) = {
  set text(size: 8.2pt)
  let (x, y, w, h) = (27.44cm, 2.98cm, 5.40cm, 1.88cm)
  let c = lum(accent1, 20%, off: 80%)
  place(top + left, dx: x, dy: y, polygon(fill: c, stroke: none,
    (0cm, 0cm), (w, 0cm), (w, h), (w * 4 / 12, h), (w * 0.171, 2.563cm), (w * 2 / 12, h), (0cm, h)))
  place(top + left, dx: x, dy: y, block(width: w, height: h, inset: (x: 0.3cm, y: 0.2cm),
    align(horizon, text(size: 8.2pt, fill: accent1, top-edge: 0.905em, bottom-edge: "descender", body))))
}

// 1 ─ Titelfolie
#title-slide(
  kicker: [Spitzmarke],
  title: [Titel (maximal 2 Zeilen)],
  subtitle: [Untertitel],
  author: [Referent/-in \ Organisationseinheit],
)

// 2 ─ Titelfolie mit Bild (hell)
#title-slide(
  photo: image("assets/example/photo-light.jpg"),
  kicker: [Spitzmarke],
  title: [Titel (maximal 2 Zeilen)],
  subtitle: [Untertitel],
  author: [Referent/-in \ Organisationseinheit],
  overlay: callout[Hintergrundbild mit Rechtsklick ersetzen («Bild ändern») und Sprechblase löschen.],
)

// 3 ─ Titelfolie mit Bild (dunkel)
#title-slide(
  photo: image("assets/example/photo-dark.jpg"),
  dark: true,
  kicker: [Spitzmarke],
  title: [Titel (maximal 2 Zeilen)],
  subtitle: [Untertitel],
  author: [Referent/-in \ Organisationseinheit],
  overlay: callout[Hintergrundbild mit Rechtsklick ersetzen («Bild ändern») und Sprechblase löschen.],
)

// 4–7 ─ Kapiteltitel
#section-slide([Beispiel Kapiteltitel Schwarz], subtitle: [Untertitel], style: "black")
#section-slide([Beispiel Kapiteltitel Blaugrau], subtitle: [Untertitel], style: "bluegray")
#section-slide([Beispiel Kapiteltitel Weiss], subtitle: [Untertitel], style: "white")
#section-slide([Beispiel Kapiteltitel Rot], subtitle: [Untertitel], style: "red")

// 8 ─ Hinweis zu den Textebenen
#let ribbon = {
  place(top + left, dx: 16.956cm, dy: 10.925cm,
    box(stroke: 0.75pt + lum(bg1, 75%), image("assets/example/ribbon.png", width: 11.40cm, height: 3.088cm)))
  place(top + left, dx: 19.52cm, dy: 11.19cm, rect(width: 1.826cm, height: 0.973cm, stroke: 2.25pt + accent3))
  let red = 2.25pt + rgb("#FF0000")
  place(top + left, dx: 17.00cm, dy: 11.19cm, line(start: (0cm, 0cm), end: (0.855cm, 0.855cm), stroke: red))
  place(top + left, dx: 17.00cm, dy: 11.19cm, line(start: (0.855cm, 0cm), end: (0cm, 0.855cm), stroke: red))
}
#slide(title: [Hinweis zum Erstellen von Aufzählungen], overlay: ribbon)[
  Für Aufzählungen nicht den «Aufzählungs-Button» verwenden \
  sondern mit Textebenen arbeiten. Die Textebenen werden im Absatzformat mit der Funktion #text(fill: accent3)[«Listenebene erhöhen» / «Listenebene verringern»] definiert.

  Textebene 1
  - Textebene 2
    - Textebene 3
      - Textebene 4
        - Textebene 5
]

// 9 ─ Programm
#slide(title: [Programm])[
  + Thema
  + Thema
  + Thema
  + Thema
  + …
]

// 10 ─ Titel und Inhalt
#slide(title: [Beispielfolie «Titel und Inhalt»])[
  Lorem ipsum dolor sit amet, consectetuer adipiscing elit. Maecenas porttitor congue massa. Fusce posuere, magna sed pulvinar ultricies, purus lectus malesuada libero, sit amet commodo magna eros quis urna.

  - Aufzählung (Textebene 2)
  - Aufzählung (Textebene 2)
    - Aufzählung (Textebene 3)
    - Aufzählung (Textebene 3)
]

// 11 ─ Titel, Untertitel und Inhalt
#slide(title: [Beispielfolie «Titel, Untertitel und Inhalt»], subtitle: [Untertitel])[
  Lorem ipsum dolor sit amet, consectetuer adipiscing elit. Maecenas porttitor congue massa. Fusce posuere, magna sed pulvinar ultricies, purus lectus malesuada libero, sit amet commodo magna eros quis urna. Stet clita kasd gubergren, no sea takimata est Lorem ipsum dolor sit amet.

  Fusce posuere, magna sed pulvinar ultricies, purus lectus malesuada libero, sit amet commodo magna eros quis urna.

  #v(1fr)
  Letzte Zeile
]

// 12/13 ─ Titel, Inhalt und Bild rechts / links (Bildplatzhalter leer)
#let lorem-short = [Lorem ipsum dolor sit amet, cons-ectetuer adipiscing elit. Maecenas porttitor congue massa. Fusce pos-uere, magna sed pulvinar ultricies, purus lectus malesuada libero, sit amet commodo magna eros quis urna.]
#image-slide(title: [Beispielfolie «Titel, Inhalt und Bild rechts»], side: right, lorem-short)
#image-slide(title: [Beispielfolie «Titel, Inhalt und Bild links»], side: left, lorem-short)

// 14 ─ Tabelle
#slide(title: [Tabelle])[
  #data-table(
    columns: (14.605cm, 9.001cm, 6.905cm),
    header: ([1\. Spalte], [2\. Spalte], [3\. Spalte]),
    ..range(9).map(_ => ([Text], [0], [0])).flatten(),
  )
]

// 15 ─ Säulendiagramm (rot)
#let abc = "ABCDEFGHIJKL".clusters().enumerate().map(((i, c)) => (c, (i + 1) * 10))
#slide(title: [Beispielfolie Säulendiagramm])[
  #move(dx: -0.20cm, bar-chart(abc, width: 31.0cm, height: 12.98cm, max: 130, step: 10,
    inset: (left: 0.62cm, right: 0.61cm)))
]

// 16 ─ Säulendiagramm (Akzentfarben) mit Text
#two-content-slide(title: [Beispielfolie Säulendiagramm])[
  #move(dx: 0.04cm, dy: -0.08cm)[Lorem ipsum dolor sit amet, cons-ectetuer adipiscing elit. Maecenas porttitor congue massa. Fusce pos-uere, magna sed pulvinar ultricies, purus lectus malesuada libero, sit amet commodo magna eros quis urna.]
][
  #move(dx: -0.20cm, dy: -0.09cm, bar-chart(abc, width: 15.30cm, height: 12.09cm, max: 130, step: 10,
    colors: chart-colors, inset: (left: 0.30cm, right: 0.30cm, top: 0.41cm)))
]

// 17 ─ Kreisdiagramm mit Text und kleiner Tabelle
#two-content-slide(title: [Beispielfolie Kreisdiagramm])[
  #move(dx: 0.04cm, dy: -0.08cm)[Lorem ipsum dolor sit amet, cons-ectetuer adipiscing elit. Maecenas porttitor congue massa.]
  #v(-0.20cm)
  #data-table(
    columns: (11.0cm, 3.84cm),
    align: (left, right),
    size: 13pt,
    header: ([2019], [CHF]),
    [Text], [000],
    [Text], [–0 000],
    [Text], [0 000],
  )
][
  #move(dx: 1.32cm, dy: -0.03cm, donut-chart(
    (20, 20, 30, 40, 50, 60, 70, 80, 90, 100).map(v => ("", v)),
    size: 11.95cm,
  ))
]

// 18 ─ Hinterlegtes Farbkonzept
#blank-slide(title: [Hinterlegtes Farbkonzept])[
  // Farbtabelle: 11 Spalten à 2.774 cm, weisse Trennlinien 4.5 pt
  #let cols = (
    ([Hintergr. 1], bg1), ([Text 1], tx1), ([Hintergr. 2], bg2), ([Text 2], tx2), (none, none),
    ([Akzent 1], accent1), ([Akzent 2], accent2), ([Akzent 3], accent3),
    ([Akzent 4], accent4), ([Akzent 5], accent5), ([Akzent 6], accent6),
  )
  #let cw = 2.774cm
  #let rh = 0.852cm
  #let g = 2.25pt
  #for (i, (label, c)) in cols.enumerate() {
    let x = 2.33cm + cw * i
    if label != none {
      place(top + left, dx: x + 0.354cm, dy: 5.15cm + rh - 0.127cm - 1.117 * 8pt,
        text(size: 8pt, weight: "bold", top-edge: 0.905em, bottom-edge: "descender", label))
      let swatches = (c,) + tints(c)
      for (j, s) in swatches.enumerate() {
        let y = 5.15cm + rh * (j + 1) + if j > 0 { 0.491cm } else { 0cm }
        place(top + left, dx: x + g, dy: y + g, rect(width: cw - 2 * g, height: rh - 2 * g, fill: s, stroke: none))
      }
    }
  }
  #place(top + left, dx: 2.34cm, dy: 12.20cm,
    text(size: 11pt, top-edge: 1.0em, bottom-edge: "descender")[Akzentfarben werden automatisch für Diagramme und SmartArts verwendet])

  // Mini-Säulendiagramm (6 Reihen, eine Kategorie)
  #place(top + left, dx: 2.41cm, dy: 13.60cm, {
    let (pw, ph, py) = (8.707cm, 3.134cm, 0.353cm)
    for k in range(11) {
      place(top + left, line(start: (0cm, py + ph * k / 10), end: (pw, py + ph * k / 10), stroke: 0.75pt + lum(bg1, 85%)))
    }
    let b = pw / 9.54
    let x0 = (pw - 7.35 * b) / 2
    for (i, v) in (5, 7, 6, 9, 8, 10).enumerate() {
      place(top + left, dx: x0 + 1.27 * b * i, dy: py + ph * (1 - v / 10),
        rect(width: b, height: ph * v / 10, fill: accents.at(i), stroke: none))
    }
  })

  // Mini-Ringdiagramm
  #place(top + left, dx: 14.33cm - 1.69cm, dy: 15.42cm - 1.69cm,
    donut-chart((20, 10, 25, 5, 20, 12).map(v => ("", v)), size: 3.38cm, hole: 65%,
      value-labels: false, separator: none))

  // Mini-Blasendiagramm
  #place(top + left, dx: 17.43cm, dy: 13.69cm, {
    let (pw, ph) = (7.69cm, 3.67cm)
    for k in range(11) { place(top + left, line(start: (pw * k / 10, 0cm), end: (pw * k / 10, ph), stroke: 0.75pt + lum(bg1, 85%))) }
    for k in range(8) { place(top + left, line(start: (0cm, ph * k / 7), end: (pw, ph * k / 7), stroke: 0.75pt + lum(bg1, 85%))) }
    let dmax = 0.25 * ph
    for (x, y, s) in ((0.2, 2.7, 10), (1.8, 3.2, 24), (2.6, 0.8, 8), (3, 2, 20), (4.5, 3, 30)) {
      let d = dmax * calc.sqrt(s / 30)
      place(top + left, dx: pw * x / 5 - d / 2, dy: ph * (1 - y / 3.5) - d / 2,
        circle(width: d, fill: accent1.transparentize(25%), stroke: none))
    }
  })

  // Mini-Organigramm (SmartArt)
  #place(top + left, dx: 26.53cm, dy: 12.93cm, {
    let conn(c, ..pts) = {
      let p = pts.pos()
      place(top + left, curve(stroke: 0.75pt + lum(c, 75%), curve.move(p.first()), ..p.slice(1).map(q => curve.line(q))))
    }
    conn(accent2, (2.98cm, 0.82cm), (2.98cm, 0.995cm), (1.49cm, 0.995cm), (1.49cm, 1.17cm))
    conn(accent2, (2.98cm, 0.82cm), (2.98cm, 0.995cm), (4.47cm, 0.995cm), (4.47cm, 1.17cm))
    conn(accent3, (1.49cm, 1.99cm), (1.49cm, 2.34cm))
    conn(accent3, (4.47cm, 1.99cm), (4.47cm, 2.165cm), (3.48cm, 2.165cm), (3.48cm, 2.34cm))
    conn(accent3, (4.47cm, 1.99cm), (4.47cm, 2.165cm), (5.46cm, 2.165cm), (5.46cm, 2.34cm))
    conn(accent4, (0.83cm, 3.16cm), (0.83cm, 3.92cm), (1.08cm, 3.92cm))
    for (x, y, c) in (
      (2.16, 0.0, accent1), (0.66, 1.17, accent2), (3.65, 1.17, accent2),
      (0.66, 2.34, accent3), (2.65, 2.34, accent3), (4.64, 2.34, accent3), (1.08, 3.5, accent4),
    ) {
      place(top + left, dx: x * 1cm, dy: y * 1cm, rect(width: 1.64cm, height: 0.82cm, fill: c, stroke: none))
    }
  })
]

// 19 ─ Kontakt
#slide(title: [Kontakt])[
  Vorname Name \
  Funktion \
  vorname.name\@be.ch \
  +41 31 000 00 00

  #block(above: 1.155cm + 0.533cm, text(size: 13pt)[Dok.-Nr. XXXXX / Aktenzeichen XXXXX])
]
