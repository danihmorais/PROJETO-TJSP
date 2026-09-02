from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape

from .config import Source
from .legislation import Device


@dataclass(frozen=True)
class CompilationEntry:
    source: Source
    devices: list[Device]
    consulted_at: datetime
    error: str | None = None


UNIT_RE = re.compile(
    r"^(§\s*\d+[º°]?\s*[—–-]?|Parágrafo\s+único\.?\s*[—–-]?|"
    r"[IVXLCDM]{1,8}\s*[.)—–-]\s+|[a-z]\s*[.)—–-]\s+)",
    re.IGNORECASE,
)
INLINE_UNIT_RE = re.compile(
    r"(?=\s+(?:§\s*\d+[º°]?\s*[—–-]?|Parágrafo\s+único\.?\s*[—–-]?|"
    r"[IVXLCDM]{1,8}\s*[.)—–-]\s+|[a-z]\s*[.)—–-]\s+))",
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


def _split_line(line: str) -> list[str]:
    """Split multiple legal units only when an explicit unit marker exists."""
    parts = [part.strip() for part in INLINE_UNIT_RE.split(line) if part.strip()]
    return parts or [line.strip()]


def parse_legal_units(device: Device) -> list[tuple[str, str | None, str]]:
    """Organiza o dispositivo sem alterar sua redação substantiva."""
    heading = re.compile(
        rf"^Art(?:igo)?\.?\s*{re.escape(device.number)}[º°]?\s*(?:[—–-]\s*)?",
        re.IGNORECASE,
    )
    text = heading.sub("", device.text.strip(), count=1).strip()
    if not text:
        return []

    units: list[tuple[str, str | None, str]] = []
    current_kind = "caput"
    current_label: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        body = _clean_inline(" ".join(current_lines))
        if body:
            units.append((current_kind, current_label, body))

    for raw_line in text.splitlines():
        line = _clean_inline(raw_line)
        if not line:
            continue
        for chunk in _split_line(line):
            match = UNIT_RE.match(chunk)
            if match:
                flush()
                current_kind = _unit_kind(match.group(1))
                current_label = _unit_label(match.group(1))
                current_lines = [chunk[match.end():].strip()]
            else:
                current_lines.append(chunk)

    flush()
    return units


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower(), flags=re.IGNORECASE).strip("-")


def _article_html(device: Device) -> str:
    parts: list[str] = []
    for kind, label, body in parse_legal_units(device):
        if kind == "caput":
            parts.append(f"<div class='caput'>{escape(body)}</div>")
            continue
        parts.append(
            f"<div class='legal-unit {kind}'>"
            f"<span class='unit-marker'>{escape(label or '')}</span>"
            f"<div class='unit-text'>{escape(body)}</div>"
            f"</div>"
        )
    return "".join(parts) or f"<div class='caput'>{escape(device.text)}</div>"


def _caput_preview(device: Device, limit: int = 150) -> str:
    units = parse_legal_units(device)
    text = next((body for kind, _label, body in units if kind == "caput"), device.text)
    text = _clean_inline(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


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
        for device in entry.devices:
            lines += [f"#### Art. {device.number}", ""]
            for kind, label, body in parse_legal_units(device):
                lines += [f"**{label}** {body}" if label else body, ""]
    return "\n".join(lines).strip() + "\n"


def render_html(entries: list[CompilationEntry], generated_at: datetime) -> str:
    body: list[str] = []
    toc: list[str] = []
    current_subject: str | None = None
    total_articles = 0
    total_laws = 0

    for entry in entries:
        if entry.source.subject != current_subject:
            if current_subject is not None:
                body.append("</section>")
                toc.append("</div>")
            current_subject = entry.source.subject
            body.append(
                f"<section class='subject' id='subject-{_slug(current_subject)}'>"
                f"<div class='subject-heading'><span class='eyebrow'>MATÉRIA</span>"
                f"<h2>{escape(current_subject)}</h2></div>"
            )
            toc.append(
                f"<div class='toc-subject'><div class='toc-subject-title'>{escape(current_subject)}</div>"
            )

        total_laws += 1
        law_id = f"law-{total_laws}"
        body.append(f"<section class='law' id='{law_id}'>")
        body.append(
            f"<header class='law-header'><div><span class='eyebrow'>LEGISLAÇÃO</span>"
            f"<h3>{escape(entry.source.title)}</h3></div>"
            f"<a class='source-link' href='{escape(entry.source.url, quote=True)}' target='_blank' rel='noopener'>"
            f"Fonte oficial ↗</a></header>"
        )

        if entry.error:
            body.append(
                f"<div class='error-box'><strong>Fonte indisponível.</strong>"
                f"<span>{escape(entry.error)}</span></div>"
            )
            toc.append(
                f"<a class='toc-law error-link' href='#{law_id}'>{escape(entry.source.title)}</a>"
            )
            body.append("</section>")
            continue

        total_articles += len(entry.devices)
        body.append(
            f"<div class='law-meta'><span>{len(entry.devices)} artigos selecionados</span>"
            f"<span>Consulta: {entry.consulted_at.astimezone().strftime('%d/%m/%Y %H:%M:%S')}</span></div>"
        )

        article_links: list[str] = []
        if entry.devices:
            quick_items: list[str] = []
            for device in entry.devices:
                article_id = f"art-{_slug(entry.source.key)}-{_slug(device.number)}"
                preview = escape(_caput_preview(device))
                quick_items.append(
                    f"<a class='quick-item' href='#{article_id}'><strong>Art. {escape(device.number)}</strong>"
                    f"<span>{preview}</span></a>"
                )
                article_links.append(
                    f"<a href='#{article_id}' data-article-link='{article_id}'>Art. {escape(device.number)}</a>"
                )

            body.append(
                "<details class='quick-map'><summary>Visão rápida dos artigos</summary>"
                f"<div class='quick-grid'>{''.join(quick_items)}</div></details>"
            )

        for device in entry.devices:
            article_id = f"art-{_slug(entry.source.key)}-{_slug(device.number)}"
            search_blob = _clean_inline(
                f"{entry.source.subject} {entry.source.title} artigo art. {device.number} {device.text}"
            ).lower()
            body.append(
                f"<article class='article-card' id='{article_id}' data-search='{escape(search_blob, quote=True)}'>"
                f"<div class='article-top'><h4>Art. {escape(device.number)}</h4>"
                f"<button class='copy-link' type='button' onclick=\"copyArticle('{article_id}')\">Copiar link</button></div>"
                f"{_article_html(device)}</article>"
            )

        toc.append(
            f"<details class='toc-law' open><summary>{escape(entry.source.title)} "
            f"<small>{len(entry.devices)}</small></summary>"
            f"<div class='toc-articles'>{''.join(article_links)}</div></details>"
        )
        body.append("</section>")

    if current_subject is not None:
        body.append("</section>")
        toc.append("</div>")

    generated = generated_at.astimezone().strftime("%d/%m/%Y %H:%M:%S %z")
    sidebar_html = "".join(toc)

    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Lei seca — Compilado Legislativo TJSP</title>
<style>
:root{{--bg:#f3f4f6;--surface:#fff;--surface2:#f7f8fa;--text:#20242a;--muted:#68717d;--line:#dfe3e8;--accent:#17385f;--accent-soft:#e8eef6;--mark:#fff1a8;--danger:#8b2c2c;--shadow:0 2px 12px rgba(20,28,40,.05)}}
:root.dark{{--bg:#17191d;--surface:#202328;--surface2:#282c32;--text:#eceff3;--muted:#a7afb9;--line:#373d45;--accent:#9dbce2;--accent-soft:#2b3542;--mark:#665c26;--danger:#ef9b9b;--shadow:none}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}button,input{{font:inherit}}a{{color:inherit}}
.app{{display:grid;grid-template-columns:310px minmax(0,1fr);min-height:100vh}}.sidebar{{position:sticky;top:0;height:100vh;overflow:auto;background:var(--surface);border-right:1px solid var(--line);padding:18px 14px;z-index:10}}.brand{{padding:4px 10px 16px;border-bottom:1px solid var(--line);margin-bottom:12px}}.brand strong{{display:block;font-size:18px;letter-spacing:-.02em}}.brand span{{display:block;color:var(--muted);font-size:11px;margin-top:4px}}.toc-title{{font-size:10px;font-weight:900;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);padding:8px 10px}}.toc-subject{{margin-bottom:10px}}.toc-subject-title{{font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);padding:8px 10px 4px}}.toc-law{{display:block;margin:2px 0;color:var(--text);font-size:12px;text-decoration:none;border-radius:7px}}details.toc-law{{padding:0}}details.toc-law summary{{list-style:none;cursor:pointer;padding:8px 10px;font-weight:650}}details.toc-law summary::-webkit-details-marker{{display:none}}.toc-law summary small{{float:right;color:var(--muted);font-weight:500}}.toc-law:hover,.toc-articles a:hover{{background:var(--surface2)}}.toc-articles{{display:flex;flex-wrap:wrap;gap:4px;padding:1px 8px 8px 18px}}.toc-articles a{{padding:4px 6px;border-radius:5px;background:var(--surface2);text-decoration:none;font-size:11px}}.error-link{{color:var(--danger)}}
.main{{min-width:0}}.hero{{background:linear-gradient(180deg,var(--surface),var(--bg));border-bottom:1px solid var(--line);padding:36px clamp(20px,4vw,58px) 24px}}.hero-inner{{max-width:1180px;margin:auto}}.eyebrow{{font-size:10px;font-weight:900;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}.hero h1{{font-size:clamp(25px,3vw,38px);letter-spacing:-.035em;margin:5px 0 8px}}.hero p{{color:var(--muted);font-size:14px;max-width:860px;margin:0;line-height:1.55}}.generated{{margin-top:7px!important;font-size:11px!important}}
.toolbar{{position:sticky;top:0;z-index:8;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:11px clamp(20px,4vw,58px)}}.toolbar-inner{{max-width:1180px;margin:auto;display:flex;align-items:center;gap:7px;flex-wrap:wrap}}.search{{flex:1 1 390px}}.search input{{width:100%;padding:10px 12px;background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:9px;outline:0}}.search input:focus{{border-color:#829bbb;box-shadow:0 0 0 3px var(--accent-soft)}}.tool-btn{{padding:9px 11px;background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:8px;cursor:pointer}}.tool-btn:hover{{background:var(--surface2)}}.stats{{font-size:11px;color:var(--muted);margin-left:auto;white-space:nowrap}}
.content{{max-width:1180px;margin:auto;padding:7px clamp(20px,4vw,58px) 70px}}.subject{{margin-top:32px}}.subject-heading h2{{font-size:21px;margin:4px 0 14px;letter-spacing:-.015em}}.law{{margin:18px 0 30px}}.law-header{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:6px}}.law-header h3{{font-size:20px;letter-spacing:-.015em;margin:3px 0 0}}.source-link{{font-size:11px;text-decoration:none;color:var(--accent);white-space:nowrap}}.law-meta{{display:flex;gap:13px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin-bottom:11px}}.law-meta span+span::before{{content:'•';margin-right:13px}}
.quick-map{{border:1px solid var(--line);border-radius:9px;background:var(--surface);overflow:hidden;margin:0 0 12px}}.quick-map summary{{list-style:none;cursor:pointer;padding:10px 12px;font-size:11px;font-weight:850;color:var(--accent)}}.quick-map summary::-webkit-details-marker{{display:none}}.quick-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1px;background:var(--line);border-top:1px solid var(--line)}}.quick-item{{display:block;padding:9px 11px;background:var(--surface2);text-decoration:none;min-width:0}}.quick-item:hover{{background:var(--accent-soft)}}.quick-item strong{{display:block;font-size:11px;color:var(--accent);margin-bottom:3px}}.quick-item span{{display:block;color:var(--muted);font:12px/1.45 Georgia,"Times New Roman",serif}}
.article-card{{background:var(--surface);border:1px solid var(--line);border-radius:9px;margin:8px 0;padding:16px 18px;box-shadow:var(--shadow);scroll-margin-top:70px}}.article-card.hidden{{display:none}}.article-card.match{{box-shadow:0 0 0 3px var(--accent-soft)}}.article-top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}}.article-top h4{{font-size:14px;color:var(--accent);margin:0;letter-spacing:.01em}}.copy-link{{background:transparent;border:0;color:var(--muted);font-size:11px;padding:3px 5px;border-radius:5px;cursor:pointer}}.copy-link:hover{{background:var(--surface2);color:var(--text)}}.caput{{font:17px/1.72 Georgia,"Times New Roman",serif;padding:2px 0 9px}}.legal-unit{{display:grid;grid-template-columns:82px minmax(0,1fr);gap:12px;border-top:1px solid var(--line);padding:9px 0;font:16px/1.68 Georgia,"Times New Roman",serif}}.legal-unit.inciso{{padding-left:8px}}.legal-unit.alinea{{grid-template-columns:64px minmax(0,1fr);padding-left:30px}}.unit-marker{{font:700 11px/1.3 Inter,ui-sans-serif,system-ui,sans-serif;color:var(--accent);padding:6px 7px;background:var(--accent-soft);border-radius:5px;align-self:start;text-align:center;white-space:normal}}.unit-text{{min-width:0}}.error-box{{border:1px solid #e1baba;color:var(--danger);background:color-mix(in srgb,var(--danger) 6%,var(--surface));padding:12px;border-radius:8px;display:flex;flex-direction:column;gap:3px;font-size:12px}}
.no-results{{display:none;margin:28px 0;padding:24px;background:var(--surface);border:1px dashed var(--line);border-radius:9px;text-align:center;color:var(--muted)}}.focus .sidebar{{display:none}}.focus .app{{grid-template-columns:1fr}}.focus .article-card:not(.match){{opacity:.55}}.compact .article-card{{padding:11px 14px;margin:5px 0}}.compact .caput{{font-size:15px;line-height:1.55;padding-bottom:6px}}.compact .legal-unit{{font-size:14px;line-height:1.5;padding:6px 0}}
.footer-tools{{position:fixed;right:18px;bottom:16px;z-index:20;display:flex;gap:6px}}.footer-tools button{{padding:8px 10px;background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);cursor:pointer}}
@media(max-width:900px){{.app{{grid-template-columns:1fr}}.sidebar{{display:none;position:fixed;left:0;top:0;width:min(320px,88vw);box-shadow:8px 0 28px rgba(0,0,0,.15)}}body.menu-open .sidebar{{display:block}}.stats{{width:100%;margin-left:0}}.law-header{{align-items:start}}}}
@media print{{body{{background:#fff}}.sidebar,.toolbar,.footer-tools,.quick-map,.copy-link,.source-link{{display:none!important}}.hero{{padding:0 0 15px;background:#fff;border:0}}.content{{padding:0}}.subject{{break-before:page}}.law{{break-inside:auto}}.article-card{{box-shadow:none;border:0;border-top:1px solid #ddd;border-radius:0;break-inside:avoid}}}}
</style>
</head>
<body>
<div class='app'>
<aside class='sidebar' id='sidebar'>
  <div class='brand'><strong>Compilado TJSP</strong><span>Lei seca para estudo</span></div>
  <div class='toc-title'>Sumário</div>
  {sidebar_html}
</aside>
<main class='main'>
<section class='hero'><div class='hero-inner'>
  <span class='eyebrow'>LEITURA LEGISLATIVA</span>
  <h1>Compilado de Lei Seca</h1>
  <p>Texto normativo organizado por matéria, legislação e artigo. A formatação facilita a leitura e a revisão, sem substituir a fonte oficial.</p>
  <p class='generated'>Gerado em {escape(generated)}</p>
</div></section>
<div class='toolbar'><div class='toolbar-inner'>
  <div class='search'><input id='search' type='search' autocomplete='off' placeholder='Buscar artigo, expressão ou legislação...'></div>
  <button class='tool-btn' type='button' onclick='toggleMenu()'>Sumário</button>
  <button class='tool-btn' type='button' onclick='toggleClass("compact")'>Compacta</button>
  <button class='tool-btn' type='button' onclick='toggleClass("focus")'>Foco</button>
  <button class='tool-btn' type='button' onclick='toggleTheme()'>Tema</button>
  <div class='stats'><span id='stats'>{total_articles} artigos · {total_laws} legislações</span></div>
</div></div>
<div class='content' id='content'>
{''.join(body)}
<div class='no-results' id='noResults'>Nenhum artigo corresponde à busca.</div>
</div>
</main>
</div>
<div class='footer-tools'><button type='button' onclick='window.scrollTo({{top:0,behavior:"smooth"}})' title='Voltar ao topo'>↑ Topo</button></div>
<script>
const root=document.documentElement;
const body=document.body;
const search=document.getElementById('search');
const noResults=document.getElementById('noResults');
const articles=[...document.querySelectorAll('.article-card')];
const laws=[...document.querySelectorAll('.law')];
const subjects=[...document.querySelectorAll('.subject')];
function updateSearch(){{
  const q=search.value.trim().toLowerCase();
  let visible=0;
  laws.forEach(law=>{{
    const lawText=law.textContent.toLowerCase();
    let lawVisible=false;
    law.querySelectorAll('.article-card').forEach(article=>{{
      const ok=!q || lawText.includes(q) || article.dataset.search.includes(q);
      article.classList.toggle('hidden',!ok);
      article.classList.toggle('match',Boolean(q&&ok));
      if(ok){{visible++;lawVisible=true;}}
    }});
    law.style.display=lawVisible?'':'none';
  }});
  subjects.forEach(subject=>{{subject.style.display=[...subject.querySelectorAll('.law')].some(x=>x.style.display!=='none')?'':'none';}});
  noResults.style.display=(q&&visible===0)?'block':'none';
  document.getElementById('stats').textContent=q?(visible+' resultados'):("{total_articles} artigos · {total_laws} legislações");
}}
search.addEventListener('input',updateSearch);
document.addEventListener('keydown',e=>{{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){{e.preventDefault();search.focus();search.select();}}}});
function toggleClass(name){{body.classList.toggle(name);localStorage.setItem('tjsp-'+name,body.classList.contains(name)?'1':'0');}}
function toggleTheme(){{root.classList.toggle('dark');localStorage.setItem('tjsp-dark',root.classList.contains('dark')?'1':'0');}}
function toggleMenu(){{body.classList.toggle('menu-open');}}
function copyArticle(id){{const url=location.href.split('#')[0]+'#'+id;navigator.clipboard?.writeText(url).then(()=>{{}});location.hash=id;}}
['compact','focus'].forEach(n=>{{if(localStorage.getItem('tjsp-'+n)==='1')body.classList.add(n);}});
if(localStorage.getItem('tjsp-dark')==='1')root.classList.add('dark');
document.querySelectorAll('.toc-articles a,.quick-item').forEach(a=>a.addEventListener('click',()=>body.classList.remove('menu-open')));
</script>
</body>
</html>"""
