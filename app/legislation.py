from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .config import Source

# Metadados editoriais que não fazem parte do texto normativo vigente para estudo.
EDITORIAL_PATTERNS = (
    r"\[?(?:Redação dada|Incluído|Incluída|Revogado|Revogada|Alterado|Alterada)\s+pela\s+(?:Lei|Emenda|Medida Provisória)[^\]\n]*\]?",
    r"\[?Vide\s+(?:Lei|Emenda|Decreto)[^\]\n]*\]?",
    r"\[?(?:Renumerado|Transformado)\s+pela\s+(?:Lei|Emenda|Decreto)[^\]\n]*\]?",
)

@dataclass(frozen=True)
class Device:
    number: str
    text: str


def clean_text(text: str) -> str:
    # Remove Markdown/HTML-style links antes dos demais metadados.
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    for pattern in EDITORIAL_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.I)
    # Elimina URLs remanescentes, mas preserva o texto legislativo.
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_article_number(raw: str) -> str:
    return raw.lower().replace("º", "").replace("°", "").replace(" ", "")


def _number(value: str) -> int | None:
    match = re.match(r"^(\d+)", normalize_article_number(value))
    return int(match.group(1)) if match else None


def article_in_ranges(number: str, ranges: tuple[str, ...]) -> bool:
    current = _number(number)
    if current is None:
        return False
    for spec in ranges:
        parts = spec.split("-", 1)
        start = _number(parts[0])
        end = _number(parts[-1])
        if start is not None and end is not None and start <= current <= end:
            return True
    return False


def extract_articles(html: str, source: Source) -> list[Device]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    # Extrai do texto completo para não depender de como o site separou parágrafos/divs.
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    # Captura cada artigo até o início do próximo. Preserva incisos/parágrafos no meio.
    matches = list(re.finditer(
        r"(?mi)(?<![A-Za-z])Art\.?\s*(\d+(?:[A-Za-z])?)[º°]?\s*[—–-]?\s*",
        text,
    ))
    results: list[Device] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        number = match.group(1)
        if source.article_ranges and not article_in_ranges(number, source.article_ranges):
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = clean_text(text[match.start():end])
        if not body or number in seen:
            continue
        seen.add(number)
        results.append(Device(number=number, text=body))
    return results


async def fetch_source(source: Source) -> tuple[list[Device], datetime]:
    headers = {
        "User-Agent": "PROJETO-TJSP/1.0 (ferramenta educacional; contato via GitHub)"
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(source.url)
        response.raise_for_status()
    return extract_articles(response.text, source), datetime.now(timezone.utc)
