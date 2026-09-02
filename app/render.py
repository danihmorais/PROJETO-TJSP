from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from urllib.parse import quote

from .config import Source
from .legislation import Device


@dataclass(frozen=True)
class CompilationEntry:
    source: Source
    devices: list[Device]
    consulted_at: datetime
    error: str | None = None


UNIT_RE = re.compile(
    r"^(§\s*\d+[º°]?\s*[—–-]?|Parágrafo único\.?\s*[—–-]?|[IVXLCDM]{1,8}\s*[.)—–-]\s+|[a-z]\s*[.)—–-]\s+)",
    re.IGNORECASE,
)
INLINE_UNIT_RE = re.compile(
    r"(?=\s+(?:§\s*\d+[º°]?|Parágrafo único\.?|[IVXLCDM]{1,8}\s*[.)—–-]\s+|[a-z]\s*[.)—–-]\s+))",
    re.IGNORECASE,
)


def _clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def _unit_kind(marker: str) -> str:
    marker = marker.strip()
    if marker.lower().startswith("parágrafo") or marker.startswith("§"):
        return "paragraph"
    if re.match(r"^[IVXLCDM]{1,8}\s*[.)—–-]", marker, re.IGNORECASE):
        return "inciso"
    if re.match(r"^[a-z]\s*[.)—–-]", marker, re.IGNORECASE):
        return "alinea"
    return "other"


def _unit_label(marker: str) -> str:
    return _clean_inline(marker.replace("—", "").replace("–", "").rstrip("-.: "))


def parse_legal_units(device: Device) -> list[tuple[str, str | None, str]]:
    """Organiza o dispositivo para leitura sem alterar sua redação substantiva."""
    text = device.text.strip()
    heading = re.compile(
        rf"^Art\.?\s*{re.escape(device.number)}[º°]?\s*(?:[—–-]\s*)?",
        re.IGNORECASE,
    )
    text = heading.sub("", text, count=1).strip()
    if not text:
        return []

    chunks: list[str] = []
    for line in (_clean_inline(v) for v in text.splitlines()):
        if line:
            chunks.extend(piece.strip() for piece in INLINE_UNIT_RE.split(line) if piece.strip())

    units: list[tuple[str, str | None, str]] = []
    pending_caput: list[str] = []
    for chunk in chunks:
        match = UNIT_RE.match(chunk)
        if not match:
            if units and units[-1][0] != "caput":
                kind, label, body = units[-1]
                units[-1] = (kind, label, _clean_inline(f"{body} {chunk}"))
            else:
                pending_caput.append(chunk)
            continue
        if pending_caput:
            units.append(("caput", None, _clean_inline(" ".join(pending_caput))))
            pending_caput = []
        marker = match.group(1)
        units.append((_unit_kind(marker), _unit_label(marker), _clean_inline(chunk[match.end():])))
    if pending_caput:
        units.append(("caput", None, _clean_inline(" ".join(pending_caput))))
    return [(kind, label, body) for kind, label, body in units if body]


def _slug(value: str) -> str:
    return quote(value, safe="").replace("%", "-")


def _article_html(device: Device) -> str:
    parts: list[str] = []
    for kind, label, body in parse_legal_units(device):
        if kind == "caput":
            parts.append(f"<div class='caput'>{escape(body)}</div>")
            continue
        marker = f"<span class='unit-marker'>{escape(label or '')}</span>" if label else ""
        parts.append(
            f"<div class='legal-unit {kind}'>{marker}<div class='unit-text'>{escape(body)}</div></div>"
        )
    return "".join(parts) or f"<div class='caput'>{escape(device.text)}</div>"


def render_markdown(entries: list[CompilationEntry], generated_at: datetime) -> str:
    lines = [
        "# COMPILADO LEGISLATIVO — PROJETO-TJSP",
        "",
        f"**Gerado em:** {generated_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}",
        "",
        "> Material organizado para estudo. A redação dos dispositivos é preservada; em caso de divergência, prevalece a fonte oficial.",
        "",
    ]
    current_subject = None
    for entry in entries:
        if entry.source.subject != current_subject:
            current_subject = entry.source.subject
            lines += [f"## {current_subject}", ""]
        lines += [f"### {entry.source.title}", "", f"**Fonte oficial:** {entry.source.url}", ""]
        if entry.error:
            lines += [f"> **Falha na consulta:** {entry.error}", ""]
            continue
        lines += [
            f"_Consulta realizada em {entry.consulted_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')} — {len(entry.devices)} artigos encontrados._",
            "",
        ]
        for device in entry.devices:
            lines += [f"#### Art. {device.number}", ""]
            for _kind, label, body in parse_legal_units(device):
                prefix = f"**{label}** " if label else ""
                lines += [f"{prefix}{body}", ""]
    return "\n".join(lines).strip() + "\n"


def render_html(entries: list[CompilationEntry], generated_at: datetime) -> str:
    body: list[str] = []
    toc: list[str] = []
    current_subject = None
    total_articles = 0
    law_index = 0

    for entry in entries:
        if entry.source.subject != current_subject:
            current_subject = entry.source.subject
            body.append(
                f"<section class='subject' id='subject-{_slug(current_subject)}'>"
                f"<div class='subject-heading'><span class='eyebrow'>MATÉRIA</span><h2>{escape(current_subject)}</h2></div>"
            )
            toc.append(f"<div class='toc-subject-title'>{escape(current_subject)}</div>")

        law_index += 1
        law_id = f"law-{law_index}"
        body.append(f"<section class='law' id='{law_id}'>")
        body.append(
            f"<div class='law-header'><div><span class='eyebrow'>LEGISLAÇÃO</span>"
            f"<h3>{escape(entry.source.title)}</h3></div>"
            f"<a class='source-link' href='{escape(entry.source.url, quote=True)}' target='_blank' rel='noopener'>Fonte oficial ↗</a></div>"
        )

        if entry.error:
            body.append(
                f"<div class='error-box'><strong>Não foi possível consultar esta fonte.</strong>"
                f"<span>{escape(entry.error)}</span></div>"
            )
            toc.append(f"<a href='#{law_id}' class='toc-law'>{escape(entry.source.title)} <small>erro</small></a>")
        else:
            total_articles += len(entry.devices)
            body.append(
                f"<div class='law-meta'><span>{len(entry.devices)} artigos</span>"
                f"<span>Consulta: {entry.consulted_at.astimezone().strftime('%d/%m/%Y %H:%M:%S')}</span></div>"
            )
            article_links: list[str] = []
            for device in entry.devices:
                article_id = f"art-{_slug(entry.source.key)}-{_slug(device.number)}"
                search_blob = _clean_inline(f"{entry.source.title} Art. {device.number} {device.text}").lower()
                body.append(
                    f"<article class='article-card' id='{article_id}' data-search='{escape(search_blob, quote=True)}'>"
                    f"<div class='article-top'><h4>Art. {escape(device.number)}</h4>"
                    f"<button class='copy-link' onclick=\"copyArticle('{article_id}')\">Copiar link</button></div>"
                    f"{_article_html(device)}</article>"
                )
                article_links.append(f"<a href='#{article_id}'>{escape(device.number)}</a>")
            toc.append(
                f"<details class='toc-law' open><summary>{escape(entry.source.title)} "
                f"<small>{len(entry.devices)} artigos</small></summary>"
                f"<div class='toc-articles'>{''.join(article_links)}</div></details>"
            )
        body.append("</section>")

    if current_subject is not None:
        body.append("</section>")

    template = """<!doctype html>
<html lang='pt-BR'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Compilado Legislativo — TJSP</title>
<style>
:root{--bg:#f5f6f8;--surface:#fff;--surface2:#f8f9fb;--text:#20242b;--muted:#68707d;--line:#dfe3e8;--accent:#1d3557;--accent2:#e8eef6;--danger:#8e2a2a}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}.app{display:grid;grid-template-columns:285px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;overflow:auto;background:#fff;border-right:1px solid var(--line);padding:20px 15px}.brand{padding:4px 10px 18px;border-bottom:1px solid var(--line);margin-bottom:12px}.brand strong{font-size:18px}.brand span{display:block;color:var(--muted);font-size:11px;margin-top:4px}.toc-title,.eyebrow{font-size:10px;font-weight:900;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}.toc-title{padding:8px 10px}.toc-subject-title{font-size:11px;font-weight:850;color:var(--accent);padding:9px 10px 5px}.toc-law{display:block;text-decoration:none;border-radius:8px;padding:7px 10px;color:#39414c;font-size:12px}.toc-law:hover,.toc-articles a:hover{background:var(--surface2)}details.toc-law{padding:0}details.toc-law summary{cursor:pointer;list-style:none;padding:7px 10px}details.toc-law summary::-webkit-details-marker{display:none}.toc-law small{float:right;color:var(--muted)}.toc-articles{display:flex;flex-wrap:wrap;gap:4px;padding:0 8px 8px 18px}.toc-articles a{text-decoration:none;font-size:11px;background:var(--surface2);padding:4px 6px;border-radius:5px}.main{min-width:0}.hero{padding:38px clamp(22px,4vw,60px) 25px;background:linear-gradient(#fff,var(--bg));border-bottom:1px solid var(--line)}.hero-inner,.content{max-width:1180px;margin:auto}.hero h1{font-size:clamp(25px,3vw,38px);margin:4px 0 8px;letter-spacing:-.03em}.hero p{max-width:850px;margin:0;color:var(--muted);font-size:14px}.hero .generated{margin-top:7px;font-size:11px}.toolbar{position:sticky;top:0;z-index:5;background:rgba(245,246,248,.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:12px clamp(22px,4vw,60px)}.toolbar-inner{max-width:1180px;margin:auto;display:flex;gap:8px;flex-wrap:wrap;align-items:center}.search{flex:1 1 320px}.search input{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:9px;outline:0}.tool-btn{border:1px solid var(--line);background:#fff;border-radius:9px;padding:9px 11px;color:#3f4650;cursor:pointer}.stats{margin-left:auto;font-size:11px;color:var(--muted)}.stat{background:#fff;border:1px solid var(--line);border-radius:999px;padding:7px 9px}.content{padding:8px clamp(22px,4vw,60px) 60px}.subject{margin-top:35px}.subject-heading h2{font-size:21px;margin:4px 0 14px}.law{margin:18px 0 28px}.law-header{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:6px}.law-header h3{margin:4px 0 0;font-size:20px}.source-link{font-size:12px;color:var(--accent);text-decoration:none}.law-meta{font-size:11px;color:var(--muted);display:flex;gap:14px;margin-bottom:12px}.article-card{background:var(--surface);border:1px solid var(--line);border-radius:11px;margin:9px 0;padding:16px 18px;scroll-margin-top:70px}.article-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.article-top h4{font-size:14px;color:var(--accent);margin:0}.copy-link{background:transparent;border:0;color:var(--muted);font-size:11px;cursor:pointer}.caput{font-family:Georgia,"Times New Roman",serif;font-size:17px;line-height:1.72;padding-bottom:7px}.legal-unit{display:grid;grid-template-columns:82px minmax(0,1fr);gap:12px;border-top:1px solid #edf0f3;padding:8px 0;font-family:Georgia,"Times New Roman",serif;font-size:16px;line-height:1.65}.unit-marker{font-family:system-ui,sans-serif;font-size:11px;font-weight:800;background:var(--accent2);color:var(--accent);border-radius:5px;padding:4px 5px;height:max-content;text-align:center}.alinea{grid-template-columns:28px minmax(0,1fr);padding-left:18px}.alinea .unit-marker{background:transparent;padding-left:0}.error-box{display:flex;flex-direction:column;gap:4px;padding:13px;border:1px solid #efd1d1;background:#fff6f6;color:var(--danger);border-radius:9px;font-size:13px}.empty-search{text-align:center;color:var(--muted);padding:40px;display:none}body.compact .article-card{padding:11px 14px;margin:6px 0}body.compact .caput,body.compact .legal-unit{font-size:14px;line-height:1.5}body.focus .sidebar{display:none}body.focus .app{display:block}body.focus .content{max-width:980px}body.dark{--bg:#101317;--surface:#181c21;--surface2:#20252b;--text:#e9edf2;--muted:#9da7b3;--line:#303740;--accent:#bfd0e5;--accent2:#273545}body.dark .sidebar,body.dark .hero,body.dark .toolbar{background:#14181d}body.dark .search input,body.dark .tool-btn,body.dark .stat{background:var(--surface);color:var(--text)}@media(max-width:900px){.app{display:block}.sidebar{position:relative;height:auto;max-height:260px;border-right:0;border-bottom:1px solid var(--line)}.stats{margin-left:0}.law-header{align-items:start;flex-direction:column;gap:5px}}@media(max-width:620px){.content,.hero,.toolbar{padding-left:14px;padding-right:14px}.legal-unit{grid-template-columns:1fr}.alinea{grid-template-columns:22px 1fr;padding-left:8px}.unit-marker{justify-self:start}}@media print{.sidebar,.toolbar,.copy-link{display:none!important}.app{display:block}.hero{padding:0 0 12px;border:0}.content{padding:0}.article-card{border:0;border-top:1px solid #ddd;border-radius:0;break-inside:avoid}.subject{break-before:page}}
</style>
</head>
<body>
<div class='app'>
<aside class='sidebar'><div class='brand'><strong>PROJETO-TJSP</strong><span>Lei seca para revisão</span></div><div class='toc-title'>ÍNDICE</div>__TOC__</aside>
<main class='main'>
<header class='hero'><div class='hero-inner'><span class='eyebrow'>MATERIAL DE ESTUDO</span><h1>Compilado Legislativo — TJSP</h1><p>A redação normativa permanece em primeiro plano. A estrutura abaixo foi apenas reorganizada para facilitar leitura, revisão, busca e localização de artigos.</p><p class='generated'>Gerado em __GENERATED__ · __LAWS__ legislações · __ARTICLES__ artigos localizados</p></div></header>
<div class='toolbar'><div class='toolbar-inner'><div class='search'><input id='search' type='search' placeholder='Buscar na lei seca, artigo ou expressão...' oninput='filterArticles()'></div><button class='tool-btn' onclick='toggleCompact()'>Leitura compacta</button><button class='tool-btn' onclick='toggleFocus()'>Modo foco</button><button class='tool-btn' onclick='toggleDark()'>Tema</button><button class='tool-btn' onclick='expandAll(true)'>Abrir índice</button><button class='tool-btn' onclick='expandAll(false)'>Fechar índice</button><div class='stats'><span class='stat' id='resultCount'>__ARTICLES__ artigos</span></div></div></div>
<div class='content'>__BODY__<div id='emptySearch' class='empty-search'>Nenhum artigo corresponde à busca.</div></div>
</main></div>
<script>
function articles(){return Array.from(document.querySelectorAll('.article-card'))}
function filterArticles(){const q=document.getElementById('search').value.trim().toLowerCase();let visible=0;articles().forEach(el=>{const ok=!q||el.dataset.search.includes(q);el.style.display=ok?'':'none';if(ok)visible++});document.getElementById('resultCount').textContent=visible+' artigos';document.getElementById('emptySearch').style.display=visible?'none':'block'}
function toggleCompact(){document.body.classList.toggle('compact')}
function toggleFocus(){document.body.classList.toggle('focus')}
function toggleDark(){document.body.classList.toggle('dark');try{localStorage.setItem('tjsp-study-dark',document.body.classList.contains('dark'))}catch{}}
function expandAll(open){document.querySelectorAll('details.toc-law').forEach(d=>d.open=open)}
async function copyArticle(id){const url=location.href.split('#')[0]+'#'+id;try{await navigator.clipboard.writeText(url);const el=document.getElementById(id).querySelector('.copy-link');const old=el.textContent;el.textContent='Copiado';setTimeout(()=>el.textContent=old,1200)}catch{location.hash=id}}
try{if(localStorage.getItem('tjsp-study-dark')==='true')document.body.classList.add('dark')}catch{}
</script>
</body></html>"""

    return (
        template.replace("__TOC__", "".join(toc))
        .replace("__BODY__", "".join(body))
        .replace("__GENERATED__", generated_at.astimezone().strftime("%d/%m/%Y %H:%M:%S %z"))
        .replace("__LAWS__", str(len(entries)))
        .replace("__ARTICLES__", str(total_articles))
    )
