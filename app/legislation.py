from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .config import Source

# Texto editorial encontrado nas páginas de legislação, mas que não integra
# a redação substantiva do dispositivo.
EDITORIAL_LINK_RE = re.compile(
    r"\[\s*\(?\s*(?:Redação dada|Incluído|Incluída|Revogado|Revogada|Alterado|Alterada|"
    r"Renumerado|Renumerada|Transformado|Transformada|Vide)\b.*?\)?\s*\]\([^)]*\)",
    re.IGNORECASE,
)
EDITORIAL_NOTE_RE = re.compile(
    r"\s*\(\s*(?:Redação dada|Incluído|Incluída|Revogado|Revogada|Alterado|Alterada|"
    r"Renumerado|Renumerada|Transformado|Transformada)\b[^()\n]*\)",
    re.IGNORECASE,
)
EDITORIAL_VIDE_RE = re.compile(r"\s*\(\s*Vide\b[^()\n]*\)", re.IGNORECASE)
EDITORIAL_STATUS_RE = re.compile(r"\s*\(\s*(?:Vigência|Produção de efeitos|NR)\s*\)", re.IGNORECASE)

# A AL-SP publica anotações depois do texto, muitas vezes na própria linha:
# "... (NR) - Artigo 319 com redação dada ..."
# ou "... (NR) - acrescentado pela ...".
EDITORIAL_TAIL_PATTERNS = (
    re.compile(
        r"\s*(?:[-–—]\s*)?(?:\(?NR\)?\s*[-–—]\s*)?"
        r"(?:Artigo|Art\.?)[ \t]*\d+(?:-[A-Za-z]+)?[º°]?[ \t]+"
        r"(?:com redação|reposicionado|renumerado|revogado|acrescentado|incluído|incluída|"
        r"alterado|alterada|transformado|transformada)\b.*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"\s*(?:[-–—]\s*)?(?:[\"“”']?Caput[\"“”']?)[ \t]+"
        r"(?:com redação|reposicionado|renumerado|revogado|acrescentado|incluído|incluída|"
        r"alterado|alterada|transformado|transformada)\b.*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"\s*[-–—][ \t]*(?:acrescentado|acrescentada|incluído|incluída|revogado|revogada|"
        r"alterado|alterada|renumerado|renumerada|transformado|transformada|"
        r"suprimido|suprimida)\b.*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"\s*(?:[-–—]\s*)?(?:Parágrafo\s+único|§\s*\d+[º°]?)[ \t]+"
        r"(?:com redação|reposicionado|renumerado|revogado|acrescentado|incluído|incluída|"
        r"alterado|alterada|transformado|transformada)\b.*$",
        re.IGNORECASE | re.MULTILINE,
    ),
)
EDITORIAL_BLOCK_RE = re.compile(
    r"^(?:[-–—]\s*)?(?:\(?NR\)?|(?:Artigo|Art\.?)[ \t]*\d+(?:-[A-Za-z]+)?[º°]?[ \t]+"
    r"(?:com redação|reposicionado|renumerado|revogado|acrescentado|incluído|incluída|"
    r"alterado|alterada|transformado|transformada)|(?:Parágrafo\s+único|§\s*\d+[º°]?)"
    r"[ \t]+(?:com redação|reposicionado|renumerado|revogado|acrescentado|incluído|incluída|"
    r"alterado|alterada|transformado|transformada)|[\"“”']?Caput[\"“”']?[ \t]+"
    r"(?:com redação|reposicionado|renumerado|revogado|acrescentado|incluído|incluída|"
    r"alterado|alterada|transformado|transformada))\b.*$",
    re.IGNORECASE,
)

ARTICLE_RE = re.compile(
    r"(?mi)^[ \t]*(?:Art\.?|Artigo)\s*(\d+(?:-[A-Za-z]+)?)[º°]?\s*(?:[—–-]\s*)?"
)


@dataclass(frozen=True)
class Device:
    number: str
    text: str


def _strip_editorial_tails(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        for pattern in EDITORIAL_TAIL_PATTERNS:
            text = pattern.sub("", text)
    return text


def clean_text(text: str) -> str:
    """Remove ruído editorial sem reescrever a redação normativa."""
    text = EDITORIAL_LINK_RE.sub("", text)
    text = EDITORIAL_NOTE_RE.sub("", text)
    text = EDITORIAL_VIDE_RE.sub("", text)
    text = EDITORIAL_STATUS_RE.sub("", text)
    text = _strip_editorial_tails(text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)

    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line or EDITORIAL_BLOCK_RE.match(line):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def normalize_article_number(raw: str) -> str:
    return raw.lower().replace("º", "").replace("°", "").replace(" ", "")


def _article_id(value: str) -> tuple[int, str]:
    normalized = normalize_article_number(value)
    match = re.fullmatch(r"(\d+)(?:-([a-z]+))?", normalized)
    if not match:
        raise ValueError(f"Número de artigo inválido: {value!r}")
    return int(match.group(1)), (match.group(2) or "")


def _is_range_spec(spec: str) -> bool:
    return bool(re.fullmatch(r"\d+\s*-\s*\d+", spec))


def article_in_ranges(number: str, ranges: tuple[str, ...]) -> bool:
    current_num, current_suffix = _article_id(number)
    for raw_spec in ranges:
        spec = normalize_article_number(raw_spec)
        if _is_range_spec(spec):
            start, _ = _article_id(spec.split("-", 1)[0])
            end, _ = _article_id(spec.split("-", 1)[1])
            if start <= current_num <= end:
                return True
        else:
            target_num, target_suffix = _article_id(spec)
            if current_num == target_num and current_suffix == target_suffix:
                return True
    return False


def extract_articles(html: str, source: Source) -> list[Device]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "del", "s", "strike"]):
        node.decompose()
    for node in soup.find_all(style=re.compile(r"line-through", re.IGNORECASE)):
        node.decompose()

    text = "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    )
    matches = list(ARTICLE_RE.finditer(text))

    results: list[Device] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        number = match.group(1)
        normalized = normalize_article_number(number)
        if source.article_ranges and not article_in_ranges(number, source.article_ranges):
            continue

        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = clean_text(text[match.start():end])
        if not body or normalized in seen:
            continue
        seen.add(normalized)
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
