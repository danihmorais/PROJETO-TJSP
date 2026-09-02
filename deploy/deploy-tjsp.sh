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
echo "Script carregado de: ${BASH_SOURCE[0]}"
echo "Serviço: $SERVICE"
echo "=========================================="

exec 200>"$LOCK"
flock -n 200 || { set_status failure "Outro deploy do TJSP já está em execução."; exit 1; }

cd "$REPO"
git fetch origin
git cat-file -e "$SHA^{commit}" 2>/dev/null || { set_status failure "Commit não encontrado."; exit 1; }
git checkout --force "$SHA"
echo "HEAD após checkout: $(git rev-parse HEAD)"

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

# Aguarda o serviço ficar ativo.
for i in $(seq 1 15); do
    if /usr/bin/systemctl is-active --quiet "$SERVICE"; then
        break
    fi
    sleep 1
done
/usr/bin/systemctl is-active --quiet "$SERVICE" || { echo "Serviço $SERVICE não iniciou."; exit 1; }

# Mostra imediatamente o estado do serviço e o listener, facilitando o diagnóstico.
echo "Estado do serviço após restart:"
/usr/bin/systemctl is-active "$SERVICE" || true
echo "Listeners TCP relacionados à porta 8000:"
/usr/bin/ss -ltnp 2>/dev/null | /usr/bin/grep -E '(:8000[[:space:]]|:8000$)' || echo "Nenhum listener encontrado em 8000."

# O systemd pode marcar o serviço como ativo antes de o Uvicorn estar pronto
# para aceitar conexões. Aguarda o endpoint de health responder corretamente.
health_check=""
health_ok=0
for i in $(seq 1 20); do
    if health_check=$(/usr/bin/curl --ipv4 --fail --silent --show-error --connect-timeout 2 --max-time 3 http://127.0.0.1:8000/health 2>&1); then
        health_ok=1
        echo "GET /health respondeu na tentativa $i/20"
        break
    fi
    echo "Aguardando /health ($i/20): ${health_check:-sem resposta}"
    sleep 1
done

if [ "$health_ok" -ne 1 ]; then
    echo "GET /health não respondeu após 20 tentativas."
    echo "Listeners TCP no momento da falha:"
    /usr/bin/ss -ltnp 2>/dev/null | /usr/bin/grep -E '(:8000[[:space:]]|:8000$)' || echo "Nenhum listener encontrado em 8000."
    /usr/bin/systemctl status "$SERVICE" --no-pager -l || true
    /usr/bin/journalctl -u "$SERVICE" -n 40 --no-pager || true
    set_status failure "GET /health não respondeu após 20 tentativas: ${health_check:-sem resposta}"
    exit 1
fi

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
