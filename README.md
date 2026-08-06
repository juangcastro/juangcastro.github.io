# Hermes Files — Organización

Carpeta de salida de Hermes (reportes, páginas, documentos) y repositorio de
GitHub Pages para **theredqueen.co**.

## Estructura

```
Hermes Files/
├── CNAME              # Dominio custom (requerido por GitHub Pages — NO mover)
├── dashboard.html     # Odyssey Dashboard (página pública: /dashboard.html)
├── trq-program.html   # Propuesta de mentorías The Red Queen (/trq-program.html)
├── assets/            # Assets del sitio web (favicon, logo)
├── Neuromancer/       # Informes del consejo de inversión Neuromancer (12)
├── PDFs/              # Documentos PDF (libros, protocolos, planes)
├── Trading/           # Backtests y análisis de trading
└── Contenido/         # Contenido editorial (LinkedIn: parrilla, audit)
```

## Reglas

- **Raíz = sitio web publicado.** `CNAME`, `dashboard.html` y `trq-program.html`
  deben permanecer en la raíz: GitHub Pages los sirve desde ahí y moverlos rompe
  las URLs públicas (https://theredqueen.co/...).
- Los assets del sitio viven en `assets/` y se referencian como `assets/...`.
- Los informes y documentos por proyecto en sus carpetas (`Neuromancer/`,
  `PDFs/`, `Trading/`, `Contenido/`).
- `.DS_Store` no se versiona.
