// =============================================================================
//  Kanton Bern – Präsentationsvorlage für Typst
//  Nachbau der PowerPoint-Vorlage (16:9, 33.867 × 19.05 cm)
//
//  Verwendung:
//    #import "kanton-bern.typ": *
//    #show: kanton-bern.with(
//      classification: [Klassifizierung: intern],
//      date: auto,                       // auto = heutiges Datum, deutsch
//    )
//    #title-slide(kicker: [Spitzmarke], title: [Titel], subtitle: [Untertitel],
//                 author: [Referent/-in \ Organisationseinheit])
//    #slide(title: [Titel])[ Text … ]
//
//  Alle Masse stammen 1:1 aus dem Folienmaster / den Layouts der .pptx.
//  Zeilenabstand wie PowerPoint: Zeilenhöhe = 1.2 × Schriftgrösse × Abstand.
// =============================================================================

// ---------------------------------------------------------------- Farbschema
// Theme "Kanton Bern" (theme1.xml)
#let tx1 = rgb("#000000")      // Text 1
#let bg1 = rgb("#FFFFFF")      // Hintergrund 1
#let tx2 = rgb("#63737B")      // Text 2
#let bg2 = rgb("#B1B9BD")      // Hintergrund 2
#let accent1 = rgb("#3C505A")  // Blaugrau
#let accent2 = rgb("#96D7F0")  // Hellblau
#let accent3 = rgb("#A0C7A0")  // Hellgrün
#let accent4 = rgb("#E1D2C6")  // Sand
#let accent5 = rgb("#644B41")  // Braun
#let accent6 = rgb("#EA161F")  // Bern-Rot
#let grey = rgb("#999999")     // Untertitel
#let pink = rgb("#F69CA0")     // Untertitel auf Rot

#let accents = (accent1, accent2, accent3, accent4, accent5, accent6)

/// PowerPoint-Farbvariante (lumMod / lumOff im HSL-Raum).
/// `lum(accent1, 20%, off: 80%)` entspricht "Akzent 1, heller 80 %".
#let lum(c, mod, off: 0%) = {
  let (h, s, l, ..) = color.hsl(c).components()
  let v = calc.clamp(l / 100% * (mod / 100%) + off / 100%, 0, 1)
  rgb(color.hsl(h, s, v * 100%))
}

/// Farbreihenfolge der Diagramme (wie in den Beispieldiagrammen):
/// Akzent 1–6, danach Akzent 1–6 um 40 % abgedunkelt.
#let chart-colors = accents + accents.map(c => lum(c, 60%))

/// Die fünf Varianten, die PowerPoint in der Farbpalette anbietet.
#let tints(c) = {
  if c == bg1 { (95%, 85%, 75%, 65%, 50%).map(m => lum(c, m)) }
  else if c == tx1 { (50%, 35%, 25%, 15%, 5%).map(o => lum(c, 100% - o, off: o)) }
  else if c == accent4 {(90%, 75%, 50%, 25%, 10%).map(m => lum(c, m)) }
  else {
    ((20%, 80%), (40%, 60%), (60%, 40%), (75%, 0%), (50%, 0%)).map(((m, o)) => lum(c, m, off: o))
  }
}

// ---------------------------------------------------------------- Grundmasse
#let slide-width = 33.867cm
#let slide-height = 19.05cm
#let fonts = ("Arial", "Liberation Sans")

// Inhaltsbereich (Folienmaster)
#let _x = 2.33cm
#let _w = 30.51cm
#let _col-w = 14.81cm   // linke Spalte
#let _col2-x = 18.04cm  // rechte Spalte
#let _col2-w = 14.80cm

#let _months = (
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
)
/// Datum im Stil der Vorlage: "18. Oktober 2026".
#let german-date(d) = [#d.day(). #_months.at(d.month() - 1) #d.year()]

#let _cfg = state("kanton-bern-config", (
  classification: [Klassifizierung: intern / vertraulich / geheim],
  date: german-date(datetime.today()),
))

// ---------------------------------------------------------------- Textstile
/// Zeilenabstand wie PowerPoint: Zeilenhöhe = 1.2 em × `spacing`,
/// zusätzlicher Raum über der Zeile. Ein Absatzwechsel entspricht einer
/// Leerzeile (in der Vorlage werden Absätze mit leeren Zeilen getrennt).
#let lines(spacing: 105%, body) = {
  let pitch = 1.2 * (spacing / 100%)
  set text(top-edge: (pitch - 0.212) * 1em, bottom-edge: "descender")
  set par(leading: 0pt, spacing: pitch * 1em)
  set block(spacing: pitch * 1em)
  body
}

// Box an absoluter Position; `anchor: bottom` wächst nach oben (wie PowerPoint).
#let _at(x, y, w, h, anchor: top, body) = {
  if anchor == bottom {
    context {
      let b = block(width: w, body)
      let m = measure(b)
      place(top + left, dx: x, dy: y + h - m.height, b)
    }
  } else {
    place(top + left, dx: x, dy: y, block(width: w, height: h, breakable: false, body))
  }
}

// ---------------------------------------------------------------- Kopfzeile
// Logo links, Klassifizierung / Datum / Foliennummer rechts (8.2 pt).
#let _header(inverse: false) = {
  let fg = if inverse { bg1 } else { tx1 }
  let logo = if inverse { "assets/logo-white.svg" } else { "assets/logo-black.svg" }
  place(top + left, dx: 0.81cm, dy: 0.50cm, image(logo, width: 4.12cm, height: 1.93cm))
  set text(size: 8.2pt, fill: fg)
  show: lines.with(spacing: 100%)
  context {
    let cfg = _cfg.get()
    _at(25.93cm, 0.83cm, 5.80cm, 0.35cm, anchor: bottom, cfg.classification)
    _at(25.93cm, 1.21cm, 5.80cm, 0.30cm, cfg.date)
    _at(31.93cm, 0.83cm, 0.89cm, 0.30cm, align(right, counter(page).display()))
  }
}

// Grundgerüst jeder Folie
#let _slide(fill: bg1, inverse: false, header: true, background: none, overlay: none, body) = page(
  fill: fill,
  margin: 0pt,
  background: {
    if background != none { background }
    if header { _header(inverse: inverse) }
  },
  foreground: overlay,
  body,
)

// Titel einer Inhaltsfolie: 34 pt, oben verankert
#let _title(title, height: 1.72cm) = {
  if title != none {
    _at(_x, 2.98cm, _w, height, {
      set text(size: 34pt)
      show: lines.with(spacing: 100%)
      title
    })
  }
}

// Inhaltsbereich: 26 pt, Textebenen über Absätze (Ebene 1) und Listen (Ebene 2–5)
#let _content(x, y, w, h, body) = _at(x, y, w, h, {
  set text(size: 26pt)
  show: lines
  body
})

#let _photo(x, y, w, h, img) = {
  if img != none {
    place(top + left, dx: x, dy: y, block(width: w, height: h, clip: true, {
      set image(width: w, height: h, fit: "cover")
      img
    }))
  }
}

// ---------------------------------------------------------------- Dokument
/// Hauptfunktion: `#show: kanton-bern.with(...)`.
/// - classification: Text der Klassifizierung (Kopfzeile rechts)
/// - date: `auto` (heute, deutsch formatiert), Inhalt oder `datetime`
#let kanton-bern(
  classification: [Klassifizierung: intern / vertraulich / geheim],
  date: auto,
  lang: "de",
  region: "ch",
  font: fonts,
  body,
) = {
  let date = if date == auto { german-date(datetime.today()) }
    else if type(date) == datetime { german-date(date) }
    else { date }
  set document(date: none)
  set page(width: slide-width, height: slide-height, margin: 0pt)
  set text(font: font, lang: lang, region: region, size: 26pt, fill: tx1, hyphenate: false)

  // Aufzählungen: Ebene 2–5 mit Halbgeviertstrich «‒», Einzug 1 cm
  set list(
    marker: (
      box(width: 0.992cm, align(start)[‒]), box(width: 0.997cm, align(start)[‒]),
      box(width: 1.010cm, align(start)[‒]), box(width: 0.992cm, align(start)[‒]),
    ),
    indent: 0pt,
    body-indent: 0pt,
    spacing: 0pt,
  )
  // Nummerierung: «1.» mit Einzug 1.24 cm
  set enum(
    numbering: (..n) => box(width: 1.244cm, align(start, numbering("1.", n.pos().last()))),
    indent: 0pt,
    body-indent: 0pt,
    spacing: 0pt,
    number-align: start + top,
  )
  set table(stroke: none)
  set line(stroke: 0.75pt + bg2)

  _cfg.update((classification: classification, date: date))
  body
}

// ---------------------------------------------------------------- Titelfolien
/// Titelfolie (Layouts «Titelfolie», «Titelfolie mit Bild (hell/dunkel)»).
/// - photo: z. B. `image("bild.jpg")` – füllt die ganze Folie (randabfallend)
/// - dark: helle Schrift und weisses Logo (für dunkle Bilder)
/// - veil: optionale transparente Fläche über dem Bild (Breite, z. B. `60%`)
#let title-slide(
  kicker: none,
  title: none,
  subtitle: none,
  author: none,
  photo: none,
  dark: false,
  veil: none,
  overlay: none,
) = {
  let fg = if dark { bg1 } else { tx1 }
  let bg = {
    _photo(0cm, 0cm, slide-width, slide-height, photo)
    if veil != none {
      let vw = if type(veil) == ratio { slide-width * (veil / 100%) } else { veil }
      let vc = if dark { accent1 } else { bg1 }
      place(top + left, rect(width: vw, height: slide-height, fill: vc.transparentize(30.2%)))
    }
  }
  _slide(inverse: dark, background: bg, overlay: overlay, {
    // Spitzmarke: 13 pt fett, Rot (auf dunklem Bild weiss)
    if kicker != none {
      _at(_x + 0.05cm, 5.23cm, 14.55cm, 0.70cm, {
        set text(size: 13pt, weight: "bold", tracking: -0.2pt, fill: if dark { bg1 } else { accent6 })
        show: lines
        kicker
      })
    }
    // Titel: 51 pt, unten verankert (max. 2 Zeilen)
    _at(_x, 5.92cm, 23.60cm, 4.33cm, anchor: bottom, {
      set text(size: 51pt, fill: fg)
      show: lines
      title
    })
    // Untertitel: 51 pt grau
    if subtitle != none {
      _at(_x, 10.44cm, 23.60cm, 4.17cm, {
        set text(size: 51pt, fill: grey)
        show: lines
        subtitle
      })
    }
    // Referent/-in, Organisationseinheit: 13 pt, unten verankert
    if author != none {
      _at(_x, 16.76cm, 14.60cm, 1.20cm, anchor: bottom, {
        set text(size: 13pt, fill: fg)
        show: lines
        author
      })
    }
  })
}

/// Kapiteltitel. style: "white" | "black" | "bluegray" | "red"
/// (Layouts «Kapiteltitel Weiss / Schwarz / Blaugrau / Rot»)
#let section-slide(title, subtitle: none, style: "white") = {
  let (fill, inverse, sub) = (
    white: (bg1, false, grey),
    black: (tx1, true, grey),
    bluegray: (accent1, true, lum(tx2, 40%, off: 60%)),
    red: (accent6, true, pink),
  ).at(style)
  _slide(fill: fill, inverse: inverse, {
    _at(_x, 5.92cm, 23.60cm, 2.04cm, anchor: bottom, {
      set text(size: 51pt, fill: if inverse { bg1 } else { tx1 })
      show: lines
      title
    })
    if subtitle != none {
      _at(_x, 8.12cm, 23.60cm, 4.64cm, {
        set text(size: 51pt, fill: sub)
        show: lines
        subtitle
      })
    }
  })
}

// ---------------------------------------------------------------- Inhaltsfolien
/// «Titel und Inhalt» bzw. «Titel, Untertitel und Inhalt» (mit `subtitle`).
/// overlay (alle Folientypen): zusätzliche, absolut positionierte Elemente
/// (z. B. `place(top + left, dx: 17cm, dy: 11cm, image(…))`), Koordinaten
/// relativ zur Folie.
#let slide(title: none, subtitle: none, overlay: none, body) = _slide(overlay: overlay, {
  if subtitle == none {
    _title(title)
    _content(_x, 5.15cm, _w, 12.98cm, body)
  } else {
    _title(title, height: 1.50cm)
    _at(_x, 4.53cm, _w, 1.55cm, {
      set text(size: 34pt, fill: grey)
      show: lines
      subtitle
    })
    _content(_x, 6.72cm, _w, 11.40cm, body)
  }
})

/// «Zwei Inhalte»: zwei Spalten à 14.8 cm.
#let two-content-slide(title: none, overlay: none, left, right) = _slide(overlay: overlay, {
  _title(title)
  _content(_x, 5.15cm, _col-w, 12.98cm, left)
  _content(_col2-x, 5.15cm, _col2-w, 12.98cm, right)
})

/// «Titel, Inhalt und Bild rechts/links».
/// photo: `image("…")`, wird auf 14.81 × 12.52 cm zugeschnitten.
#let image-slide(title: none, photo: none, side: right, body) = _slide({
  _title(title)
  if side == right {
    _content(_x, 5.15cm, _col-w, 12.98cm, body)
    _photo(18.03cm, 5.32cm, 14.81cm, 12.52cm, photo)
  } else {
    _photo(_x, 5.32cm, 14.81cm, 12.52cm, photo)
    _content(_col2-x, 5.15cm, _col2-w, 12.98cm, body)
  }
})

/// «Titel und Bild»: Bild über die ganze Inhaltsbreite (30.51 × 12.52 cm).
#let title-image-slide(title: none, photo: none) = _slide({
  _title(title)
  _photo(_x, 5.32cm, _w, 12.52cm, photo)
})

/// «Nur Titel» / «Leer»: freie Fläche; Inhalte mit `place` absolut positionieren
/// (Koordinaten relativ zur Folie).
#let blank-slide(title: none, body) = _slide({
  _title(title)
  set text(size: 26pt)
  show: lines
  body
})

// ---------------------------------------------------------------- Tabellen
/// Tabelle im Stil der Vorlage: Kopfzeile 13 pt unten verankert, graue
/// Trennlinien (Hintergrund 2), keine senkrechten Linien.
/// - size: Schriftgrösse der Tabellenzeilen (Vorlage: 26 pt oder 13 pt)
/// - row-height: Mindesthöhe (Vorlage: 1.03 cm bzw. 0.8 cm)
#let data-table(
  columns: auto,
  align: auto,
  header: (),
  size: 26pt,
  row-height: auto,
  ..cells,
) = {
  let rh = if row-height == auto { if size >= 20pt { 1.03cm } else { 0.8cm } } else { row-height }
  let ncols = if type(columns) == array { columns.len() } else if type(columns) == int { columns } else { header.len() }
  let aligns = if align == auto { range(ncols).map(_ => left) } else if type(align) == array { align } else { range(ncols).map(_ => align) }
  let pad-y = calc.max(0.03cm, (rh - 1.117 * size) / 2)
  let head-top = calc.max(0.03cm, rh - 0.2cm - 1.117 * 13pt)
  set text(size: size, top-edge: 0.905em, bottom-edge: "descender")
  set par(leading: 0.2 * 1em, spacing: 0.2em)
  table(
    columns: columns,
    stroke: (bottom: 0.75pt + bg2),
    inset: (x: 0pt, top: pad-y, bottom: pad-y),
    align: (col, _) => aligns.at(calc.rem(col, aligns.len())) + horizon,
    ..if header.len() > 0 {
      (table.header(..header.enumerate().map(((i, h)) => table.cell(
        inset: (x: 0pt, top: head-top, bottom: 0.2cm),
        align: aligns.at(calc.rem(i, aligns.len())) + bottom,
        text(size: 13pt, h),
      ))),)
    },
    ..cells,
  )
}

// ---------------------------------------------------------------- Diagramme
#let _nice-step(v) = {
  let raw = v / 10
  let mag = calc.pow(10.0, calc.floor(calc.log(raw, base: 10)))
  for f in (1, 2, 2.5, 5, 10) { if raw <= f * mag { return f * mag } }
  10 * mag
}

#let _fmt(v) = {
  let s = if calc.fract(v) == 0 { str(int(v)) } else { str(v) }
  s
}

/// Säulendiagramm im Stil der Vorlage.
/// data: Array von (Kategorie, Wert)
/// colors: eine Farbe (Vorlage: Rot) oder Array (z. B. `chart-colors`)
#let bar-chart(
  data,
  width: _w,
  height: 12.98cm,
  colors: accent6,
  max: auto,
  step: auto,
  gap: 48%,
  value-labels: true,
  inset: (left: 0.3cm, right: 0.3cm, top: 0.42cm, bottom: 0.28cm),
) = context {
  let colors = if type(colors) == color { (colors,) } else { colors }
  let vals = data.map(d => d.at(1))
  let vmax = calc.max(..vals)
  let step = if step == auto { _nice-step(vmax) } else { step }
  let ymax = if max == auto { (calc.floor(vmax / step) + 1) * step } else { max }
  let ticks = range(int(calc.round(ymax / step)) + 1).map(i => i * step)

  let edge = (top-edge: 0.905em, bottom-edge: "descender")
  let ylab(v) = text(size: 8.2pt, fill: bg2, ..edge, _fmt(v))
  let clab(c) = text(size: 13pt, fill: tx1, ..edge, c)
  let lw = calc.max(..ticks.map(t => measure(ylab(t)).width))
  let ch = measure(clab[A]).height

  let ins = (left: 0.3cm, right: 0.3cm, top: 0.42cm, bottom: 0.28cm) + inset
  let x0 = ins.left + lw + 0.11cm
  let x1 = width - ins.right
  let y0 = ins.top
  let y1 = height - ins.bottom - ch - 0.07cm
  let ypos(v) = y1 - (y1 - y0) * (v / ymax)
  let n = data.len()
  let cw = (x1 - x0) / n
  let bw = cw / (1 + gap / 100%)

  box(width: width, height: height, {
    for t in ticks {
      let y = ypos(t)
      place(top + left, line(start: (x0, y), end: (x1, y), stroke: 0.75pt + bg2))
      let l = ylab(t)
      let m = measure(l)
      place(top + left, dx: x0 - 0.11cm - m.width, dy: y - m.height / 2, l)
    }
    for (i, (cat, v)) in data.enumerate() {
      let cx = x0 + cw * (i + 0.5)
      let y = ypos(v)
      place(top + left, dx: cx - bw / 2, dy: y,
        rect(width: bw, height: y1 - y, fill: colors.at(calc.rem(i, colors.len())), stroke: none))
      if value-labels {
        let l = clab(_fmt(v))
        let m = measure(l)
        place(top + left, dx: cx - m.width / 2, dy: y - 0.12cm - m.height, l)
      }
      let l = clab(cat)
      let m = measure(l)
      place(top + left, dx: cx - m.width / 2, dy: y1 + 0.07cm, l)
    }
  })
}

/// Ringdiagramm (Kreisdiagramm der Vorlage).
/// data: Array von (Kategorie, Wert); Start oben, im Uhrzeigersinn.
#let donut-chart(
  data,
  size: 11.95cm,
  hole: 70%,
  colors: chart-colors,
  value-labels: true,
  label-color: bg1,
  separator: 0.75pt + bg1,
) = context {
  let total = data.map(d => d.at(1)).sum()
  let R = size / 2
  let r = R * (hole / 100%)
  box(width: size, height: size, {
    let a = -90deg
    for (i, (cat, v)) in data.enumerate() {
      let sweep = 360deg * (v / total)
      let steps = calc.max(2, int(calc.ceil(sweep / 2deg)))
      let pts = ()
      for k in range(steps + 1) {
        let t = a + sweep * (k / steps)
        pts.push((R + R * calc.cos(t), R + R * calc.sin(t)))
      }
      for k in range(steps + 1).rev() {
        let t = a + sweep * (k / steps)
        pts.push((R + r * calc.cos(t), R + r * calc.sin(t)))
      }
      place(top + left, polygon(fill: colors.at(calc.rem(i, colors.len())), stroke: separator, ..pts))
      if value-labels {
        let mid = a + sweep / 2
        let rm = (R + r) / 2
        let l = text(size: 13pt, fill: label-color, top-edge: 0.905em, bottom-edge: "descender", _fmt(v))
        let m = measure(l)
        place(top + left, dx: R + rm * calc.cos(mid) - m.width / 2, dy: R + rm * calc.sin(mid) - m.height / 2, l)
      }
      a += sweep
    }
  })
}
