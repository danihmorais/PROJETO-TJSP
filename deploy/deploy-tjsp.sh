#!/bin/bash
set -euo pipefail

REPO="${PROJETO_TJSP_REPO:-/home/daniel/Downloads/PROJETO-TJSP}"
VENV="${PROJETO_TJSP_VENV:-/home/daniel/python/.venv}"
LOG="${PROJETO_TJSP_LOG:-/home/daniel/python/deploy-tjsp.log}"
STATUS_DIR="${DEPLOY_STATUS_DIR:-/home/daniel/python/deploy-status/PROJETO-TJSP}"
INSTALL_ROOT="${DEPLOY_INSTALL_ROOT:-/home/daniel/python}"
SERVICE="${PROJETO_TJSP_SERVICE:-python-api.service}"
LOCK="/tmp/projeto-tjsp-deploy.lock"
SHA="${1:-}"

if [ -z "$SHA" ]; then
    echo "SHA não informado"
    exit 1
fi

mkdir -p "$STATUS_DIR"
STATUS_FILE="$STATUS_DIR/$SHA.json"

set_status() {
    local state="$1"
    local message="$2"
    /usr/bin/python3 - "$SHA" "$state" "$message" "$STATUS_FILE" <<'PY'
import json, sys
sha, state, message, path = sys.argv[1:]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"project":"PROJETO-TJSP","sha":sha,"state":state,"message":message}, f, ensure_ascii=False)
PY
}

exec >> "$LOG" 2>&1
trap 'rc=$?; msg="Deploy falhou na etapa: $BASH_COMMAND"; echo "$(date) - $msg"; set_status failure "$msg"; exit "$rc"' ERR

echo ""
echo "=========================================="
echo "$(date) - DEPLOY TJSP INICIADO"
echo "Commit: $SHA"
echo "Serviço: $SERVICE"
echo "=========================================="

exec 200>"$LOCK"
flock -n 200 || { set_status failure "Outro deploy do TJSP já está em execução."; exit 1; }

cd "$REPO"
git fetch origin
git cat-file -e "$SHA^{commit}" 2>/dev/null || { set_status failure "Commit não encontrado."; exit 1; }
git checkout --force "$SHA"
git rev-parse HEAD

# Mantém os scripts usados pelo dispatcher sincronizados com o repositório.
install -m 0755 "$REPO/deploy/deploy-tjsp.sh" "$INSTALL_ROOT/deploy-tjsp.sh.new"
mv -f "$INSTALL_ROOT/deploy-tjsp.sh.new" "$INSTALL_ROOT/deploy-tjsp.sh"
install -m 0755 "$REPO/deploy/deploy-site.sh" "$INSTALL_ROOT/deploy-site.sh"
install -m 0644 "$REPO/deploy/deploy_server.py" "$INSTALL_ROOT/deploy_server.py"

"$VENV/bin/python" -m pip install -r "$REPO/requirements.txt"
"$VENV/bin/python" -m pip check
PYTHONPATH="$REPO" "$VENV/bin/python" -c "from app.main import app; print(app.title)"

/usr/bin/sudo -n /usr/bin/systemctl daemon-reload
/usr/bin/sudo -n /usr/bin/systemctl restart "$SERVICE"

for i in $(seq 1 10); do
    if /usr/bin/systemctl is-active --quiet "$SERVICE"; then
        break
    fi
    sleep 1
done
/usr/bin/systemctl is-active --quiet "$SERVICE" || { echo "Serviço $SERVICE não iniciou."; exit 1; }

# Valida a própria API do PROJETO-TJSP sem depender de recursos externos ao deploy.
health_check=$(/usr/bin/curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8000/health)
"$VENV/bin/python" - "$health_check" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if not isinstance(payload, dict) or payload.get("status") != "ok":
    raise SystemExit("GET /health não retornou status=ok")
print("GET /health OK")
PY

set_status success "Deploy concluído com sucesso; GET /health validado"
echo "$(date) - DEPLOY TJSP CONCLUÍDO COM SUCESSO"
echo "=========================================="
