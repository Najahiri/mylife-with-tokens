import { useEffect, useRef } from "react";

type Node = { x: number; y: number; vx: number; vy: number; z: number; hub: boolean };
type Pulse = { a: number; b: number; t: number };

const AREA_PER_NODE = 15000;   // px² per node: the density
const LINK = 150;              // nodes closer than this (scaled by depth) are linked
const POINTER_LINK = 190;      // reach of the pointer
const PULSE_EVERY = 520;       // ms between new signals
const PULSE_TIME = 1300;       // ms a signal needs along its edge

/** Animated background: a graph of nodes drifting at different depths, linked when they come close, with signals
 *  travelling along the links. The pointer acts as a node itself: nearby nodes link to it in red and lean towards
 *  it, and the depths shift with it for a 3D feel. Behind the whole UI, never catches clicks; pauses in a hidden
 *  tab and stands still with reduced motion. */
export function BackgroundField() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const darkScheme = window.matchMedia("(prefers-color-scheme: dark)");
    let width = 0, height = 0, frame = 0, last = 0, sincePulse = 0;
    let nodes: Node[] = [];
    let pulses: Pulse[] = [];
    const pointer = { x: -9999, y: -9999, px: 0, py: 0 };

    function seed() {
      const count = Math.round((width * height) / AREA_PER_NODE);
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width, y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.12, vy: (Math.random() - 0.5) * 0.12,
        z: 0.35 + Math.random() * 0.65, hub: Math.random() < 0.08,
      }));
      pulses = [];
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

    // where a node is drawn: its position shifted with the pointer, the nearer the more
    const at = (n: Node) => ({ x: n.x - pointer.px * 40 * n.z, y: n.y - pointer.py * 40 * n.z });

    function step(dt: number) {
      pointer.px += ((pointer.x < 0 ? 0 : pointer.x / width - 0.5) - pointer.px) * 0.05;
      pointer.py += ((pointer.y < 0 ? 0 : pointer.y / height - 0.5) - pointer.py) * 0.05;
      for (const n of nodes) {
        const p = at(n);
        const d = Math.hypot(p.x - pointer.x, p.y - pointer.y);
        if (d < POINTER_LINK && d > 1) {                    // lean towards the pointer
          n.vx += ((pointer.x - p.x) / d) * 0.0025 * dt * 0.06;
          n.vy += ((pointer.y - p.y) / d) * 0.0025 * dt * 0.06;
        }
        n.vx *= 0.995; n.vy *= 0.995;
        const speed = Math.hypot(n.vx, n.vy);
        if (speed < 0.04) { n.vx += (Math.random() - 0.5) * 0.01; n.vy += (Math.random() - 0.5) * 0.01; }
        n.x += n.vx * dt * 0.06 * (0.5 + n.z);
        n.y += n.vy * dt * 0.06 * (0.5 + n.z);
        if (n.x < -40) n.x = width + 40; else if (n.x > width + 40) n.x = -40;
        if (n.y < -40) n.y = height + 40; else if (n.y > height + 40) n.y = -40;
      }
      sincePulse += dt;
      if (sincePulse > PULSE_EVERY && nodes.length > 1) {
        sincePulse = 0;
        const a = Math.floor(Math.random() * nodes.length);
        let best = -1, bestD = Infinity;
        for (let i = 0; i < nodes.length; i++) {          // the nearest linked neighbour
          if (i === a) continue;
          const d = Math.hypot(nodes[i].x - nodes[a].x, nodes[i].y - nodes[a].y);
          if (d < bestD && d < LINK * Math.min(nodes[i].z, nodes[a].z) * 1.4) { best = i; bestD = d; }
        }
        if (best >= 0) pulses.push({ a, b: best, t: 0 });
      }
      pulses = pulses.filter((p) => (p.t += dt / PULSE_TIME) < 1);
    }

    function draw() {
      const dark = document.documentElement.classList.contains("dark") || darkScheme.matches;
      const ink = dark ? "175, 198, 232" : "20, 42, 84";
      const red = "229, 9, 20";
      ctx!.clearRect(0, 0, width, height);
      const pos = nodes.map(at);

      ctx!.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const reach = LINK * Math.min(nodes[i].z, nodes[j].z) * 1.4;
          const d = Math.hypot(pos[i].x - pos[j].x, pos[i].y - pos[j].y);
          if (d > reach) continue;
          const alpha = (1 - d / reach) * (dark ? 0.32 : 0.22) * Math.min(nodes[i].z, nodes[j].z);
          ctx!.strokeStyle = `rgba(${ink}, ${alpha})`;
          ctx!.beginPath(); ctx!.moveTo(pos[i].x, pos[i].y); ctx!.lineTo(pos[j].x, pos[j].y); ctx!.stroke();
        }
      }
      for (let i = 0; i < nodes.length; i++) {               // links to the pointer
        const d = Math.hypot(pos[i].x - pointer.x, pos[i].y - pointer.y);
        if (d > POINTER_LINK) continue;
        ctx!.strokeStyle = `rgba(${red}, ${(1 - d / POINTER_LINK) * 0.45 * nodes[i].z})`;
        ctx!.beginPath(); ctx!.moveTo(pos[i].x, pos[i].y); ctx!.lineTo(pointer.x, pointer.y); ctx!.stroke();
      }
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const near = Math.max(0, 1 - Math.hypot(pos[i].x - pointer.x, pos[i].y - pointer.y) / POINTER_LINK);
        const r = (n.hub ? 3.4 : 1.8) * (0.6 + n.z * 0.7) * (1 + near * 0.5);
        ctx!.fillStyle = near > 0.05 ? `rgba(${red}, ${0.35 + near * 0.5})` : `rgba(${ink}, ${(dark ? 0.55 : 0.4) * n.z})`;
        ctx!.beginPath(); ctx!.arc(pos[i].x, pos[i].y, r, 0, Math.PI * 2); ctx!.fill();
      }
      for (const p of pulses) {                              // signals travelling along the links
        const a = pos[p.a], b = pos[p.b];
        if (!a || !b) continue;
        const x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t;
        const fade = Math.sin(p.t * Math.PI);
        ctx!.fillStyle = `rgba(${red}, ${0.18 * fade})`;
        ctx!.beginPath(); ctx!.arc(x, y, 7, 0, Math.PI * 2); ctx!.fill();
        ctx!.fillStyle = `rgba(${red}, ${0.85 * fade})`;
        ctx!.beginPath(); ctx!.arc(x, y, 2.2, 0, Math.PI * 2); ctx!.fill();
      }
      if (pointer.x > 0) {
        ctx!.fillStyle = `rgba(${red}, 0.5)`;
        ctx!.beginPath(); ctx!.arc(pointer.x, pointer.y, 2.6, 0, Math.PI * 2); ctx!.fill();
      }
    }

    function loop(t: number) {
      const dt = Math.min(50, last ? t - last : 16);
      last = t;
      step(dt);
      draw();
      frame = requestAnimationFrame(loop);
    }

    const move = (e: PointerEvent) => { pointer.x = e.clientX; pointer.y = e.clientY; if (still) draw(); };
    const out = () => { pointer.x = pointer.y = -9999; if (still) draw(); };
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
    if (still) draw();
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
