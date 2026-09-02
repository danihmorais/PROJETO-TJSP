from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from .config import SOURCES
from .legislation import fetch_source

app = FastAPI(title="PROJETO-TJSP — Compilador Legislativo", version="1.0.0")

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>PROJETO-TJSP</title><style>body{font-family:system-ui;max-width:1100px;margin:40px auto;padding:0 20px}button{padding:10px 16px;cursor:pointer}pre{white-space:pre-wrap;line-height:1.6}</style></head><body><h1>Compilado Legislativo — TJSP</h1><p>Busca legislação em fontes oficiais, aplica o recorte programático e remove notas editoriais de alteração.</p><button onclick='gerar()'>Gerar compilado</button><p id='status'></p><pre id='out'></pre><script>async function gerar(){status.textContent='Consultando fontes oficiais...';const r=await fetch('/compilado');const t=await r.text();out.textContent=t;status.textContent='Concluído.'}</script></body></html>"""

@app.get("/fontes")
async def fontes():
    return [{"key": s.key, "materia": s.subject, "titulo": s.title, "fonte_oficial": s.url, "artigos": s.article_ranges, "documento_integral": s.full_document} for s in SOURCES]

@app.get("/compilado", response_class=PlainTextResponse)
async def compilado():
    fetched = await asyncio.gather(*(fetch_source(s) for s in SOURCES), return_exceptions=True)
    groups: dict[str, list[tuple]] = defaultdict(list)
    errors = []
    for source, result in zip(SOURCES, fetched):
        if isinstance(result, Exception):
            errors.append(f"- {source.title}: {result}")
            continue
        devices, timestamp = result
        groups[source.subject].append((source, devices, timestamp))

    lines = ["COMPILADO LEGISLATIVO — PROJETO-TJSP", "", f"Gerado em: {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}", "", "ATENÇÃO: conteúdo destinado a estudo. A fonte oficial deve prevalecer em caso de divergência.", ""]
    for subject, entries in groups.items():
        lines += [f"# {subject}", ""]
        for source, devices, timestamp in entries:
            lines += [f"## {source.title}", f"Fonte oficial: {source.url}", f"Consulta: {timestamp.isoformat()}", ""]
            if not devices:
                lines.append("Nenhum dispositivo foi extraído; verifique o parser/fonte.")
            for d in devices:
                lines += [f"### Art. {d.number}", d.text, ""]
    if errors:
        lines += ["# FALHAS DE CONSULTA", ""] + errors
    return "\n".join(lines)

@app.get("/health")
async def health():
    return {"status": "ok", "fontes": len(SOURCES)}
