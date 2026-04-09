const STORAGE_KEY = "ultratrader_ui_font_scale_v1";
const MIN_SCALE = 0.85;
const MAX_SCALE = 2.0;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function loadScale() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return 1;
    const n = Number(raw);
    if (!Number.isFinite(n)) return 1;
    return clamp(n, MIN_SCALE, MAX_SCALE);
  } catch {
    return 1;
  }
}

function saveScale(scale) {
  try {
    localStorage.setItem(STORAGE_KEY, String(scale));
  } catch {
    // ignore
  }
}

function applyScaleToApp(scale) {
  const app = document.querySelector(".app");
  if (!app) return;
  app.style.setProperty("--uifs", String(scale));
}

export function initFontScale(ctx, vue) {
  const { ref } = vue;

  const uiFontScale = ref(loadScale());
  applyScaleToApp(uiFontScale.value);

  function setScale(next) {
    const clamped = clamp(Math.round(next * 100) / 100, MIN_SCALE, MAX_SCALE);
    uiFontScale.value = clamped;
    applyScaleToApp(clamped);
    saveScale(clamped);
  }

  function increaseFont() {
    setScale(uiFontScale.value + 0.05);
  }

  function decreaseFont() {
    setScale(uiFontScale.value - 0.05);
  }

  function resetFontScale() {
    setScale(1);
  }

  ctx.uiFontScale = uiFontScale;
  ctx.increaseFont = increaseFont;
  ctx.decreaseFont = decreaseFont;
  ctx.resetFontScale = resetFontScale;
  return ctx;
}
