import pytest
from fastapi.testclient import TestClient

from app.config import SOURCES
from app.legislation import article_in_ranges, clean_text, extract_articles
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_editorial_notes_are_removed():
    text = "Art. 1º Texto vigente. (Redação dada pela Lei nº 14.230, de 2021)."
    cleaned = clean_text(text)
    assert "Redação dada" not in cleaned
    assert "Texto vigente" in cleaned
    assert "()" not in cleaned


def test_exact_lettered_article_is_not_treated_as_range():
    assert article_in_ranges("311-A", ("311-A",))
    assert not article_in_ranges("311-B", ("311-A",))


def test_ranges_include_requested_articles():
    assert article_in_ranges("293", ("293-305",))
    assert article_in_ranges("305", ("293-305",))
    assert not article_in_ranges("306", ("293-305",))


def test_extract_only_selected_articles_and_ignore_references():
    source = next(s for s in SOURCES if s.key == "cp")
    html = """
    <html><body>
      <p>Art. 292. Fora.</p>
      <p>Art. 293. Dentro. (Redação dada pela Lei nº 1).</p>
      <p>Parágrafo único. Conforme o art. 294, segue o texto.</p>
      <p>Art. 294. Dentro.</p>
      <p>Art. 306. Fora.</p>
    </body></html>
    """
    result = extract_articles(html, source)
    assert [item.number for item in result] == ["293", "294"]
    assert all("Redação dada" not in item.text for item in result)
    assert "art. 294" in result[0].text


def test_extracts_lei_10261_artigo_marker():
    source = next(s for s in SOURCES if s.key == "lei10261")
    html = "<html><body><p>Artigo 1° - Texto.</p><p>Artigo 2° - Outro texto.</p><p>Artigo 90 - Fora.</p></body></html>"
    result = extract_articles(html, source)
    assert [item.number for item in result] == ["1", "2"]


def test_constitution_scope_matches_notice():
    source = next(s for s in SOURCES if s.key == "cf")
    assert source.article_ranges == ("5-17", "37-41", "92")


def test_defaults_expose_the_complete_default_program(client):
    response = client.get("/api/defaults")
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["sources"]}
    assert {source.key for source in SOURCES} == keys


def test_compile_rejects_non_official_source(client):
    payload = {
        "sources": [{
            "key": "x", "subject": "Teste", "title": "Teste",
            "url": "https://example.com/lei", "article_ranges": ["1"]
        }],
        "format": "json"
    }
    response = client.post("/api/compilar", json=payload)
    assert response.status_code == 422


def test_compile_rejects_duplicate_keys(client):
    source = SOURCES[0]
    item = {
        "key": source.key, "subject": source.subject, "title": source.title,
        "url": source.url, "article_ranges": list(source.article_ranges)
    }
    response = client.post("/api/compilar", json={"sources": [item, item], "format": "json"})
    assert response.status_code == 422
