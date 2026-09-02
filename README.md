# PROJETO-TJSP

Compilador legislativo para estudos voltados ao TJSP. A aplicação usa **FastAPI** como backend e uma interface estática publicada no **GitHub Pages**.

## Arquitetura

- **GitHub Pages:** interface web estática em `docs/index.html`.
- **FastAPI:** roda no servidor do usuário, acessível pelo endereço HTTPS do Tailscale.
- **localStorage:** guarda no navegador a seleção, inclusão, alteração e exclusão de legislações. O backend não usa SQLite nem outro banco para essas preferências.
- **Fontes oficiais:** o backend consulta a legislação diretamente no momento da geração.

## Programa padrão

- Direito Penal — Código Penal: arts. 293–305, 307, 308, 311-A, 312–317, 319–333, 336–337, 339–347, 357 e 359.
- Direito Processual Penal — CPP: arts. 251–258, 261–267, 274, 351–372, 394–497, 531–538, 541–548 e 574–667; Lei 9.099/1995: arts. 60–83, 88 e 89.
- Direito Processual Civil — CPC: arts. 144–155, 188–275, 294–311, 318–538 e 994–1026; Lei 9.099/1995: arts. 3º–19; Lei 12.153/2009 integral.
- Direito Constitucional — CF: Título II, Capítulos I–III; Título III, Capítulo VII, Seções I–II; art. 92.
- Direito Administrativo — Lei 10.261/1968: arts. 1º–86, 171–175 e 239–323; Lei 8.429/1992 integral.

## Interface

A página permite:

- selecionar/desmarcar legislações;
- adicionar uma nova legislação oficial;
- alterar matéria, título, URL e recorte de artigos;
- excluir uma legislação da configuração local;
- pesquisar/filtrar a lista;
- restaurar o programa padrão;
- gerar HTML, Markdown ou JSON.

As alterações ficam no `localStorage` do navegador e permanecem após recarregar a página no mesmo navegador.

## Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Endpoints principais:

- `GET /health` — status do backend.
- `GET /api/defaults` — programa padrão.
- `GET /fontes` — fontes padrão.
- `POST /api/compilar` — recebe a configuração atual do navegador e gera o material.
- `GET /docs` — documentação interativa do FastAPI.

O backend não mantém a configuração do usuário. Cada compilação recebe explicitamente as fontes selecionadas pela interface.

## GitHub Pages

O workflow `.github/workflows/pages.yml` publica automaticamente o conteúdo de `docs/` no GitHub Pages a cada atualização da `main`.

## Limpeza editorial

O parser remove elementos HTML riscados (`del`, `s`, `strike`) e notas editoriais reconhecíveis, preservando o texto normativo. O projeto não mantém uma cópia permanente da legislação no repositório; o texto é consultado nas fontes oficiais no momento da geração.

## Princípios

1. Fonte oficial primeiro.
2. Configuração do usuário no navegador, sem banco de dados.
3. Atualização do texto sob demanda.
4. Recorte programático dos artigos selecionados.
5. Remoção de ruído editorial sem substituir o texto normativo.
6. A publicação oficial da norma prevalece em caso de divergência.
