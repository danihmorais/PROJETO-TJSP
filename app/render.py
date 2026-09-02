from __future__ import annotations

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


def render_markdown(entries: list[CompilationEntry], generated_at: datetime) -> str:
    lines = [
        "# COMPILADO LEGISLATIVO — PROJETO-TJSP",
        "",
        f"**Gerado em:** {generated_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}",
        "",
        "> Material organizado para estudo. Em caso de divergência, prevalece a fonte oficial indicada em cada norma.",
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
        lines += [f"_Consulta realizada em {entry.consulted_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}_", ""]
        for device in entry.devices:
            lines += [f"#### Art. {device.number}", "", device.text, ""]
    return "\n".join(lines).strip() + "\n"


def render_html(entries: list[CompilationEntry], generated_at: datetime) -> str:
    body: list[str] = []
    current_subject = None
    for entry in entries:
        if entry.source.subject != current_subject:
            if current_subject is not None:
                body.append("</section>")
            current_subject = entry.source.subject
            body.append(f"<section class='subject'><h2>{escape(current_subject)}</h2>")
        body.append("<article class='law'>")
        body.append(f"<h3>{escape(entry.source.title)}</h3>")
        body.append(
            f"<p class='source'>Fonte oficial: <a href='{escape(entry.source.url, quote=True)}' target='_blank' rel='noopener'>{escape(entry.source.url)}</a></p>"
        )
        if entry.error:
            body.append(f"<p class='error'>Falha na consulta: {escape(entry.error)}</p>")
        else:
            body.append(
                f"<p class='consulted'>Consulta: {entry.consulted_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}</p>"
            )
            for device in entry.devices:
                paragraphs = "".join(
                    f"<p>{escape(line)}</p>" for line in device.text.splitlines() if line.strip()
                )
                body.append(f"<div class='article'><h4>Art. {escape(device.number)}</h4>{paragraphs}</div>")
        body.append("</article>")
    if current_subject is not None:
        body.append("</section>")

    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Compilado Legislativo — TJSP</title>
<style>
body {{ font-family: Georgia, 'Times New Roman', serif; line-height: 1.55; max-width: 980px; margin: 0 auto; padding: 32px; color: #1f2937; }}
h1 {{ font-family: system-ui, sans-serif; margin-bottom: 8px; }}
h2 {{ font-family: system-ui, sans-serif; border-bottom: 2px solid #ddd; padding-bottom: 8px; margin-top: 42px; }}
h3, h4 {{ font-family: system-ui, sans-serif; }}
.subtitle, .source, .consulted {{ color: #5b6470; font-size: .92rem; }}
.article {{ margin: 22px 0; break-inside: avoid; }}
.article p {{ margin: 5px 0; }}
.error {{ color: #9b1c1c; font-weight: 600; }}
a {{ color: inherit; }}
@media print {{ body {{ max-width: none; padding: 15mm; }} a {{ text-decoration: none; }} .subject {{ break-before: page; }} }}
</style>
</head>
<body>
<h1>Compilado Legislativo — TJSP</h1>
<p class='subtitle'>Gerado em {escape(generated_at.astimezone().strftime('%d/%m/%Y %H:%M:%S %z'))}</p>
<p class='subtitle'>Material organizado para estudo. Em caso de divergência, prevalece a fonte oficial.</p>
{''.join(body)}
</body>
</html>"""
