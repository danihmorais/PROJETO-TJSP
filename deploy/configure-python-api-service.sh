#!/bin/bash
set -euo pipefail

REPO="${PROJETO_TJSP_REPO:-$HOME/Downloads/PROJETO-TJSP}"
VENV="${PROJETO_TJSP_VENV:-$HOME/python/.venv}"
DOCUMENTS_DIR="${DOCUMENTOS_MODELO_DIR:-/run/media/daniel/c1eb5cb7-675f-4e8c-9564-4dabc66d9164}"
SERVICE="${PROJETO_TJSP_SERVICE:-python-api.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN_FILE="${DROPIN_DIR}/10-projeto-tjsp.conf"
SUDOERS_FILE="/etc/sudoers.d/projeto-tjsp-deploy"

install -d -m 0755 "$DROPIN_DIR"

cat <<EOF | sudo tee "$DROPIN_FILE" >/dev/null
[Unit]
RequiresMountsFor=$DOCUMENTS_DIR

[Service]
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
Environment=DOCUMENTOS_MODELO_DIR=$DOCUMENTS_DIR
ExecStart=
ExecStart=$VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
EOF

# O webhook roda como usuário normal e precisa apenas destas operações do systemd.
# Não concedemos sudo irrestrito ao processo de deploy.
sudo tee "$SUDOERS_FILE" >/dev/null <<EOF
$USER ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload
$USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart $SERVICE
EOF
sudo chmod 0440 "$SUDOERS_FILE"
sudo visudo -cf "$SUDOERS_FILE"

sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE"
sleep 2
sudo systemctl is-active --quiet "$SERVICE"

printf 'Serviço %s configurado com DOCUMENTOS_MODELO_DIR=%s e API reiniciada.\n' "$SERVICE" "$DOCUMENTS_DIR"
