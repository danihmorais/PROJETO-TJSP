from app.config import SOURCES
from app.legislation import article_in_ranges, clean_text, extract_articles


def test_editorial_notes_are_removed():
    text = "Art. 1º Texto vigente. (Redação dada pela Lei nº 14.230, de 2021)."
    cleaned = clean_text(text)
    assert "Redação dada" not in cleaned
    assert "Texto vigente" in cleaned


def test_ranges_include_requested_articles():
    assert article_in_ranges("293", ("293-305",))
    assert article_in_ranges("311-A", ("311-A",))
    assert not article_in_ranges("306", ("293-305",))


def test_extract_only_selected_articles():
    source = next(s for s in SOURCES if s.key == "cp")
    html = "<html><body><p>Art. 292. Fora.</p><p>Art. 293. Dentro. (Redação dada pela Lei nº 1).</p><p>Art. 294. Dentro.</p></body></html>"
    result = extract_articles(html, source)
    assert [item.number for item in result] == ["293", "294"]
    assert all("Redação dada" not in item.text for item in result)
