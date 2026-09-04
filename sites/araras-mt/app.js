(() => {
  const root = document.documentElement;
  const body = document.body;
  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());

  /** Base do painel Streamlit (piloto SES). Override: data-panel-base no <html> ou ?painel= */
  const PANEL_BASE =
    root.dataset.panelBase ||
    new URLSearchParams(location.search).get("painel") ||
    "http://10.15.0.131:8501/";

  const panelUrl = (modulo) => {
    const base = PANEL_BASE.endsWith("/") ? PANEL_BASE : `${PANEL_BASE}/`;
    if (!modulo) return base;
    const url = new URL(base);
    url.searchParams.set("aba", modulo);
    return url.toString();
  };

  document.querySelectorAll("[data-panel-modulo]").forEach((el) => {
    const modulo = el.getAttribute("data-panel-modulo") || "";
    if (el instanceof HTMLAnchorElement) {
      el.href = panelUrl(modulo);
    }
  });

  const SCALE_KEY = "araras-font-scale";
  const CONTRAST_KEY = "araras-high-contrast";
  let scale = Number(localStorage.getItem(SCALE_KEY) || "100");
  if (!Number.isFinite(scale)) scale = 100;
  scale = Math.min(130, Math.max(90, scale));

  const applyScale = () => {
    root.style.setProperty("--font-scale", `${scale}%`);
    localStorage.setItem(SCALE_KEY, String(scale));
    const decrease = document.getElementById("font-decrease");
    const increase = document.getElementById("font-increase");
    if (decrease) decrease.disabled = scale <= 90;
    if (increase) increase.disabled = scale >= 130;
  };

  const applyContrast = (on) => {
    body.classList.toggle("high-contrast", on);
    const btn = document.getElementById("contrast-toggle");
    if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
    localStorage.setItem(CONTRAST_KEY, on ? "1" : "0");
  };

  document.getElementById("font-decrease")?.addEventListener("click", () => {
    scale = Math.max(90, scale - 10);
    applyScale();
  });
  document.getElementById("font-increase")?.addEventListener("click", () => {
    scale = Math.min(130, scale + 10);
    applyScale();
  });
  document.getElementById("contrast-toggle")?.addEventListener("click", () => {
    applyContrast(!body.classList.contains("high-contrast"));
  });

  applyScale();
  applyContrast(localStorage.getItem(CONTRAST_KEY) === "1");

  document.querySelectorAll(".mobile-menu a").forEach((link) => {
    link.addEventListener("click", () => {
      const menu = document.querySelector(".mobile-menu");
      if (menu instanceof HTMLDetailsElement) menu.open = false;
    });
  });
})();
