import { useEffect, useRef } from "react";

type P3 = { x: number; y: number; z: number };
type Pulse = { edge: number; forward: boolean; t: number };

const NODES = 160;          // points on the globe
const LINKS = 3;            // each node to its nearest neighbours
const SPIN = 0.00009;       // radians per ms (about one turn a minute)
const PULSE_EVERY = 420;    // ms between new signals
const PULSE_TIME = 1400;    // ms a signal needs along its edge

/** Animated background: a slowly turning globe of nodes, each linked to its nearest neighbours, with signals
 *  travelling along the links. Front nodes are larger and stronger than those behind; the pointer tilts and turns
 *  the globe a little and lights up the node under it with its links. Behind the whole UI, never catches clicks;
 *  pauses in a hidden tab and stands still with reduced motion. */
export function BackgroundField() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const darkScheme = window.matchMedia("(prefers-color-scheme: dark)");
    let width = 0, height = 0, frame = 0, last = 0, spin = 0, sincePulse = 0;
    let pulses: Pulse[] = [];
    const pointer = { x: -9999, y: -9999, px: 0, py: 0 };

    // points evenly on the unit sphere (Fibonacci sphere), and fixed links to the nearest neighbours
    const points: P3[] = Array.from({ length: NODES }, (_, i) => {
      const y = 1 - (i / (NODES - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const a = i * Math.PI * (3 - Math.sqrt(5));
      return { x: Math.cos(a) * r, y, z: Math.sin(a) * r };
    });
    const accent = points.map(() => Math.random() < 0.1);
    const edges: [number, number][] = [];
    const neighbours: number[][] = points.map(() => []);
    points.forEach((p, i) => {
      points.map((q, j) => ({ j, d: (p.x - q.x) ** 2 + (p.y - q.y) ** 2 + (p.z - q.z) ** 2 }))
        .filter((o) => o.j !== i).sort((a, b) => a.d - b.d).slice(0, LINKS)
        .forEach(({ j }) => {
          if (edges.some(([a, b]) => (a === i && b === j) || (a === j && b === i))) return;
          neighbours[i].push(edges.length); neighbours[j].push(edges.length);
          edges.push([i, j]);
        });
    });

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      el!.width = width * ratio;
      el!.height = height * ratio;
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    // rotate around y (spin + pointer), then tilt around x (pointer), then project with a little perspective
    function project() {
      pointer.px += ((pointer.x < 0 ? 0 : pointer.x / width - 0.5) - pointer.px) * 0.04;
      pointer.py += ((pointer.y < 0 ? 0 : pointer.y / height - 0.5) - pointer.py) * 0.04;
      const ay = spin + pointer.px * 0.9, ax = 0.32 + pointer.py * 0.6;
      const [sy, cy, sx, cx] = [Math.sin(ay), Math.cos(ay), Math.sin(ax), Math.cos(ax)];
      const radius = Math.min(width, height) * 0.42;
      const ox = width / 2, oy = height * 0.55;
      return points.map((p) => {
        const x1 = p.x * cy + p.z * sy, z1 = -p.x * sy + p.z * cy;
        const y2 = p.y * cx - z1 * sx, z2 = p.y * sx + z1 * cx;
        const persp = 1 / (1 - z2 * 0.3);
        return { x: ox + x1 * radius * persp, y: oy + y2 * radius * persp, z: z2 };   // z: -1 back … 1 front
      });
    }

    function draw(dt: number) {
      const dark = document.documentElement.classList.contains("dark") || darkScheme.matches;
      const ink = dark ? "170, 195, 232" : "22, 44, 86";
      const red = "229, 9, 20";
      const strength = dark ? 1.25 : 1;
      const pos = project();
      const depth = (z: number) => 0.18 + 0.82 * ((z + 1) / 2);              // 0.18 behind … 1 in front
      ctx!.clearRect(0, 0, width, height);

      // the front node under the pointer lights up with its links and neighbours
      let focus = -1, focusD = 34;
      pos.forEach((p, i) => {
        const d = Math.hypot(p.x - pointer.x, p.y - pointer.y);
        if (p.z > 0 && d < focusD) { focus = i; focusD = d; }
      });
      const lit = new Set(focus >= 0 ? neighbours[focus] : []);
      const litNodes = new Set<number>(focus >= 0 ? [focus] : []);
      lit.forEach((e) => { litNodes.add(edges[e][0]); litNodes.add(edges[e][1]); });

      // back to front, so the near side covers the far side
      const order = edges.map((_, i) => i).sort((a, b) =>
        (pos[edges[a][0]].z + pos[edges[a][1]].z) - (pos[edges[b][0]].z + pos[edges[b][1]].z));
      for (const i of order) {
        const [a, b] = edges[i];
        const d = depth((pos[a].z + pos[b].z) / 2);
        ctx!.strokeStyle = lit.has(i) ? `rgba(${red}, 0.75)` : `rgba(${ink}, ${0.2 * d * d * strength})`;
        ctx!.lineWidth = lit.has(i) ? 1.6 : 0.5 + d * 0.7;
        ctx!.beginPath(); ctx!.moveTo(pos[a].x, pos[a].y); ctx!.lineTo(pos[b].x, pos[b].y); ctx!.stroke();
      }

      sincePulse += dt;
      if (dt && sincePulse > PULSE_EVERY) {
        sincePulse = 0;
        pulses.push({ edge: Math.floor(Math.random() * edges.length), forward: Math.random() < 0.5, t: 0 });
      }
      pulses = pulses.filter((p) => (p.t += dt / PULSE_TIME) < 1);
      for (const p of pulses) {
        const [i, j] = edges[p.edge];
        const a = pos[p.forward ? i : j], b = pos[p.forward ? j : i];
        const x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t;
        const d = depth(a.z + (b.z - a.z) * p.t), fade = Math.sin(p.t * Math.PI) * d;
        ctx!.fillStyle = `rgba(${red}, ${0.18 * fade})`;
        ctx!.beginPath(); ctx!.arc(x, y, 7 * d, 0, Math.PI * 2); ctx!.fill();
        ctx!.fillStyle = `rgba(${red}, ${0.9 * fade})`;
        ctx!.beginPath(); ctx!.arc(x, y, 2.2 * d, 0, Math.PI * 2); ctx!.fill();
      }

      const nodeOrder = pos.map((_, i) => i).sort((a, b) => pos[a].z - pos[b].z);
      for (const i of nodeOrder) {
        const d = depth(pos[i].z);
        const on = litNodes.has(i);
        const colour = on || accent[i] ? red : ink;
        const alpha = on ? 0.95 : (accent[i] ? 0.6 : 0.5) * d * strength;
        const r = (accent[i] ? 2.6 : 1.9) * (0.45 + d * 0.9) * (i === focus ? 1.6 : 1);
        if (on || accent[i]) {
          ctx!.fillStyle = `rgba(${colour}, ${alpha * 0.18})`;
          ctx!.beginPath(); ctx!.arc(pos[i].x, pos[i].y, r * 3, 0, Math.PI * 2); ctx!.fill();
        }
        ctx!.fillStyle = `rgba(${colour}, ${alpha})`;
        ctx!.beginPath(); ctx!.arc(pos[i].x, pos[i].y, r, 0, Math.PI * 2); ctx!.fill();
      }
    }

    function loop(t: number) {
      const dt = Math.min(50, last ? t - last : 16);
      last = t;
      spin += dt * SPIN;
      draw(dt);
      frame = requestAnimationFrame(loop);
    }

    const move = (e: PointerEvent) => { pointer.x = e.clientX; pointer.y = e.clientY; if (still) draw(0); };
    const out = () => { pointer.x = pointer.y = -9999; if (still) draw(0); };
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
    if (still) draw(0);
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
