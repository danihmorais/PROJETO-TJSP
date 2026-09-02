from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator

from .config import SOURCES
from .legislation import fetch_source
from .render import CompilationEntry, render_html, render_markdown

app = FastAPI(title="PROJETO-TJSP — Compilador Legislativo", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https://danihmorais\.github\.io|https?://localhost(:\\d+)?|https?://127\.0\.0\.1(:\\d+)?)$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

ALLOWED_OFFICIAL_SUFFIXES = (".gov.br", ".leg.br", ".jus.br")


class SourceInput(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    article_ranges: list[str] = Field(default_factory=list, max_length=100)
    full_document: bool = False

    @field_validator("url")
    @classmethod
    def official_https_url(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https":
            raise ValueError("A fonte deve usar HTTPS")
        if not host.endswith(ALLOWED_OFFICIAL_SUFFIXES):
            raise ValueError("A fonte deve ser um domínio oficial .gov.br, .leg.br ou .jus.br")
        return value


class CompileRequest(BaseModel):
    sources: list[SourceInput] = Field(min_length=1, max_length=100)
    format: str = Field(default="html", pattern="^(markdown|html|json)$")


def source_to_dict(source) -> dict:
    return {
        "key": source.key,
        "subject": source.subject,
        "title": source.title,
        "url": source.url,
        "article_ranges": list(source.article_ranges),
        "full_document": source.full_document,
    }


def source_from_input(item: SourceInput):
    from .config import Source

    return Source(
        item.key,
        item.subject,
        item.title,
        str(item.url),
        tuple(item.article_ranges),
        item.full_document,
    )


async def build_compilation(sources) -> tuple[list[CompilationEntry], datetime]:
    fetched = await asyncio.gather(*(fetch_source(source) for source in sources), return_exceptions=True)
    entries: list[CompilationEntry] = []
    for source, result in zip(sources, fetched):
        if isinstance(result, Exception):
            entries.append(CompilationEntry(source, [], datetime.now(timezone.utc), str(result)))
        else:
            devices, consulted_at = result
            entries.append(CompilationEntry(source, devices, consulted_at))
    return entries, datetime.now(timezone.utc)


def entries_json(entries, generated_at):
    return {
        "generated_at": generated_at.isoformat(),
        "entries": [
            {
                "key": entry.source.key,
                "materia": entry.source.subject,
                "titulo": entry.source.title,
                "fonte_oficial": entry.source.url,
                "artigos": [device.number for device in entry.devices],
                "erro": entry.error,
            }
            for entry in entries
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return "<html><body><h1>PROJETO-TJSP API</h1><p>Use a interface do GitHub Pages para configurar o compilado.</p><a href='/docs'>Documentação da API</a></body></html>"


@app.get("/health")
async def health():
    return {"status": "ok", "fontes_padrao": len(SOURCES), "persistencia": "localStorage no cliente"}


@app.get("/api/defaults")
async def defaults():
    return {"sources": [source_to_dict(source) for source in SOURCES]}


@app.get("/fontes")
async def fontes():
    return [source_to_dict(source) for source in SOURCES]


@app.post("/api/compilar")
async def api_compilar(request: CompileRequest):
    sources = [source_from_input(item) for item in request.sources]
    entries, generated_at = await build_compilation(sources)
    if request.format == "html":
        return HTMLResponse(render_html(entries, generated_at))
    if request.format == "json":
        return entries_json(entries, generated_at)
    return PlainTextResponse(render_markdown(entries, generated_at), media_type="text/markdown; charset=utf-8")


@app.get("/compilado")
async def compilado():
    entries, generated_at = await build_compilation(SOURCES)
    return HTMLResponse(render_html(entries, generated_at))
