"""Build the standalone site (GitHub Pages) from the dashboard page and the processed CSVs.

The dashboard page is written for the Claude Dashboard runtime (`dash.*`, theme tokens).
This wraps it with a small shim of that API and the tokens, so the same page runs as a
plain static site that reads ./data/*.csv.

Usage: python3 -I scripts/build_site.py <dashboard/index.html> <data/processed> <docs>
"""
import os
import shutil
import sys

PAGE, DATA, OUT = sys.argv[1:4]
DATASETS = ["serie_mensal", "resumo_12m", "pares_12m", "usinas", "sin_mensal", "sistema_12m", "uf_12m", "mapa_uf.json"]

HEAD = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Curtailment - Projetos Renováveis</title>
<meta name="description" content="Controle mensal de curtailment (constrained-off ONS) dos ativos renováveis com exposição via debêntures.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400&display=swap">
<style>
  :root {
    --color-bg: #f7f8f7; --color-panel: #ffffff; --color-fg: #1d2421; --color-fg-muted: #5f6964;
    --color-border-line: #dfe3e0; --color-ok: #2f7d4f; --color-warn: #a86b00; --color-bad: #b43a2f;
    --cds-chart-grid: #e8ebe9; --cds-chart-muted: #9aa49f; --cds-chart-reference: #7b8580;
    --cds-surface-popover: #ffffff; --cds-border: #d3d8d5; --cds-text-secondary: #5f6964;
    --cds-shadow-popover: 0 4px 16px rgba(20, 30, 25, .12);
    --k1: #2b6cb0; --k2: #d08a2e; --k3: #8a4fb3;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --color-bg: #121614; --color-panel: #1a201d; --color-fg: #e6ebe8; --color-fg-muted: #9aa49f;
      --color-border-line: #2c3430; --color-ok: #6cc28c; --color-warn: #e0a64a; --color-bad: #ee7b6f;
      --cds-chart-grid: #262d29; --cds-chart-muted: #6c7671; --cds-chart-reference: #8d9792;
      --cds-surface-popover: #222925; --cds-border: #353e39; --cds-text-secondary: #9aa49f;
      --cds-shadow-popover: 0 4px 16px rgba(0, 0, 0, .45);
      --k1: #6aa8ec; --k2: #e8a94f; --k3: #b88ae0;
      color-scheme: dark;
    }
  }
  :root {
    --font-anthropic-sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    --font-anthropic-serif: "Source Serif 4", Georgia, "Times New Roman", serif;
    --cds-font-size-caption: 12px; --cds-font-size-body: 14px; --cds-font-size-heading: 16px; --cds-font-size-title: 26px;
    --cds-font-weight-medium: 500;
    --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 16px; --cds-gap-lg: 24px; --cds-gap-xl: 32px;
    --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 20px; --cds-pad-xl: 28px;
    --cds-radius: 8px; --cds-dur-slow: 300ms;
  }
  html, body { margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: var(--font-anthropic-sans); font-size: 14px; }
  #dash-root { max-width: 1280px; margin-inline: auto; padding-block: 28px 40px;
    padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
  .site-foot { margin-top: 32px; color: var(--color-fg-muted); font-size: 12px; line-height: 1.5; }
  .site-foot a { color: inherit; }
  [hidden] { display: none !important; }
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
  // Minimal stand-in for the Claude Dashboard runtime: loads ./data/<id>.csv as rows of text.
  (() => {
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const store = {}, subs = [], JSON_IDS = ['mapa_uf'];
    const run = () => subs.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
    const load = (id) => {
      if (store[id]) return store[id];
      store[id] = { status: 'loading', data: [], columns: [] };
      const json = JSON_IDS.includes(id);
      fetch('data/' + id + (json ? '.json' : '.csv'), { cache: 'no-cache' })
        .then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then((t) => { const rows = json ? JSON.parse(t) : d3.csvParse(t); store[id] = { status: 'ok', data: rows, columns: rows.columns || Object.keys(rows[0] || {}) }; run(); })
        .catch((e) => { store[id] = { status: 'error', data: [], columns: [], message: String(e) }; run(); });
      return store[id];
    };
    window.dash = {
      get colors() { return [css('--k1'), css('--k2'), css('--k3')]; },
      data: (id) => load(id),
      onData: (fn) => { subs.push(fn); fn(); },
      setLink: (name) => { try { history.replaceState(null, '', '#' + name); } catch (e) {} },
      params: () => ({}), setParams: () => {}, resetParams: () => {}, refresh: () => {},
    };
    let w = 0;
    window.addEventListener('resize', () => { if (Math.abs(innerWidth - w) > 4) { w = innerWidth; run(); } });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', run);
  })();
</script>
</head>
<body>
<div id="dash-root">
"""

FOOT = """
<footer class="site-foot">
  Fonte: ONS Dados Abertos — Restrição de Operação por Constrained-off de Usinas Eólicas e Fotovoltaicas
  (por conjunto e detalhamento por usina). Cálculos e método no
  <a href="https://github.com/Rafaelcreditovinland/Controle-curtailment">repositório</a>.
</footer>
</div>
</body>
</html>
"""

page = open(PAGE, encoding="utf-8").read()
os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(HEAD + page + FOOT)
for d in DATASETS:
    name = d if d.endswith(".json") else d + ".csv"
    shutil.copy(os.path.join(DATA, name), os.path.join(OUT, "data", name))
open(os.path.join(OUT, ".nojekyll"), "w").close()
print("site:", os.path.join(OUT, "index.html"), "+", len(DATASETS), "csv")
