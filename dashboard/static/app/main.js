import { mountDashboard } from "./mountDashboard.js";

async function loadTemplateParts() {
  const parts = [
    "/static/templates/app-dom.part1.html",
    "/static/templates/app-dom.part2.html",
    "/static/templates/app-dom.part3.html",
  ];

  const results = await Promise.all(
    parts.map(async (url) => {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`載入模板失敗: ${url} (${res.status})`);
      }
      return await res.text();
    }),
  );

  return results.join("\n");
}

async function bootstrap() {
  const placeholder = document.getElementById("app");
  if (!placeholder) return;

  const html = await loadTemplateParts();
  placeholder.outerHTML = html;

  mountDashboard();
}

bootstrap().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("[dashboard bootstrap]", err);
});

