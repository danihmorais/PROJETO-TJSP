from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

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
    r"(?mi)^[ \t]*(?:[>•·*]+\s*)?(?:Art(?:igo)?\.?)\s*"
    r"(\d+(?:-[A-Za-z]+)?)[º°]?\s*(?:[.·—–-]\s*)?"
)

RETRYABLE_STATUS_CODES = {403, 408, 425, 429, 500, 502, 503, 504}
PLANALTO_HOSTS = {"www.planalto.gov.br", "planalto.gov.br"}


@dataclass(frozen=True)
class Device:
    number: str
    text: str


def _detect_declared_encoding(response: httpx.Response) -> str | None:
    """Detecta charset HTTP/HTML sem confiar cegamente em response.text."""
    content_type = response.headers.get("content-type", "")
    match = re.search(r"charset\s*=\s*[\"']?\s*([\w.-]+)", content_type, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()

    head = response.content[:8192].decode("ascii", errors="ignore")
    match = re.search(r"<meta[^>]+charset\s*=\s*[\"']?\s*([\w.-]+)", head, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()

    match = re.search(
        r"<meta[^>]+content\s*=\s*[\"'][^\"']*charset\s*=\s*([\w.-]+)",
        head,
        re.IGNORECASE,
    )
    return match.group(1).strip().lower() if match else None


def _normalize_encoding_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.lower().replace("_", "-")
    aliases = {
        "latin1": "iso-8859-1",
        "latin-1": "iso-8859-1",
        "iso8859-1": "iso-8859-1",
        "windows1252": "windows-1252",
        "cp1252": "windows-1252",
    }
    return aliases.get(normalized, normalized)


def _decode_html_response(response: httpx.Response) -> str:
    """Decodifica HTML antigo do Planalto sem introduzir U+FFFD nos acentos."""
    raw = response.content
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    declared = _normalize_encoding_name(_detect_declared_encoding(response))
    candidates: list[str] = ["utf-8"]
    if declared and declared not in candidates:
        candidates.append(declared)
    for fallback in ("windows-1252", "iso-8859-1"):
        if fallback not in candidates:
            candidates.append(fallback)

    for encoding in candidates:
        try:
            decoded = raw.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
        if "\ufffd" not in decoded:
            return decoded

    return raw.decode("utf-8", errors="replace")


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


def source_url_candidates(url: str) -> tuple[str, ...]:
    """Retorna a URL original e, para Planalto, a variante com/sem www."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    candidates = [url]
    if host in PLANALTO_HOSTS:
        alternate_host = "planalto.gov.br" if host == "www.planalto.gov.br" else "www.planalto.gov.br"
        candidates.append(
            urlunsplit((parsed.scheme, alternate_host, parsed.path, parsed.query, parsed.fragment))
        )
    return tuple(dict.fromkeys(candidates))


def _is_probable_legislation_response(html: str, source: Source) -> bool:
    """Evita aceitar página de bloqueio/intersticial como se fosse uma lei válida."""
    if not html or len(html.strip()) < 100:
        return False
    return bool(extract_articles(html, source))


async def _fetch_html(client: httpx.AsyncClient, source: Source) -> str:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.planalto.gov.br/",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
    }
    errors: list[str] = []

    for url in source_url_candidates(source.url):
        for attempt in range(3):
            try:
                response = await client.get(url, headers=headers)
                status = response.status_code
                if status in RETRYABLE_STATUS_CODES and attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                response.raise_for_status()
                html = _decode_html_response(response)
                if not _is_probable_legislation_response(html, source):
                    errors.append(f"{url} -> resposta sem artigos reconhecíveis")
                    break
                return html
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                errors.append(f"{url} -> HTTP {status}")
                if status not in RETRYABLE_STATUS_CODES:
                    break
            except httpx.HTTPError as exc:
                errors.append(f"{url} -> {exc.__class__.__name__}: {exc}")
                break

    detail = "; ".join(errors[-8:]) or "resposta vazia"
    raise RuntimeError(f"Não foi possível consultar a legislação oficial: {detail}")


def extract_articles(html: str, source: Source) -> list[Device]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "del", "s", "strike"]):
        node.decompose()
    for node in soup.find_all(style=re.compile(r"line-through", re.IGNORECASE)):
        node.decompose()

    text = soup.get_text("\n", strip=False).replace("\xa0", " ")
    text = "\n".join(
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
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
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        html = await _fetch_html(client, source)
    return extract_articles(html, source), datetime.now(timezone.utc)
