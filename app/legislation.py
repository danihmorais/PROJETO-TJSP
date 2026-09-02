from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from .config import Source

ALTERATION_PATTERNS = [
    re.compile(r"\s*\(?\s*\[?Redação dada pela Lei[^\n\)]*\)?\s*", re.I),
    re.compile(r"\s*\(?\s*\[?Incluído pela Lei[^\n\)]*\)?\s*", re.I),
    re.compile(r"\s*\(?\s*\[?Revogado pela Lei[^\n\)]*\)?\s*", re.I),
    re.compile(r"\s*\(?\s*\[?Alterado pela Lei[^\n\)]*\)?\s*", re.I),
    re.compile(r"\s*\(?\s*\[?Vide Lei[^\n\)]*\)?\s*", re.I),
]

@dataclass
class Device:
    number: str
    text: str
    heading: str = ""


def clean_text(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)
    for pattern in ALTERATION_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_article_number(raw: str) -> str:
    return raw.lower().replace("º", "").replace("°", "").replace(" ", "")


def parse_range(spec: str) -> tuple[str, str]:
    if "-" in spec:
        return tuple(spec.split("-", 1))  # type: ignore[return-value]
    return spec, spec


def article_in_ranges(number: str, ranges: tuple[str, ...]) -> bool:
    m = re.match(r"(\d+)(?:-([a-z]))?$", normalize_article_number(number))
    if not m:
        return False
    n, suffix = int(m.group(1)), m.group(2) or ""
    for item in ranges:
        a, b = parse_range(item)
        ma = re.match(r"(\d+)(?:-([a-z]))?$", normalize_article_number(a))
        mb = re.match(r"(\d+)(?:-([a-z]))?$", normalize_article_number(b))
        if not ma or not mb:
            continue
        lo, hi = int(ma.group(1)), int(mb.group(1))
        if lo <= n <= hi:
            return True
    return False


def extract_articles(html: str, source: Source) -> list[Device]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    results: list[Device] = []
    # Textos legislativos oficiais do Planalto/ALSP usam parágrafos iniciados por Art.
    for node in soup.find_all(["p", "div", "li"]):
        raw = " ".join(node.stripped_strings)
        m = re.match(r"^Art\.?\s*(\d+(?:-?[A-Za-z])?)[º°]?\s*[—–-]?\s*(.*)$", raw, re.S)
        if not m:
            continue
        number = m.group(1)
        if source.article_ranges and not article_in_ranges(number, source.article_ranges):
            continue
        text = clean_text(raw)
        if text and not any(d.number == number for d in results):
            results.append(Device(number=number, text=text))
    return results


async def fetch_source(source: Source) -> tuple[list[Device], datetime]:
    headers = {"User-Agent": "PROJETO-TJSP/1.0 (estudo legislativo)"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(source.url)
        response.raise_for_status()
    fetched = datetime.now(timezone.utc)
    return extract_articles(response.text, source), fetched
