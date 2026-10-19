import { useEffect, useRef } from "react";

type Node = { x: number; y: number; vx: number; vy: number; r: number; links: number };
type Link = { a: number; b: number; age: number; life: number };

const AREA_PER_NODE = 22000;   // px² per node: the density
const REACH = 240;             // only nodes this close can link
const MAX_LINKS = 3;           // per node at the same time
const FADE = 700;              // ms to fade a link in and out

/** Animated background: nodes drifting slowly; now and then two of them link up for a few seconds, then the link
 *  fades out again. Behind the whole UI, never catches clicks; pauses in a hidden tab and stands still with
 *  reduced motion. */
export function BackgroundField() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const darkScheme = window.matchMedia("(prefers-color-scheme: dark)");
    let width = 0, height = 0, frame = 0, last = 0;
    let nodes: Node[] = [], links: Link[] = [];

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      el!.width = width * ratio;
      el!.height = height * ratio;
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);
      nodes = Array.from({ length: Math.round((width * height) / AREA_PER_NODE) }, () => ({
        x: Math.random() * width, y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.03, vy: (Math.random() - 0.5) * 0.03,
        r: 1.6 + Math.random() * 1.8, links: 0,
      }));
      links = [];
    }

    function step(dt: number) {
      for (const n of nodes) {
        n.x += n.vx * dt; n.y += n.vy * dt;
        if (n.x < 0 || n.x > width) n.vx *= -1;
        if (n.y < 0 || n.y > height) n.vy *= -1;
      }
      // links age; they end after their life, or when the nodes drift apart
      links = links.filter((l) => {
        l.age += dt;
        const gone = l.age > l.life + FADE ||
          Math.hypot(nodes[l.a].x - nodes[l.b].x, nodes[l.a].y - nodes[l.b].y) > REACH * 1.3;
        if (gone) { nodes[l.a].links--; nodes[l.b].links--; }
        return !gone;
      });
      // new links between random nearby nodes, about one per node on average
      for (let tries = 0; tries < 4 && links.length < nodes.length; tries++) {
        const a = Math.floor(Math.random() * nodes.length), b = Math.floor(Math.random() * nodes.length);
        if (a === b || nodes[a].links >= MAX_LINKS || nodes[b].links >= MAX_LINKS) continue;
        if (Math.hypot(nodes[a].x - nodes[b].x, nodes[a].y - nodes[b].y) > REACH) continue;
        if (links.some((l) => (l.a === a && l.b === b) || (l.a === b && l.b === a))) continue;
        links.push({ a, b, age: 0, life: 2500 + Math.random() * 4500 });
        nodes[a].links++; nodes[b].links++;
      }
    }

    function draw() {
      const dark = document.documentElement.classList.contains("dark") || darkScheme.matches;
      const ink = dark ? "170, 195, 232" : "22, 44, 86";
      ctx!.clearRect(0, 0, width, height);
      ctx!.lineWidth = 1;
      for (const l of links) {
        const fadeIn = Math.min(1, l.age / FADE), fadeOut = Math.min(1, Math.max(0, (l.life + FADE - l.age) / FADE));
        ctx!.strokeStyle = `rgba(${ink}, ${(dark ? 0.3 : 0.2) * fadeIn * fadeOut})`;
        ctx!.beginPath(); ctx!.moveTo(nodes[l.a].x, nodes[l.a].y); ctx!.lineTo(nodes[l.b].x, nodes[l.b].y); ctx!.stroke();
      }
      ctx!.fillStyle = `rgba(${ink}, ${dark ? 0.5 : 0.35})`;
      for (const n of nodes) {
        ctx!.beginPath(); ctx!.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx!.fill();
      }
    }

    function loop(t: number) {
      const dt = Math.min(50, last ? t - last : 16);
      last = t;
      step(dt);
      draw();
      frame = requestAnimationFrame(loop);
    }

    const visibility = () => {
      cancelAnimationFrame(frame);
      last = 0;
      if (!document.hidden && !still) frame = requestAnimationFrame(loop);
    };

    resize();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", visibility);
    if (still) { for (let i = 0; i < 60; i++) step(16); draw(); }
    else frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);

  return <canvas ref={canvas} aria-hidden className="pointer-events-none fixed inset-0 -z-10 h-full w-full" />;
}
