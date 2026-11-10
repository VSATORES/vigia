#!/bin/bash
# Roda antes de qualquer push: testes + varredura de credenciais e marcas. Para se achar algo.
set -e
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests >/dev/null 2>&1 || { echo "testes falharam"; python3 -m unittest discover -s tests; exit 1; }
if git ls-files -co --exclude-standard | grep -v '^scripts/checar_publico.sh$' | xargs grep -nIE '(mcp_live_|phx_[A-Za-z0-9]{10}|gho_|ghp_|sk-ant-|CF-Access-Client-Secret"\s*=\s*"[^$])' 2>/dev/null; then
  echo "possível credencial no repositório"; exit 1; fi
echo "ok: pode publicar"
