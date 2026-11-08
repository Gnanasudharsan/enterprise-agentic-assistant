// All page behaviour in one small module. Everything degrades to a fully readable,
// static page without JavaScript, and motion is skipped when the reader asks for less.

const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $$ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) =>
  Array.from(root.querySelectorAll<T>(sel) as unknown as T[]);

document.documentElement.classList.add("smooth");

// ---------- Reveal on scroll ----------
const revealer = new IntersectionObserver(
  (entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add("in");
      revealer.unobserve(e.target);
      const el = e.target as HTMLElement;
      if (el.matches("[data-chart]")) countUp(el);
      $$("[data-count]", el).forEach((n) => countUpOne(n));
    }
  },
  { rootMargin: "0px 0px -10% 0px", threshold: 0.12 },
);
$$(".reveal, [data-words], [data-chart]").forEach((el) => revealer.observe(el));

// ---------- Count-up numbers ----------
function countUpOne(el: HTMLElement) {
  if (el.dataset.done) return;
  el.dataset.done = "1";
  const target = Number(el.dataset.count);
  const decimals = Number(el.dataset.decimals ?? 0);
  if (reduce || !Number.isFinite(target)) return;
  const start = performance.now();
  const dur = 1400;
  const tick = (now: number) => {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 4);
    el.textContent = (target * eased).toFixed(decimals);
    if (t < 1) requestAnimationFrame(tick);
    else el.textContent = target.toFixed(decimals);
  };
  requestAnimationFrame(tick);
}
function countUp(root: HTMLElement) {
  $$("[data-count]", root).forEach(countUpOne);
}

// ---------- Nav: frosted state, progress, active section ----------
const nav = document.querySelector<HTMLElement>("[data-nav]");
const progress = document.querySelector<HTMLElement>("[data-progress]");
const navLinks = $$<HTMLAnchorElement>("[data-navlink]");
const sections = navLinks
  .map((a) => document.querySelector<HTMLElement>(a.getAttribute("href")!))
  .filter(Boolean) as HTMLElement[];

const line = document.querySelector<HTMLElement>("[data-line]");
const lineFill = document.querySelector<HTMLElement>("[data-linefill]");

let ticking = false;
function onScroll() {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => {
    ticking = false;
    const y = window.scrollY;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    nav?.classList.toggle("scrolled", y > 24);
    progress?.style.setProperty("--p", String(max > 0 ? y / max : 0));

    let current = "";
    for (const s of sections) if (s.getBoundingClientRect().top < window.innerHeight * 0.4) current = s.id;
    for (const a of navLinks) a.classList.toggle("active", a.getAttribute("href") === `#${current}`);

    if (line && lineFill) {
      const r = line.getBoundingClientRect();
      const f = Math.min(1, Math.max(0, (window.innerHeight * 0.6 - r.top) / r.height));
      lineFill.style.setProperty("--fill", String(f));
    }
  });
}
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

// ---------- Walkthrough: the step nearest the middle drives the window ----------
const walk = document.querySelector<HTMLElement>("[data-walk]");
if (walk) {
  const steps = $$("[data-step]", walk);
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const i = (e.target as HTMLElement).dataset.step!;
        walk.dataset.active = i;
        steps.forEach((s) => s.classList.toggle("on", s.dataset.step === i));
      }
    },
    // On small screens the sticky window covers the middle, so read the area below it.
    { rootMargin: window.matchMedia("(max-width: 960px)").matches ? "-68% 0px -22% 0px" : "-45% 0px -45% 0px" },
  );
  steps.forEach((s) => io.observe(s));
  steps[0]?.classList.add("on");
}

// ---------- Pointer spotlight on cards ----------
for (const card of $$(".spot")) {
  card.addEventListener("pointermove", (ev) => {
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${ev.clientX - r.left}px`);
    card.style.setProperty("--my", `${ev.clientY - r.top}px`);
  });
}

// ---------- Chart tooltips (hover and keyboard-free touch tap) ----------
const tip = document.querySelector<HTMLElement>("[data-tip-el]");
if (tip) {
  for (const mark of $$<SVGGElement>("[data-tip]")) {
    const show = (ev: PointerEvent) => {
      tip.textContent = mark.dataset.tip ?? "";
      tip.style.left = `${ev.clientX}px`;
      tip.style.top = `${ev.clientY}px`;
      tip.classList.add("on");
    };
    mark.addEventListener("pointerenter", show);
    mark.addEventListener("pointermove", show);
    mark.addEventListener("pointerleave", () => tip.classList.remove("on"));
  }
  window.addEventListener("scroll", () => tip.classList.remove("on"), { passive: true });
}

// ---------- Demo video plays only while visible ----------
const video = document.querySelector<HTMLVideoElement>("[data-video]");
if (video) {
  const vio = new IntersectionObserver(
    ([e]) => {
      if (e.isIntersecting) {
        if (video.preload === "none") video.preload = "auto";
        if (!reduce) video.play().catch(() => {});
      } else video.pause();
    },
    { threshold: 0.35 },
  );
  vio.observe(video);
  if (reduce) video.controls = true;
}

// ---------- Eclipse parallax ----------
const eclipse = document.querySelector<HTMLElement>("[data-eclipse]");
if (eclipse && !reduce && window.matchMedia("(pointer: fine)").matches) {
  window.addEventListener("pointermove", (ev) => {
    const dx = (ev.clientX / window.innerWidth - 0.5) * 24;
    const dy = (ev.clientY / window.innerHeight - 0.5) * 16;
    eclipse.style.setProperty("--px", `${dx}px`);
    eclipse.style.setProperty("--py", `${dy}px`);
  });
}

// ---------- Starfield ----------
const canvas = document.querySelector<HTMLCanvasElement>("[data-stars]");
if (canvas) {
  const ctx = canvas.getContext("2d")!;
  let stars: { x: number; y: number; r: number; a: number; s: number }[] = [];
  let w = 0, h = 0, dpr = 1, raf = 0, visible = true;
  const resize = () => {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round((w * h) / 5200);
    stars = Array.from({ length: n }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.1 + 0.2,
      a: Math.random() * 0.6 + 0.15,
      s: Math.random() * 0.012 + 0.002,
    }));
  };
  const draw = (t: number) => {
    ctx.clearRect(0, 0, w, h);
    for (const st of stars) {
      const a = reduce ? st.a : st.a * (0.6 + 0.4 * Math.sin(t * st.s + st.x));
      ctx.globalAlpha = a;
      ctx.fillStyle = "#fff4e6";
      ctx.beginPath();
      const drift = reduce ? 0 : t * 0.004; // slow upward drift, wrapping at the top
      ctx.arc(st.x, (((st.y - drift) % h) + h) % h, st.r, 0, Math.PI * 2);
      ctx.fill();
    }
    if (!reduce && visible) raf = requestAnimationFrame(draw);
  };
  resize();
  window.addEventListener("resize", resize);
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    cancelAnimationFrame(raf);
    if (visible) raf = requestAnimationFrame(draw);
  }).observe(canvas);
  raf = requestAnimationFrame(draw);
}
