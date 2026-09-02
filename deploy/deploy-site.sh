#!/bin/bash
set -euo pipefail

REPO="${DANIHMORAIS_GITHUB_PAGES_REPO:-/home/daniel/Downloads/danihmorais.github.io}"
VENV="${DANIHMORAIS_GITHUB_PAGES_VENV:-/home/daniel/python/.venv}"
LOG="${DANIHMORAIS_GITHUB_PAGES_LOG:-/home/daniel/python/deploy.log}"
STATUS_DIR="${DEPLOY_STATUS_DIR:-/home/daniel/python/deploy-status}/DANIHMORAIS-GITHUB-PAGES"
SERVICE="${DANIHMORAIS_GITHUB_PAGES_SERVICE:-python-api.service}"
SERVICE_USER="${DANIHMORAIS_GITHUB_PAGES_USER:-daniel}"
LOCK="/tmp/python-api-deploy.lock"
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
trap 'rc=$?; echo "$(date) - DEPLOY SITE FALHOU"; set_status failure "Deploy falhou na etapa: $BASH_COMMAND"; exit "$rc"' ERR

echo ""
echo "=========================================="
echo "$(date) - DEPLOY SITE INICIADO"
echo "Commit: $SHA"
echo "Serviço: $SERVICE"
echo "=========================================="

# O serviço FastAPI é compartilhado pelos dois repositórios.
# Um único lock impede reinícios concorrentes e evita que um deploy sobrescreva o outro.
exec 200>"$LOCK"
flock -n 200 || { set_status failure "Outro deploy que usa o serviço FastAPI já está em execução."; exit 1; }

cd "$REPO"
git fetch origin
git cat-file -e "$SHA^{commit}" 2>/dev/null || { set_status failure "Commit não encontrado."; exit 1; }
git checkout --force "$SHA"
git rev-parse HEAD

"$VENV/bin/python" -m pip install -r "$REPO/requirements.txt"
"$VENV/bin/python" -m pip check
"$VENV/bin/python" -c "import main; print('IMPORT MAIN OK')"

# O serviço compartilhado deve executar o agregador deste repositório.
# Usa systemctl edit para persistir o override sem depender de gravação direta
# em /etc/systemd/system pelo shell do deploy.
/usr/bin/printf '%s\n' \
    '[Service]' \
    "User=$SERVICE_USER" \
    "WorkingDirectory=$REPO" \
    "Environment=PYTHONPATH=$REPO" \
    'ExecStart=' \
    "ExecStart=$VENV/bin/uvicorn main:app --host 0.0.0.0 --port 8000" \
    | /usr/bin/sudo -n /usr/bin/systemctl edit --stdin "$SERVICE"

/usr/bin/sudo -n /usr/bin/systemctl daemon-reload
/usr/bin/sudo -n /usr/bin/systemctl restart "$SERVICE"

for i in $(seq 1 20); do
    if /usr/bin/systemctl is-active --quiet "$SERVICE"; then
        break
    fi
    sleep 1
done
/usr/bin/systemctl is-active --quiet "$SERVICE" || { echo "Serviço $SERVICE não iniciou."; exit 1; }

health_check=""
for i in $(seq 1 20); do
    if health_check=$(/usr/bin/curl --ipv4 --fail --silent --show-error --connect-timeout 2 --max-time 3 http://127.0.0.1:8000/health 2>&1); then
        break
    fi
    echo "Aguardando /health ($i/20): ${health_check:-sem resposta}"
    sleep 1
done

/usr/bin/python3 - "$health_check" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if not isinstance(payload, dict) or payload.get("status") != "ok":
    raise SystemExit("GET /health não retornou status=ok")
PY

estudos_check=$(/usr/bin/curl --ipv4 --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/estudos/health)
/usr/bin/python3 - "$estudos_check" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if not isinstance(payload, dict) or payload.get("status") != "ok":
    raise SystemExit("/estudos/health não retornou status=ok")
PY

echo "GET /health OK"
echo "GET /estudos/health OK"
set_status success "Deploy concluído com sucesso"
echo "$(date) - DEPLOY SITE CONCLUÍDO COM SUCESSO"
echo "=========================================="
