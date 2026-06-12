---
name: project-bancada-phoenix
description: Contexto técnico do projeto BANCADA PHOENIX — dashboard de trading crypto
metadata:
  type: project
---

Stack: Flask (Python) + templates Jinja2 + HTML/CSS/JS puro.

Arquivos principais de UI:
- `templates/index.html` — frontend da web app Flask (SPA com fetch/JS)
- `engine.py` — motor de análise Python; gera HTML via f-strings (constante CSS + funções html_*)
- `app.py` — servidor Flask com endpoints REST (/api/import, /api/live, /api/snapshots, etc.)

**Why:** O engine.py gera HTML inline para ser injetado via innerHTML no frontend, então CSS e cores inline do engine devem estar sincronizados com o bloco style do index.html.

**How to apply:** Qualquer mudança visual deve ser feita nos dois arquivos em paralelo. Não alterar lógica Python, apenas HTML/CSS gerados pelas funções html_*.
