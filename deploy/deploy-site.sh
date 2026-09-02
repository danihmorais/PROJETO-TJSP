#!/bin/bash
set -euo pipefail

REPO="${DANIHMORAIS_GITHUB_PAGES_REPO:-/home/daniel/Downloads/danihmorais.github.io}"
VENV="${DANIHMORAIS_GITHUB_PAGES_VENV:-/home/daniel/python/.venv}"
LOG="${DANIHMORAIS_GITHUB_PAGES_LOG:-/home/daniel/python/deploy.log}"
STATUS_DIR="${DEPLOY_STATUS_DIR:-/home/daniel/python/deploy-status}/DANIHMORAIS-GITHUB-PAGES"
INSTALL_ROOT="${DEPLOY_INSTALL_ROOT:-/home/daniel/python}"
SERVICE="${DANIHMORAIS_GITHUB_PAGES_SERVICE:-python-api.service}"
LOCK="/tmp/danihmorais-github-pages-deploy.lock"
SHA="${1:-}"

if [ -z "$SHA" ]; then echo "SHA não informado"; exit 1; fi
mkdir -p "$STATUS_DIR"
STATUS_FILE="$STATUS_DIR/$SHA.json"

set_status() {
    local state="$1" message="$2"
    /usr/bin/python3 - "$SHA" "$state" "$message" "$STATUS_FILE" <<'PY'
import json, sys
sha, state, message, path = sys.argv[1:]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"project":"DANIHMORAIS-GITHUB-PAGES","sha":sha,"state":state,"message":message}, f, ensure_ascii=False)
PY
}

exec >> "$LOG" 2>&1
trap 'echo "$(date) - DEPLOY SITE FALHOU"; set_status failure "Deploy falhou. Consulte deploy.log."' ERR

echo ""
echo "=========================================="
echo "$(date) - DEPLOY SITE INICIADO"
echo "Commit: $SHA"
echo "Serviço: $SERVICE"
echo "=========================================="

exec 200>"$LOCK"
flock -n 200 || { set_status failure "Outro deploy do site já está em execução."; exit 1; }

cd "$REPO"
git fetch origin
git cat-file -e "$SHA^{commit}" 2>/dev/null || { set_status failure "Commit não encontrado."; exit 1; }
git checkout --force "$SHA"
git rev-parse HEAD

"$VENV/bin/python" -m pip install -r "$REPO/requirements.txt"
"$VENV/bin/python" -m pip check
"$VENV/bin/python" -c "import main; print('IMPORT MAIN OK')"

/usr/bin/sudo -n /usr/bin/systemctl restart "$SERVICE"
sleep 3
/usr/bin/systemctl is-active --quiet "$SERVICE" || { echo "Serviço $SERVICE não iniciou."; exit 1; }

set_status success "Deploy concluído com sucesso"
echo "$(date) - DEPLOY SITE CONCLUÍDO COM SUCESSO"
echo "=========================================="
