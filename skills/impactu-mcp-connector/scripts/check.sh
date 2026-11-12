#!/usr/bin/env bash
# Comprueba un servidor del conector de ImpactU: salud, métodos sin 405, sin OAuth, y las 12 pruebas en vivo.
#   bash check.sh [URL que termina en /mcp]   (por defecto el servidor provisional de Render)
set -u
URL=${1:-https://impactu-mcp.onrender.com/mcp}
BASE=${URL%/mcp}
REPO=${IMPACTU_MCP_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}  # the repository this skill lives in

echo "== $URL"
echo -n "healthz: "; curl -s -m 90 "$BASE/healthz"; echo
init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}'
for p in "$BASE/" "$URL"; do
  post=$(curl -s -m 30 -o /dev/null -w "%{http_code}" -X POST "$p" -H 'Content-Type: application/json' \
         -H 'Accept: application/json, text/event-stream' -d "$init")
  head=$(curl -s -m 30 -I -o /dev/null -w "%{http_code}" "$p")
  opts=$(curl -s -m 30 -o /dev/null -w "%{http_code}" -X OPTIONS "$p" -H 'Origin: https://claude.ai')
  echo "$p  POST=$post HEAD=$head OPTIONS=$opts"
done
echo -n "OAuth metadata (404 = sin inicio de sesión): "
curl -s -m 30 -o /dev/null -w "%{http_code}\n" "$BASE/.well-known/oauth-protected-resource"

if [ -x "$REPO/.venv/bin/pytest" ]; then
  (cd "$REPO" && IMPACTU_MCP_URL="$URL" .venv/bin/pytest -q -m live 2>&1 | tail -3)
else
  echo "Sin $REPO/.venv: clonar colav-playground/impactu-mcp e instalar con pip install -e '.[test]' para las pruebas en vivo."
fi
