---
name: "impactu-mcp-connector"
description: "Crear, desplegar, probar y mantener el conector de ImpactU para Claude: el servidor MCP colav-playground/impactu-mcp (15 herramientas de solo lectura sobre la API de ImpactU) publicado como conector personalizado sin inicio de sesión, que funciona también en cuentas gratis de Claude. Cubre el servidor provisional en Render (https://impactu-mcp.onrender.com/mcp), el despliegue definitivo en mcp.impactu.colav.co, cómo agregarlo en Claude, las pruebas en vivo y los errores conocidos (405 por URL sin /mcp, instancia dormida, ids DOI con barras). Úsala siempre que el usuario quiera conectar ImpactU a Claude, crear o desplegar de nuevo el conector o el servidor MCP de ImpactU, agregar o cambiar una herramienta, actualizarlo cuando cambie la API de ImpactU, comprobar si el servidor funciona, o resolver un error al agregar el conector."
---

# Conector de ImpactU para Claude

El conector es un **servidor MCP remoto** (Model Context Protocol) que traduce las preguntas de Claude en llamadas a la
API pública de ImpactU y devuelve respuestas compactas. Claude lo usa como **conector personalizado**, sin cuenta ni
clave, así que sirve en cualquier plan, **incluido el gratis** (que permite un conector personalizado).

| Qué | Dónde |
| --- | --- |
| Código (público) | <https://github.com/colav-playground/impactu-mcp>, copia local en `~/prog/claude/impactu-mcp` (venv en `.venv`) |
| Servidor provisional | <https://impactu-mcp.onrender.com/mcp> (Render, plan gratis, cuenta del usuario) |
| Servidor definitivo (pendiente, lo hace Colav) | `https://mcp.impactu.colav.co/mcp`, pasos en `DEPLOY.md` del repositorio |
| API que consulta | `https://api.dev.impactu.colav.co` (variable `IMPACTU_API_BASE`) |

```
Claude (nube de Anthropic) ──HTTPS POST /mcp──► servidor impactu-mcp ──► api.dev.impactu.colav.co
```

Claude se conecta **desde la nube de Anthropic**, no desde el computador del usuario: el servidor tiene que ser público,
con HTTPS válido. Por eso **GitHub Pages no sirve** (solo archivos estáticos y GET) y **Hugging Face Spaces** con
Docker ya exige cuenta PRO (respuesta 402).

## Estructura del repositorio

- `src/impactu_mcp/api.py`: cliente HTTP con caché TTL, límite de concurrencia y `ApiError`. `seg(valor, keep_slash)`
  arma segmentos de ruta: **`/work/{id}` necesita las barras del id sin codificar** (`%2F` da 404).
- **Id de un producto:** el primer identificador externo que tenga, en este orden: DOI, OpenAlex, ScienTI
  (`COD_RH-COD_PROD`), Minciencias, handle de DSpace (`uri`), DSpace OAI, ISBN (libros), Google Scholar y, si no hay
  ninguno, el id interno de 24 hex (`mongodb_id`). Reparto en la versión de noviembre de 2026: ScienTI 41,6 %,
  handle 24,7 %, DOI 22,5 %, OpenAlex 5,1 %, DSpace 4,0 %, interno 1,3 %, Minciencias 0,4 %, Scholar 0,3 %,
  ISBN 0,05 %. Algunos ids se comparten (un DOI hasta por 147 productos, handles por 51.422 productos en total).
  Las revistas siguen con ids de 24 hex.
- `src/impactu_mcp/compact.py`: reduce los registros de ImpactU (que pueden pesar MB) a lo útil; elige valores por
  `source`, reconstruye abstracts, cuartil de la revista en el año de publicación, y **quita números de documento**
  (`PRIVATE_ID_SOURCES`).
- `src/impactu_mcp/server.py`: `MCPServer` del SDK `mcp` 2.x (FastMCP cambió de nombre), las 15 herramientas
  (`search_products`, `list_products`, `autocomplete`, `get_product`, `find_product_by_doi`, `get_product_authors`,
  `search_people`, `get_person`, `search_affiliations`, `get_affiliation`, `search_sources`, `get_source`,
  `get_indicator`, `get_filter_options`, `get_database_info`), rutas `/healthz` y `/`, protección DNS-rebinding
  (`MCP_PUBLIC_HOSTS`, más `RENDER_EXTERNAL_HOSTNAME` y `SPACE_HOST` automáticos) y `probe_friendly`, que responde
  HEAD/OPTIONS/DELETE con 200/204 y atiende MCP también en `/`.
- `tests/`: 4 pruebas sin red y 12 en vivo (marcador `live`; cada respuesta < 60 kB).
- Despliegue: `Dockerfile`, `docker-compose.yml`, `render.yaml`, `deploy/nginx`, `deploy/systemd`,
  `deploy/huggingface/push.py`, `DEPLOY.md`.

## Tareas

### Probar un servidor (local o desplegado)

```bash
bash scripts/check.sh https://impactu-mcp.onrender.com/mcp   # desde la carpeta de esta skill
```

Revisa `/healthz`, que ningún método devuelva 405, que no haya metadatos OAuth (404 = sin inicio de sesión) y corre
las 12 pruebas en vivo. La primera llamada puede tardar hasta un minuto si Render está dormido. Para probar el código
local: `cd ~/prog/claude/impactu-mcp && .venv/bin/pytest -m live` (arranca su propio servidor). **Ojo:** si un servidor
viejo sigue escuchando en el puerto de prueba, las pruebas lo usan a él; revisa con `pgrep -af impactu-mcp`.

### Cambiar el código (herramienta nueva, cambio de la API)

1. Editar `server.py` / `compact.py` siguiendo el estilo existente (anotaciones `READ_ONLY`, `Annotated[..., Field(description=...)]`,
   paginación de máximo 25, `trim()` para listas largas).
2. `.venv/bin/pytest -m "not live"` y `.venv/bin/pytest -m live`.
3. Commit con la atribución de la sesión y `git push origin main`.
4. **Render no redespliega solo** (el servicio no está enlazado a GitHub): pedir al usuario
   **Manual Deploy → Deploy latest commit** en el panel de Render, y luego correr `check.sh`.

Sé suave con el servidor de desarrollo de ImpactU: páginas pequeñas, sin barridos masivos.

### Crear de nuevo el servidor provisional en Render

El usuario abre <https://render.com/deploy?repo=https://github.com/colav-playground/impactu-mcp>, entra (con GitHub
sirve, no pide tarjeta) y pulsa **Apply**. `render.yaml` define plan free, Docker, 1 worker (512 MB) y `/healthz`.
La URL queda `https://<nombre del servicio>.onrender.com/mcp`. La cuenta de Render es del usuario: Claude no la crea ni
inicia sesión en ella.

### Despliegue definitivo en mcp.impactu.colav.co

Lo hace alguien de Colav con acceso al servidor y al DNS de `colav.co`, siguiendo `DEPLOY.md` (DNS, Docker o systemd,
nginx + certbot o Caddy, comprobaciones externas). Cuando exista, actualizar las URLs de esta skill y del artefacto.

### Agregar el conector en Claude (explicar al usuario)

**Configuración → Conectores → Agregar conector personalizado**: nombre `ImpactU`, URL
`https://impactu-mcp.onrender.com/mcp`, **sin** OAuth (dejar vacías las opciones avanzadas). En un chat se activa desde
el menú de herramientas. Plan gratis: un conector personalizado. En Team/Enterprise lo agrega un propietario de la
organización. Una sesión ya abierta no ve conectores agregados después: abrir un chat nuevo.

## Errores conocidos

| Síntoma | Causa y solución |
| --- | --- |
| "…set up as not requiring sign-in, but the server asked for sign-in (status 405)" | La URL quedó sin `/mcp`. Desde `1d394e9` el servidor también responde en `/`, pero la URL correcta termina en `/mcp`. |
| Falla la primera pregunta tras una pausa | Render gratis duerme a los 15 min; despierta en ~1 min. Volver a preguntar. |
| `get_product` → "Not found" | Id con `/` codificado (DOI o handle); usar `seg(id, keep_slash=True)`. |
| 421 Misdirected Request | El host no está en `MCP_PUBLIC_HOSTS` (o en las variables automáticas de la plataforma). |
| 402 al crear un Space de Hugging Face | Docker Spaces requieren PRO. |

## Reglas

- Solo lectura; nunca exponer cédulas u otros números de documento.
- No pegar tokens en comandos que queden en registros; si el usuario comparte uno en el chat, recomendar revocarlo.
- Mantener `README.md`, `DEPLOY.md` y esta skill al día cuando cambie una URL o un paso.
