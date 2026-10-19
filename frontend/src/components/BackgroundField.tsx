import { useEffect, useRef } from "react";

const COLS = 72;     // dots across
const ROWS = 34;     // dots into the depth
const FOCAL = 520;   // perspective strength

/** Animated background: a plane of dots in perspective, moving like a slow wave. Around the pointer the dots rise
 *  and light up red, and the whole field shifts a little with the pointer for depth. Sits behind the whole UI and
 *  never catches clicks. Pauses in a hidden tab; with reduced motion it draws one still frame. */
export function BackgroundField() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dark = window.matchMedia("(prefers-color-scheme: dark)");
    let width = 0, height = 0, frame = 0;
    const pointer = { x: -9999, y: -9999, px: 0, py: 0 };   // px, py: smoothed parallax in -0.5 … 0.5

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      el!.width = width * ratio;
      el!.height = height * ratio;
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function draw(t: number) {
      const isDark = document.documentElement.classList.contains("dark") || dark.matches;
      const base = isDark ? "185, 205, 235" : "20, 40, 80";     // navy dots, light ones in dark mode
      ctx!.clearRect(0, 0, width, height);
      pointer.px += ((pointer.x / width - 0.5) - pointer.px) * 0.04;
      pointer.py += ((pointer.y / height - 0.5) - pointer.py) * 0.04;
      const horizon = height * (0.42 + pointer.py * 0.05);
      const camX = pointer.px * 160;
      const spread = width * 1.6;

      for (let r = 0; r < ROWS; r++) {
        const z = 60 + r * 22;                                   // depth of this row
        const scale = FOCAL / z;
        const fade = 1 - r / ROWS;
        for (let c = 0; c < COLS; c++) {
          const x = (c / (COLS - 1) - 0.5) * spread;
          const wave = Math.sin(x * 0.006 + t * 0.0006) * 14 + Math.cos(z * 0.03 + t * 0.0008) * 10;
          let sx = width / 2 + (x - camX) * scale * 0.5;
          let sy = horizon + (90 - wave) * scale;
          if (sx < -20 || sx > width + 20 || sy > height + 20) continue;
          // lift and colour the dots near the pointer
          const d = Math.hypot(sx - pointer.x, sy - pointer.y);
          const near = Math.max(0, 1 - d / 190);
          sy -= near * near * 26;
          sx += (sx - pointer.x) * near * 0.06;
          const size = Math.max(0.6, scale * 0.9) * (1 + near * 1.2);
          const alpha = (isDark ? 0.22 : 0.16) * fade + near * 0.55;
          ctx!.fillStyle = near > 0.05 ? `rgba(229, 9, 20, ${alpha})` : `rgba(${base}, ${alpha})`;
          ctx!.beginPath();
          ctx!.arc(sx, sy, size, 0, Math.PI * 2);
          ctx!.fill();
        }
      }
    }

    function loop(t: number) {
      draw(t);
      frame = requestAnimationFrame(loop);
    }

    const move = (e: PointerEvent) => { pointer.x = e.clientX; pointer.y = e.clientY; if (still) draw(0); };
    const out = () => { pointer.x = pointer.y = -9999; };
    const visibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden && !still) frame = requestAnimationFrame(loop);
    };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", move);
    document.addEventListener("pointerleave", out);
    document.addEventListener("visibilitychange", visibility);
    if (still) draw(0);
    else frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", out);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);

  return <canvas ref={canvas} aria-hidden className="pointer-events-none fixed inset-0 -z-10 h-full w-full" />;
}
