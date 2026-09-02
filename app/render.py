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
    r"(?m)^(§\s*\d+[º°]?\s*[—–-]?|Parágrafo único\.?\s*[—–-]?|[IVXLCDM]{1,8}\s*[.)—–-]\s+|[a-z]\s*[.)—–-]\s+)",
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
    value = marker.strip().replace("—", "").replace("–", "").rstrip("-.: ")
    return _clean_inline(value)


def parse_legal_units(device: Device) -> list[tuple[str, str | None, str]]:
    """Breaks an article into study-friendly units while retaining the verbatim text."""
    text = device.text.strip()
    heading = re.compile(
        rf"^Art\.?\s*{re.escape(device.number)}[º°]?\s*(?:[—–-]\s*)?",
        re.IGNORECASE,
    )
    text = heading.sub("", text, count=1).strip()
    if not text:
        return []

    raw_lines = [_clean_inline(line) for line in text.splitlines() if _clean_inline(line)]
    chunks: list[str] = []
    for line in raw_lines:
        pieces = INLINE_UNIT_RE.split(line)
        chunks.extend(piece.strip() for piece in pieces if piece.strip())

    units: list[tuple[str, str | None, str]] = []
    caput_parts: list[str] = []
    for chunk in chunks:
        match = UNIT_RE.match(chunk)
        if not match:
            if units and units[-1][0] != "caput":
                kind, label, body = units[-1]
                units[-1] = (kind, label, _clean_inline(f"{body} {chunk}"))
            else:
                caput_parts.append(chunk)
            continue
        if caput_parts:
            units.append(("caput", None, _clean_inline(" ".join(caput_parts))))
            caput_parts = []
        marker = match.group(1)
        units.append((_unit_kind(marker), _unit_label(marker), _clean_inline(chunk[match.end():])))
    if caput_parts:
        units.append(("caput", None, _clean_inline(" ".join(caput_parts))))
    return [(kind, label, body) for kind, label, body in units if body]


def render_markdown(entries: list[CompilationEntry], generated_at: datetime) -> str:
    lines = [
        "# COMPILADO LEGISLATIVO — PROJETO-TJSP",
        "",
        f"**Gerado em:** {generated_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}",
        "",
        "> Material organizado para estudo. A redação dos dispositivos é preservada; em caso de divergência, prevalece a fonte oficial indicada em cada norma.",
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
            for kind, label, body in parse_legal_units(device):
                prefix = f"**{label}** " if label else ""
                lines += [f"{prefix}{body}", ""]
    return "\n".join(lines).strip() + "\n"


def _slug(value: str) -> str:
    return quote(value, safe="").replace("%", "-")


def _render_article(device: Device) -> str:
    units = parse_legal_units(device)
    parts = []
    for kind, label, body in units:
        if kind == "caput":
            parts.append(f"<div class='caput'>{escape(body)}</div>")
            continue
        classes = f"legal-unit {kind}"
        label_html = f"<span class='unit-marker'>{escape(label or '')}</span>" if label else ""
        parts.append(f"<div class='{classes}'>{label_html}<div class='unit-text'>{escape(body)}</div></div>")
    if not parts:
        parts.append(f"<div class='caput'>{escape(device.text)}</div>")
    return "".join(parts)


def render_html(entries: list[CompilationEntry], generated_at: datetime) -> str:
    body: list[str] = []
    toc: list[str] = []
    current_subject = None
    total_articles = 0
    law_index = 0

    for entry in entries:
        law_index += 1
        if entry.source.subject != current_subject:
            if current_subject is not None:
                body.append("</section>")
            current_subject = entry.source.subject
            body.append(f"<section class='subject' id='subject-{_slug(current_subject)}'><div class='subject-heading'><span class='eyebrow'>MATÉRIA</span><h2>{escape(current_subject)}</h2></div>")
            toc.append(f"<div class='toc-subject'><div class='toc-subject-title'>{escape(current_subject)}</div>")
        law_id = f"law-{law_index}"
        body.append(f"<section class='law' id='{law_id}' data-law='{escape(entry.source.title, quote=True)}'>")
        body.append(
            f"<div class='law-header'><div><span class='eyebrow'>LEGISLAÇÃO</span><h3>{escape(entry.source.title)}</h3></div>"
            f"<a class='source-link' href='{escape(entry.source.url, quote=True)}' target='_blank' rel='noopener'>Fonte oficial ↗</a></div>"
        )
        if entry.error:
            body.append(f"<div class='error-box'><strong>Não foi possível consultar esta fonte.</strong><span>{escape(entry.error)}</span></div>")
            toc.append(f"<a href='#{law_id}' class='toc-law'>{escape(entry.source.title)} <small>erro</small></a>")
        else:
            total_articles += len(entry.devices)
            body.append(
                f"<div class='law-meta'><span>{len(entry.devices)} artigos</span><span>Consulta: {entry.consulted_at.astimezone().strftime('%d/%m/%Y %H:%M:%S')}</span></div>"
            )
            article_links = []
            for device in entry.devices:
                article_id = f"art-{_slug(entry.source.key)}-{_slug(device.number)}"
                search_blob = _clean_inline(f"{entry.source.title} Art. {device.number} {device.text}").lower()
                body.append(
                    f"<article class='article-card' id='{article_id}' data-search='{escape(search_blob, quote=True)}'>"
                    f"<div class='article-top'><h4>Art. {escape(device.number)}</h4><button class='copy-link' onclick=\"copyArticle('{article_id}')\" title='Copiar link deste artigo'>Copiar link</button></div>"
                    f"{_render_article(device)}"
                    f"</article>"
                )
                article_links.append(f"<a href='#{article_id}'>{escape(device.number)}</a>")
            toc.append(
                f"<details class='toc-law' open><summary>{escape(entry.source.title)} <small>{len(entry.devices)} artigos</small></summary>"
                f"<div class='toc-articles'>{''.join(article_links)}</div></details>"
            )
        body.append("</section>")
    if current_subject is not None:
        body.append("</section>")
        toc.append("</div>")

    generated = generated_at.astimezone().strftime("%d/%m/%Y %H:%M:%S %z")
    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Compilado Legislativo — TJSP</title>
<style>
:root{{--bg:#f5f6f8;--surface:#fff;--surface-2:#f8f9fb;--text:#20242b;--muted:#68707d;--line:#dfe3e8;--accent:#1d3557;--accent-2:#e8eef6;--mark:#fff6cf;--danger:#8e2a2a;--shadow:0 8px 24px rgba(20,28,40,.07)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}button,input{{font:inherit}}a{{color:inherit}}
.app{{display:grid;grid-template-columns:290px minmax(0,1fr);min-height:100vh}}.sidebar{{position:sticky;top:0;height:100vh;overflow:auto;padding:22px 16px;background:#fff;border-right:1px solid var(--line)}}
.brand{{padding:4px 10px 18px;border-bottom:1px solid var(--line);margin-bottom:14px}}.brand strong{{display:block;font-size:18px}}.brand span{{display:block;color:var(--muted);font-size:12px;margin-top:4px}}
.toc-title{{font-size:11px;font-weight:800;letter-spacing:.09em;color:var(--muted);padding:8px 10px}}.toc-subject{{margin-bottom:12px}}.toc-subject-title{{font-size:12px;font-weight:800;color:var(--accent);padding:6px 10px;text-transform:uppercase;letter-spacing:.06em}}.toc-law{{display:block;text-decoration:none;border-radius:8px;margin:2px 0;padding:8px 10px;color:#39414c;font-size:13px}}.toc-law:hover,.toc-articles a:hover{{background:var(--surface-2)}}details.toc-law{{padding:0}details.toc-law summary{{cursor:pointer;list-style:none;padding:8px 10px}}details.toc-law summary::-webkit-details-marker{{display:none}}.toc-law small{{color:var(--muted);float:right}}.toc-articles{{display:flex;flex-wrap:wrap;gap:4px;padding:0 8px 7px 18px}}.toc-articles a{{text-decoration:none;font-size:12px;padding:5px 6px;border-radius:6px;background:var(--surface-2)}}
.main{{min-width:0}}.hero{{padding:38px clamp(22px,4vw,60px) 26px;background:linear-gradient(180deg,#ffffff 0%,#f5f6f8 100%);border-bottom:1px solid var(--line)}}.hero-inner{{max-width:1180px;margin:0 auto}}.eyebrow{{display:block;font-size:10px;font-weight:900;letter-spacing:.12em;color:var(--muted);text-transform:uppercase}}.hero h1{{font-size:clamp(25px,3vw,38px);margin:5px 0 8px;letter-spacing:-.03em}}.hero p{{max-width:850px;margin:0;color:var(--muted)}}
.toolbar{{position:sticky;top:0;z-index:5;padding:13px clamp(22px,4vw,60px);background:rgba(245,246,248,.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}}.toolbar-inner{{max-width:1180px;margin:0 auto;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}.search{{flex:1 1 320px;position:relative}}.search input{{width:100%;padding:11px 13px;border:1px solid var(--line);border-radius:9px;background:#fff;outline:none}}.search input:focus{{border-color:#8aa0bb;box-shadow:0 0 0 3px #dfe8f4}}.tool-btn{{border:1px solid var(--line);background:#fff;border-radius:9px;padding:10px 12px;cursor:pointer;color:#3f4650}}.tool-btn:hover{{background:var(--surface-2)}}
.stats{{display:flex;gap:8px;align-items:center;margin-left:auto;color:var(--muted);font-size:12px}}.stat{{padding:8px 10px;background:#fff;border:1px solid var(--line);border-radius:999px}}.content{{max-width:1180px;margin:0 auto;padding:8px clamp(22px,4vw,60px) 70px}}.subject{{margin-top:36px}}.subject-heading h2{{font-size:22px;margin:3px 0 15px;letter-spacing:-.015em}}.law{{margin:18px 0 28px}}.law-header{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:8px}}.law-header h3{{margin:3px 0 0;font-size:20px}}.source-link{{font-size:12px;color:var(--accent);text-decoration:none;white-space:nowrap}}.law-meta{{display:flex;gap:13px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin-bottom:13px}}.law-meta span+span::before{{content:'•';margin-right:13px}}
.article-card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;margin:11px 0;padding:17px 19px;box-shadow:0 2px 8px rgba(20,28,40,.03);scroll-margin-top:75px}}.article-card.highlight{{box-shadow:0 0 0 3px #d8e3f0}}.article-top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:11px}}.article-top h4{{font-family:ui-sans-serif,system-ui,sans-serif;font-size:14px;margin:0;color:var(--accent)}}.copy-link{{border:0;background:transparent;color:var(--muted);font-size:11px;cursor:pointer;padding:3px 5px;border-radius:5px}}.copy-link:hover{{background:var(--surface-2);color:var(--text)}}
.caput{{font-family:Georgia,"Times New Roman",serif;font-size:17px;line-height:1.72;padding:2px 0 9px}}.legal-unit{{display:grid;grid-template-columns:84px minmax(0,1fr);gap:12px;padding:8px 0;border-top:1px solid #edf0f3;font-family:Georgia,"Times New Roman",serif;font-size:16px;line-height:1.67}}.unit-marker{{font-family:ui-sans-serif,system-ui,sans-serif;font-size:11px;font-weight:800;color:var(--accent);padding-top:4px;background:var(--accent-2);border-radius:5px;text-align:center;align-self:start;padding:4px 5px}.inciso .unit-marker{{letter-spacing:.03em}}.alinea{{grid-template-columns:30px minmax(0,1fr);padding-left:20px}.alinea .unit-marker{{background:transparent;padding-left:0}}.paragraph .unit-marker{{background:#f0f2f5;color:#4b5461}}.unit-text{{min-width:0}}
.error-box{{display:flex;flex-direction:column;gap:4px;padding:14px;border:1px solid #efd1d1;background:#fff6f6;color:var(--danger);border-radius:9px;font-size:13px}}.empty-search{{padding:36px;text-align:center;color:var(--muted);display:none}}
body.compact .article-card{{padding:12px 15px;margin:7px 0}}body.compact .caput,body.compact .legal-unit{{font-size:14px;line-height:1.52}}body.compact .legal-unit{{grid-template-columns:68px minmax(0,1fr);padding:5px 0}}body.focus .sidebar{{display:none}}body.focus .app{{display:block}}body.focus .content{{max-width:980px}}body.dark{{--bg:#101317;--surface:#181c21;--surface-2:#20252b;--text:#e9edf2;--muted:#9da7b3;--line:#303740;--accent:#bfd0e5;--accent-2:#273545;--mark:#3b361e}}body.dark .hero,body.dark .toolbar,body.dark .sidebar{{background:#14181d}}body.dark .article-card{{box-shadow:none}}body.dark .search input,body.dark .tool-btn,body.dark .stat{{background:var(--surface);color:var(--text)}}
@media(max-width:920px){{.app{{display:block}}.sidebar{{position:relative;height:auto;max-height:260px;border-right:0;border-bottom:1px solid var(--line)}}.toolbar{{top:0}}.stats{{margin-left:0}}}}@media(max-width:640px){{.hero{{padding-top:26px}}.law-header{{align-items:start;flex-direction:column;gap:5px}}.legal-unit{{grid-template-columns:1fr;gap:4px}}.alinea{{grid-template-columns:22px 1fr;padding-left:8px}}.unit-marker{{justify-self:start}}
}}@media print{{body{{background:#fff}}.sidebar,.toolbar,.copy-link{{display:none!important}}.app{{display:block}}.hero{{padding:0 0 12px;border:0}}.content{{padding:0;max-width:none}}.article-card{{box-shadow:none;break-inside:avoid;border:0;border-top:1px solid #ddd;border-radius:0;padding:14px 0}}.subject{{break-before:page}}}}
</style>
</head>
<body>
<div class='app'>
  <aside class='sidebar'>
    <div class='brand'><strong>PROJETO-TJSP</strong><span>Compilado para revisão e lei seca</span></div>
    <div class='toc-title'>ÍNDICE</div>
    {''.join(toc)}
  </aside>
  <main class='main'>
    <header class='hero'><div class='hero-inner'>
      <span class='eyebrow'>MATERIAL DE ESTUDO</span>
      <h1>Compilado Legislativo — TJSP</h1>
      <p>A lei seca permanece em primeiro plano. Os dispositivos foram apenas reorganizados visualmente para facilitar leitura, revisão e localização rápida de artigos.</p>
      <p style='margin-top:7px;font-size:12px'>Gerado em {escape(generated)} · {len(entries)} legislações · {total_articles} artigos localizados</p>
    </div></header>
    <div class='toolbar'><div class='toolbar-inner'>
      <div class='search'><input id='search' type='search' placeholder='Buscar na lei seca, artigo ou expressão...' oninput='filterArticles()'></div>
      <button class='tool-btn' onclick='toggleCompact()'>Leitura compacta</button>
      <button class='tool-btn' onclick='toggleFocus()'>Modo foco</button>
      <button class='tool-btn' onclick='toggleDark()'>Tema</button>
      <button class='tool-btn' onclick='expandAll(true)'>Abrir tudo</button>
      <button class='tool-btn' onclick='expandAll(false)'>Fechar índice</button>
      <div class='stats'><span class='stat' id='resultCount'>{total_articles} artigos</span></div>
    </div></div>
    <div class='content'>{''.join(body)}<div id='emptySearch' class='empty-search'>Nenhum artigo corresponde à busca.</div></div>
  </main>
</div>
<script>
function articles(){{return Array.from(document.querySelectorAll('.article-card'))}}
function filterArticles(){{const q=document.getElementById('search').value.trim().toLowerCase();let visible=0;articles().forEach(el=>{{const ok=!q||el.dataset.search.includes(q);el.style.display=ok?'':'none';if(ok)visible++}});document.getElementById('resultCount').textContent=visible+' artigos';document.getElementById('emptySearch').style.display=visible?'none':'block'}}
function toggleCompact(){{document.body.classList.toggle('compact')}}
function toggleFocus(){{document.body.classList.toggle('focus')}}
function toggleDark(){{document.body.classList.toggle('dark');try{{localStorage.setItem('tjsp-study-dark',document.body.classList.contains('dark'))}}catch{{}}}}
function expandAll(open){{document.querySelectorAll('details.toc-law').forEach(d=>d.open=open)}}
async function copyArticle(id){{const url=location.href.split('#')[0]+'#'+id;try{{await navigator.clipboard.writeText(url);const el=document.getElementById(id).querySelector('.copy-link');const old=el.textContent;el.textContent='Copiado';setTimeout(()=>el.textContent=old,1200)}}catch{{location.hash=id}}}}
try{{if(localStorage.getItem('tjsp-study-dark')==='true')document.body.classList.add('dark')}}catch{{}}
</script>
</body>
</html>"""
