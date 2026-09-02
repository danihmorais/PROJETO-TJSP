from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import SOURCES
from .legislation import fetch_source
from .render import CompilationEntry, render_html, render_markdown

app = FastAPI(title="PROJETO-TJSP — Compilador Legislativo", version="1.1.0")


class CompileRequest(BaseModel):
    keys: list[str] | None = Field(default=None, description="Chaves das fontes a incluir")
    format: str = Field(default="markdown", pattern="^(markdown|html|json)$")


async def build_compilation(keys: list[str] | None = None) -> tuple[list[CompilationEntry], datetime]:
    selected = [s for s in SOURCES if keys is None or s.key in keys]
    if keys is not None:
        known = {s.key for s in SOURCES}
        unknown = sorted(set(keys) - known)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Fontes desconhecidas: {', '.join(unknown)}")

    fetched = await asyncio.gather(*(fetch_source(source) for source in selected), return_exceptions=True)
    entries: list[CompilationEntry] = []
    for source, result in zip(selected, fetched):
        if isinstance(result, Exception):
            entries.append(CompilationEntry(source, [], datetime.now(timezone.utc), str(result)))
        else:
            devices, consulted_at = result
            entries.append(CompilationEntry(source, devices, consulted_at))
    return entries, datetime.now(timezone.utc)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>PROJETO-TJSP</title><style>body{font-family:system-ui;max-width:900px;margin:50px auto;padding:0 22px;line-height:1.55}button,a{display:inline-block;padding:11px 16px;margin:4px 4px 4px 0;border:1px solid #bbb;border-radius:7px;text-decoration:none;color:inherit;background:#fff;cursor:pointer}.primary{background:#111;color:#fff}#status{margin-top:20px}.links{margin-top:20px}</style></head><body><h1>Compilado Legislativo — TJSP</h1><p>Gera, sob demanda, o recorte do edital a partir das fontes oficiais e remove notas editoriais de alteração.</p><button class='primary' onclick='gerar("html")'>Gerar compilado</button><button onclick='gerar("markdown")'>Markdown</button><div class='links'><a href='/fontes'>Ver fontes e recortes</a><a href='/docs'>API /docs</a></div><p id='status'></p><script>async function gerar(formato){status.textContent='Consultando as fontes oficiais...';const r=await fetch('/compilado?format='+formato);if(!r.ok){status.textContent='Erro ao gerar: '+await r.text();return}const t=await r.text();if(formato==='html'){document.open();document.write(t);document.close()}else{const w=window.open();w.document.write('<pre style="white-space:pre-wrap;font-family:system-ui;padding:30px">'+t.replaceAll('&','&amp;').replaceAll('<','&lt;')+'</pre>');w.document.close();}} </script></body></html>"""


@app.get("/fontes")
async def fontes():
    return [
        {"key": s.key, "materia": s.subject, "titulo": s.title, "fonte_oficial": s.url, "artigos": s.article_ranges, "documento_integral": s.full_document}
        for s in SOURCES
    ]


@app.get("/compilado")
async def compilado(format: str = Query("markdown", pattern="^(markdown|html|json)$")):
    entries, generated_at = await build_compilation()
    if format == "html":
        return HTMLResponse(render_html(entries, generated_at))
    if format == "json":
        return {"generated_at": generated_at.isoformat(), "entries": [{"key": e.source.key, "materia": e.source.subject, "titulo": e.source.title, "fonte_oficial": e.source.url, "artigos": [d.number for d in e.devices], "erro": e.error} for e in entries]}
    return PlainTextResponse(render_markdown(entries, generated_at), media_type="text/markdown; charset=utf-8")


@app.post("/api/compilar")
async def api_compilar(request: CompileRequest):
    entries, generated_at = await build_compilation(request.keys)
    if request.format == "html":
        return HTMLResponse(render_html(entries, generated_at))
    if request.format == "json":
        return {"generated_at": generated_at.isoformat(), "entries": [{"key": e.source.key, "materia": e.source.subject, "titulo": e.source.title, "fonte_oficial": e.source.url, "artigos": [d.number for d in e.devices], "erro": e.error} for e in entries]}
    return PlainTextResponse(render_markdown(entries, generated_at), media_type="text/markdown; charset=utf-8")


@app.get("/health")
async def health():
    return {"status": "ok", "fontes": len(SOURCES)}
