import hashlib
import hmac
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
STATUS_ROOT = Path(os.environ.get("DEPLOY_STATUS_ROOT", "/home/daniel/python/deploy-status"))
STATUS_ROOT.mkdir(parents=True, exist_ok=True)

PROJECTS = {
    "DANIHMORAIS-GITHUB-PAGES": {
        "repository": "danihmorais/danihmorais.github.io",
        "script": "/home/daniel/python/deploy.sh",
    },
    "PROJETO-TJSP": {
        "repository": "danihmorais/PROJETO-TJSP",
        "script": "/home/daniel/python/deploy-tjsp.sh",
    },
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def valid_sha(sha):
    return bool(SHA_RE.fullmatch(sha or ""))


def status_file(project, sha):
    if project not in PROJECTS or not valid_sha(sha):
        raise ValueError("status inválido")
    directory = STATUS_ROOT / project
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{sha}.json"


def save_status(project, sha, state, message=""):
    path = status_file(project, sha)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "project": project,
        "sha": sha,
        "state": state,
        "message": message,
    }, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_status(project, sha):
    try:
        path = status_file(project, sha)
    except ValueError:
        return {"project": project, "sha": sha, "state": "unknown", "message": "Deploy inválido"}
    if not path.exists():
        return {"project": project, "sha": sha, "state": "unknown", "message": "Deploy não encontrado"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"project": project, "sha": sha, "state": "unknown", "message": "Status indisponível"}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_json(200, {"status": "ok", "projects": sorted(PROJECTS)})
            return
        if parsed.path not in ("/", "/deploy-status"):
            self.send_json(404, {"error": "not found"})
            return

        params = parse_qs(parsed.query)
        project = params.get("project", [None])[0]
        sha = params.get("sha", [None])[0]
        if project not in PROJECTS:
            self.send_json(400, {"error": "project inválido ou não informado"})
            return
        if not valid_sha(sha):
            self.send_json(400, {"error": "sha inválido ou não informado"})
            return
        self.send_json(200, load_status(project, sha))

    def do_POST(self):
        if self.path not in ("/", "/deploy"):
            self.send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Content-Length inválido"})
            return
        if length <= 0 or length > 1024 * 1024:
            self.send_json(400, {"error": "payload inválido"})
            return

        body = self.rfile.read(length)
        signature = self.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            self.send_json(401, {"error": "invalid signature"})
            return
        if self.headers.get("X-GitHub-Event") != "push":
            self.send_json(400, {"error": "invalid event"})
            return

        try:
            payload = json.loads(body)
            sha = payload["after"]
            ref = payload["ref"]
            repository = payload["repository"]["full_name"]
            project = payload["project"]
        except (KeyError, TypeError, json.JSONDecodeError):
            self.send_json(400, {"error": "invalid payload"})
            return

        if ref != "refs/heads/main":
            self.send_json(200, {"status": "ignored"})
            return
        if project not in PROJECTS:
            self.send_json(403, {"error": "projeto não autorizado"})
            return
        if repository != PROJECTS[project]["repository"]:
            self.send_json(403, {"error": "repository não corresponde ao projeto"})
            return
        if not valid_sha(sha):
            self.send_json(400, {"error": "commit inválido"})
            return

        header_project = self.headers.get("X-Deploy-Project")
        if header_project and header_project != project:
            self.send_json(403, {"error": "projeto do header não corresponde ao payload"})
            return

        save_status(project, sha, "in_progress", "Deploy iniciado")
        try:
            subprocess.Popen(
                [PROJECTS[project]["script"], sha],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            save_status(project, sha, "failure", str(exc))
            self.send_json(500, {"error": str(exc)})
            return

        self.send_json(202, {"status": "deploy iniciado", "project": project, "commit": sha})


ThreadingHTTPServer(("127.0.0.1", 9000), Handler).serve_forever()
