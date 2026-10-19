import { useEffect, useRef } from "react";

type Node = { hx: number; hy: number; x: number; y: number; z: number; hub: boolean; accent: boolean; phase: number };
type Edge = { a: number; b: number; long: boolean };
type Pulse = { edge: number; forward: boolean; t: number };

const AREA_PER_CLUSTER = 190000;   // px² per cluster: the density
const PULSE_EVERY = 650;           // ms between new signals
const PULSE_TIME = 1500;           // ms a signal needs along its edge
const DRIFT = 0.006;               // px per ms the whole graph drifts

/** Animated background: a knowledge graph. Clusters of nodes around a hub, fixed links between them and between
 *  the hubs, signals travelling along the links. Each cluster sits at its own depth and shifts with the pointer for a
 *  3D feel; the node under the pointer lights up with its links and neighbours. Behind the whole UI, never catches
 *  clicks; pauses in a hidden tab and stands still with reduced motion. */
export function BackgroundField() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const darkScheme = window.matchMedia("(prefers-color-scheme: dark)");
    let width = 0, height = 0, frame = 0, last = 0, clock = 0, sincePulse = 0;
    let nodes: Node[] = [], edges: Edge[] = [], pulses: Pulse[] = [];
    let neighbours: number[][] = [];
    const pointer = { x: -9999, y: -9999, px: 0, py: 0 };

    function seed() {
      nodes = []; edges = []; pulses = [];
      const clusters = Math.max(4, Math.round((width * height) / AREA_PER_CLUSTER));
      const cols = Math.ceil(Math.sqrt(clusters * (width / height)));
      const rows = Math.ceil(clusters / cols);
      const hubs: number[] = [];
      for (let k = 0; k < clusters; k++) {
        // hubs on a loose grid, so the clusters spread over the screen
        const cx = ((k % cols) + 0.2 + Math.random() * 0.6) * (width / cols);
        const cy = (Math.floor(k / cols) + 0.2 + Math.random() * 0.6) * (height / rows);
        const z = 0.45 + Math.random() * 0.55;
        const hub = nodes.push({ hx: cx, hy: cy, x: cx, y: cy, z, hub: true, accent: Math.random() < 0.3, phase: Math.random() * 6.3 }) - 1;
        hubs.push(hub);
        const count = 5 + Math.floor(Math.random() * 4);
        const members: number[] = [];
        for (let m = 0; m < count; m++) {
          const angle = (m / count) * Math.PI * 2 + Math.random() * 0.5;
          const dist = (55 + Math.random() * 75) * (0.6 + z * 0.6);
          const x = cx + Math.cos(angle) * dist, y = cy + Math.sin(angle) * dist;
          const i = nodes.push({ hx: x, hy: y, x, y, z, hub: false, accent: Math.random() < 0.14, phase: Math.random() * 6.3 }) - 1;
          members.push(i);
          edges.push({ a: hub, b: i, long: false });
        }
        for (let m = 0; m < members.length; m++)       // a few links between neighbours in the cluster
          if (Math.random() < 0.3) edges.push({ a: members[m], b: members[(m + 1) % members.length], long: false });
      }
      for (const h of hubs) {                          // every hub to its nearest one or two hubs
        const near = hubs.filter((o) => o !== h)
          .sort((a, b) => Math.hypot(nodes[a].hx - nodes[h].hx, nodes[a].hy - nodes[h].hy)
                        - Math.hypot(nodes[b].hx - nodes[h].hx, nodes[b].hy - nodes[h].hy))
          .slice(0, Math.random() < 0.5 ? 1 : 2);
        for (const o of near)
          if (!edges.some((e) => (e.a === h && e.b === o) || (e.a === o && e.b === h))) edges.push({ a: h, b: o, long: true });
      }
      neighbours = nodes.map(() => []);
      edges.forEach((e, i) => { neighbours[e.a].push(i); neighbours[e.b].push(i); });
    }

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      el!.width = width * ratio;
      el!.height = height * ratio;
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);
      seed();
    }

    // drawn position: home + gentle wobble + slow drift of the whole graph + parallax with the pointer
    function place(dt: number) {
      clock += dt;
      pointer.px += ((pointer.x < 0 ? 0 : pointer.x / width - 0.5) - pointer.px) * 0.05;
      pointer.py += ((pointer.y < 0 ? 0 : pointer.y / height - 0.5) - pointer.py) * 0.05;
      const span = width + 300;
      for (const n of nodes) {
        const drift = (clock * DRIFT * (0.5 + n.z)) % span;
        let x = n.hx + drift;
        if (x > width + 150) x -= span;
        n.x = x + Math.sin(clock * 0.0007 + n.phase) * 6 - pointer.px * 60 * n.z;
        n.y = n.hy + Math.cos(clock * 0.0006 + n.phase) * 6 - pointer.py * 60 * n.z;
      }
    }

    function step(dt: number) {
      sincePulse += dt;
      if (sincePulse > PULSE_EVERY && edges.length) {
        sincePulse = 0;
        pulses.push({ edge: Math.floor(Math.random() * edges.length), forward: Math.random() < 0.5, t: 0 });
      }
      pulses = pulses.filter((p) => (p.t += dt / PULSE_TIME) < 1);
    }

    function draw() {
      const dark = document.documentElement.classList.contains("dark") || darkScheme.matches;
      const ink = dark ? "170, 195, 232" : "22, 44, 86";
      const red = "229, 9, 20";
      const paper = dark ? "12, 22, 40" : "255, 255, 255";
      ctx!.clearRect(0, 0, width, height);

      // the node under the pointer, its links and neighbours are highlighted
      let focus = -1, focusD = 70;
      nodes.forEach((n, i) => {
        const d = Math.hypot(n.x - pointer.x, n.y - pointer.y);
        if (d < focusD * (n.hub ? 1.3 : 1)) { focus = i; focusD = d; }
      });
      const litEdges = new Set(focus >= 0 ? neighbours[focus] : []);
      const litNodes = new Set<number>(focus >= 0 ? [focus] : []);
      litEdges.forEach((e) => { litNodes.add(edges[e].a); litNodes.add(edges[e].b); });

      edges.forEach((e, i) => {
        const a = nodes[e.a], b = nodes[e.b];
        if (Math.abs(a.x - b.x) > width / 2) return;     // the graph wrapped around the edge of the screen
        const z = Math.min(a.z, b.z);
        const lit = litEdges.has(i);
        ctx!.strokeStyle = lit ? `rgba(${red}, 0.7)` : `rgba(${ink}, ${(e.long ? 0.12 : 0.22) * z * (dark ? 1.4 : 1)})`;
        ctx!.lineWidth = lit ? 1.6 : e.long ? 0.8 : 1.1;
        ctx!.setLineDash(e.long && !lit ? [3, 5] : []);
        // a slight curve, so links read as drawn connections, not a mesh
        const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.08, my = (a.y + b.y) / 2 - (b.x - a.x) * 0.08;
        ctx!.beginPath(); ctx!.moveTo(a.x, a.y); ctx!.quadraticCurveTo(mx, my, b.x, b.y); ctx!.stroke();
      });
      ctx!.setLineDash([]);

      for (const p of pulses) {
        const e = edges[p.edge];
        if (!e) continue;
        const a = nodes[p.forward ? e.a : e.b], b = nodes[p.forward ? e.b : e.a];
        if (Math.abs(a.x - b.x) > width / 2) continue;
        const mx = (nodes[e.a].x + nodes[e.b].x) / 2 + (nodes[e.b].y - nodes[e.a].y) * 0.08;
        const my = (nodes[e.a].y + nodes[e.b].y) / 2 - (nodes[e.b].x - nodes[e.a].x) * 0.08;
        const t = p.t, u = 1 - t;                         // point on the same curve
        const x = u * u * a.x + 2 * u * t * mx + t * t * b.x, y = u * u * a.y + 2 * u * t * my + t * t * b.y;
        const fade = Math.sin(t * Math.PI);
        ctx!.fillStyle = `rgba(${red}, ${0.16 * fade})`;
        ctx!.beginPath(); ctx!.arc(x, y, 8, 0, Math.PI * 2); ctx!.fill();
        ctx!.fillStyle = `rgba(${red}, ${0.9 * fade})`;
        ctx!.beginPath(); ctx!.arc(x, y, 2.3, 0, Math.PI * 2); ctx!.fill();
      }

      nodes.forEach((n, i) => {
        const lit = litNodes.has(i);
        const r = (n.hub ? 6.5 : 3.6) * (0.65 + n.z * 0.55) * (i === focus ? 1.35 : 1);
        const colour = lit || n.accent ? red : ink;
        const alpha = lit ? 0.95 : (n.accent ? 0.55 : dark ? 0.7 : 0.5) * (0.5 + n.z * 0.5);
        ctx!.fillStyle = `rgba(${colour}, ${alpha * 0.14})`;                 // soft halo
        ctx!.beginPath(); ctx!.arc(n.x, n.y, r * 2.6, 0, Math.PI * 2); ctx!.fill();
        ctx!.fillStyle = `rgba(${colour}, ${alpha})`;
        ctx!.beginPath(); ctx!.arc(n.x, n.y, r, 0, Math.PI * 2); ctx!.fill();
        if (n.hub) {                                                          // hubs: ring with a light centre
          ctx!.fillStyle = `rgba(${paper}, ${0.9 * (0.5 + n.z * 0.5)})`;
          ctx!.beginPath(); ctx!.arc(n.x, n.y, r * 0.45, 0, Math.PI * 2); ctx!.fill();
        }
      });
    }

    function loop(t: number) {
      const dt = Math.min(50, last ? t - last : 16);
      last = t;
      place(dt);
      step(dt);
      draw();
      frame = requestAnimationFrame(loop);
    }

    const redraw = () => { place(0); draw(); };
    const move = (e: PointerEvent) => { pointer.x = e.clientX; pointer.y = e.clientY; if (still) redraw(); };
    const out = () => { pointer.x = pointer.y = -9999; if (still) redraw(); };
    const visibility = () => {
      cancelAnimationFrame(frame);
      last = 0;
      if (!document.hidden && !still) frame = requestAnimationFrame(loop);
    };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", move);
    document.documentElement.addEventListener("pointerleave", out);
    document.addEventListener("visibilitychange", visibility);
    if (still) redraw();
    else frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", out);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);

  return <canvas ref={canvas} aria-hidden className="pointer-events-none fixed inset-0 -z-10 h-full w-full" />;
}
