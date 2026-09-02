from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def make_client(tmp_path: Path) -> TestClient:
    (tmp_path / "Modelos").mkdir()
    (tmp_path / "Modelo.docx").write_bytes(b"conteudo")
    (tmp_path / "Modelos" / "ETP.docx").write_bytes(b"etp")
    return TestClient(main.app)


def test_list_files(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUMENTOS_MODELO_DIR", str(tmp_path))
    client = make_client(tmp_path)

    response = client.get("/files")

    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    paths = {item["path"] for item in data["files"]}
    assert paths == {"Modelo.docx", "Modelos/ETP.docx"}
    assert all(item["url"].startswith("/files/") for item in data["files"])


def test_download_file(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUMENTOS_MODELO_DIR", str(tmp_path))
    client = make_client(tmp_path)

    response = client.get("/files/Modelos/ETP.docx")

    assert response.status_code == 200
    assert response.content == b"etp"
    assert "ETP.docx" in response.headers.get("content-disposition", "")


def test_download_blocks_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCUMENTOS_MODELO_DIR", str(tmp_path))
    client = make_client(tmp_path)

    response = client.get("/files/../outside.txt")

    assert response.status_code == 400
