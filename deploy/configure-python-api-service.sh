#!/bin/bash
set -euo pipefail

REPO="${PROJETO_TJSP_REPO:-$HOME/Downloads/PROJETO-TJSP}"
VENV="${PROJETO_TJSP_VENV:-$HOME/python/.venv}"
DOCUMENTS_DIR="${DOCUMENTOS_MODELO_DIR:-/run/media/daniel/c1eb5cb7-675f-4e8c-9564-4dabc66d9164}"
SERVICE="${PROJETO_TJSP_SERVICE:-python-api.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN_FILE="${DROPIN_DIR}/10-projeto-tjsp.conf"

cat <<EOF | sudo tee "$DROPIN_FILE" >/dev/null
[Service]
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
Environment=DOCUMENTOS_MODELO_DIR=$DOCUMENTS_DIR
ExecStart=
ExecStart=$VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
EOF

sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE"
sleep 2
sudo systemctl is-active --quiet "$SERVICE"

curl --fail --silent --show-error http://127.0.0.1:8000/files
printf '\nServiço %s configurado e GET /files respondeu corretamente.\n' "$SERVICE"
