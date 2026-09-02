from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator

from .config import SOURCES, Source
from .legislation import fetch_source
from .render import CompilationEntry, render_html, render_markdown

app = FastAPI(title="PROJETO-TJSP — Compilador Legislativo", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://danihmorais.github.io", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

OFFICIAL_SUFFIXES = (".gov.br", ".leg.br", ".jus.br")
DEFAULT_FILES_DIR = "/run/media/daniel/c1eb5cb7-675f-4e8c-9564-4dabc66d9164"


class SourceInput(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    article_ranges: list[str] = Field(default_factory=list, max_length=100)
    full_document: bool = False
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def official_https_url(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https":
            raise ValueError("A fonte deve usar HTTPS")
        if not host.endswith(OFFICIAL_SUFFIXES):
            raise ValueError("A fonte deve ser um domínio oficial .gov.br, .leg.br ou .jus.br")
        return value

    @field_validator("article_ranges")
    @classmethod
    def validate_ranges(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Intervalos de artigos não podem ser vazios")
        return cleaned


class CompileRequest(BaseModel):
    sources: list[SourceInput] = Field(min_length=1, max_length=100)
    format: str = Field(default="html", pattern="^(markdown|html|json)$")

    @field_validator("sources")
    @classmethod
    def unique_keys(cls, values: list[SourceInput]) -> list[SourceInput]:
        keys = [item.key for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("As fontes devem possuir chaves únicas")
        return values


def source_to_dict(source: Source) -> dict:
    return {
        "key": source.key,
        "subject": source.subject,
        "title": source.title,
        "url": source.url,
        "article_ranges": list(source.article_ranges),
        "full_document": source.full_document,
        "enabled": True,
    }


def source_from_input(item: SourceInput) -> Source:
    return Source(item.key, item.subject, item.title, str(item.url), tuple(item.article_ranges), item.full_document)


def files_root() -> Path:
    configured = os.environ.get("DOCUMENTOS_MODELO_DIR", DEFAULT_FILES_DIR).strip()
    if not configured:
        raise HTTPException(status_code=500, detail="DOCUMENTOS_MODELO_DIR não está configurado")
    root = Path(configured).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=503, detail="Diretório de documentos modelo indisponível")
    return root


def relative_file_path(root: Path, requested_path: str) -> Path:
    clean_path = requested_path.replace("\\", "/").lstrip("/")
    candidate = (root / clean_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Caminho de arquivo inválido") from exc
    return candidate


async def build_compilation(sources: list[Source]) -> tuple[list[CompilationEntry], datetime]:
    if not sources:
        raise HTTPException(status_code=400, detail="Nenhuma legislação habilitada")

    fetched = await asyncio.gather(*(fetch_source(source) for source in sources), return_exceptions=True)
    entries: list[CompilationEntry] = []
    for source, result in zip(sources, fetched):
        if isinstance(result, Exception):
            entries.append(CompilationEntry(source, [], datetime.now(timezone.utc), str(result)))
        else:
            devices, consulted_at = result
            entries.append(CompilationEntry(source, devices, consulted_at))
    return entries, datetime.now(timezone.utc)


def entries_json(entries: list[CompilationEntry], generated_at: datetime) -> dict:
    return {"generated_at": generated_at.isoformat(), "entries": [{
        "key": entry.source.key,
        "materia": entry.source.subject,
        "titulo": entry.source.title,
        "fonte_oficial": entry.source.url,
        "artigos": [device.number for device in entry.devices],
        "erro": entry.error,
    } for entry in entries]}


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return "<html lang='pt-BR'><body><h1>PROJETO-TJSP API</h1><p>Backend do compilador legislativo.</p><a href='/docs'>Documentação da API</a></body></html>"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "danihmorais-github-pages",
        "fontes_padrao": len(SOURCES),
        "persistencia": "localStorage no cliente",
    }


@app.get("/api/defaults")
async def defaults():
    return {"sources": [source_to_dict(source) for source in SOURCES]}


@app.get("/fontes")
async def fontes():
    return [source_to_dict(source) for source in SOURCES]


@app.get("/files")
async def list_files():
    root = files_root()
    files = []
    for path in root.rglob("*"):
        try:
            is_file = path.is_file()
        except OSError:
            continue
        if not is_file:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        files.append({
            "name": path.name,
            "path": relative,
            "type": "file",
            "size": size,
            "url": f"/files/{relative}",
        })

    files.sort(key=lambda item: item["path"].casefold())
    return {"files": files}


@app.get("/files/{requested_path:path}")
async def download_file(requested_path: str):
    root = files_root()
    candidate = relative_file_path(root, requested_path)
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(candidate, filename=candidate.name)


@app.post("/api/compilar")
async def api_compilar(request: CompileRequest):
    selected = [item for item in request.sources if item.enabled]
    if not selected:
        raise HTTPException(status_code=400, detail="Nenhuma legislação habilitada")
    sources = [source_from_input(item) for item in selected]
    entries, generated_at = await build_compilation(sources)
    if request.format == "html":
        return HTMLResponse(render_html(entries, generated_at))
    if request.format == "json":
        return entries_json(entries, generated_at)
    return PlainTextResponse(render_markdown(entries, generated_at), media_type="text/markdown; charset=utf-8")


@app.get("/compilado", response_class=HTMLResponse)
async def compilado():
    entries, generated_at = await build_compilation(list(SOURCES))
    return HTMLResponse(render_html(entries, generated_at))


def _load_optional_site_app():
    """Monta o agregador principal quando os dois repositórios estão disponíveis lado a lado."""
    site_root = Path(__file__).resolve().parents[2] / "danihmorais.github.io"
    site_main = site_root / "main.py"
    if not site_main.is_file():
        return None

    original_cwd = os.getcwd()
    original_sys_path = sys.path.copy()
    abs_site_root = site_root.resolve()
    module_name = "universe_licitacao_main"
    try:
        os.chdir(abs_site_root)
        sys.path.insert(0, str(abs_site_root))
        spec = importlib.util.spec_from_file_location(module_name, site_main)
        if spec is None or spec.loader is None:
            raise ImportError(f"Não foi possível carregar {site_main}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module.app
    finally:
        os.chdir(original_cwd)
        sys.path = original_sys_path


_site_app = _load_optional_site_app()
if _site_app is not None:
    # Mantém compatibilidade com o serviço já configurado para este entrypoint:
    # as rotas TJSP continuam disponíveis na raiz, enquanto o agregador fornece
    # /licita, /monta, /email, /geradorextrato e /estudos.
    app.mount("/", _site_app)
