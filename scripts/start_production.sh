#!/usr/bin/env bash
# Evo 生产模式启动：构建前端 + 单端口托管 Admin UI + API
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

echo "==> 构建 admin-ui"
cd "$ROOT/admin-ui"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build

echo "==> 启动 Admin API + SPA (port ${PORT:-8000})"
cd "$ROOT/src"
export PYTHONPATH=.
export EVO_ADMIN_WORKSPACE="${EVO_ADMIN_WORKSPACE:-$ROOT}"
export EVO_ENV="${EVO_ENV:-production}"
export PORT="${PORT:-8000}"

exec python3 -m uvicorn admin.server:create_app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --factory
