# PROJETO-TJSP

Compilador legislativo para estudos voltados ao TJSP. A aplicação usa **FastAPI** como backend e uma interface estática publicada no **GitHub Pages**.

## Arquitetura

- **GitHub Pages:** interface web estática em `docs/index.html`.
- **FastAPI:** roda no mesmo servidor e no mesmo processo do agregador FastAPI já utilizado pelos demais projetos.
- **Rota pública:** o agregador monta este aplicativo em `/estudos`; não existe um servidor ou uma porta exclusiva para o TJSP.
- **localStorage:** guarda no navegador a seleção, inclusão, alteração e exclusão de legislações. O backend não usa SQLite nem outro banco para essas preferências.
- **Fontes oficiais:** o backend consulta a legislação diretamente no momento da geração.

## Integração com o servidor compartilhado

O repositório é independente do agregador. O arquivo `tjsp_main.py` expõe `app` e permite que o `main.py` do servidor compartilhado o carregue como os demais projetos.

No agregador, a configuração fica conceitualmente assim:

```python
app_tjsp = load_app_from_path(
    "tjsp_main",
    os.path.join(PROJETO_TJSP_ROOT, "tjsp_main.py"),
    PROJETO_TJSP_ROOT,
)
app.mount("/estudos", app_tjsp)
```

O caminho de `PROJETO_TJSP_ROOT` deve apontar para o clone do repositório no servidor Ubuntu. O processo continua sendo o mesmo `uvicorn main:app`/serviço FastAPI já existente.

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

Para execução isolada do projeto:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Quando executado pelo agregador compartilhado, o entrypoint utilizado é `tjsp_main:app` e a aplicação é montada em `/estudos`.

Endpoints dentro do namespace do projeto:

- `GET /estudos/health` — status do backend.
- `GET /estudos/api/defaults` — programa padrão.
- `GET /estudos/fontes` — fontes padrão.
- `POST /estudos/api/compilar` — recebe a configuração atual do navegador e gera o material.
- `GET /estudos/docs` — documentação interativa do FastAPI.

O backend não mantém a configuração do usuário. Cada compilação recebe explicitamente as fontes selecionadas pela interface.

## GitHub Pages

O workflow `.github/workflows/pages.yml` publica automaticamente o conteúdo de `docs/` no GitHub Pages a cada atualização da `main`.

## Deploy

O workflow `.github/workflows/deploy-backend.yml` executa os testes antes de solicitar o deploy ao webhook compartilhado do servidor Ubuntu. O webhook deve identificar o projeto pelo repositório/projeto informado no payload e encaminhar o commit para o script de deploy correspondente.

O mesmo `API_URL` é usado pelos workflows para acessar `/deploy` e `/deploy-status`; ele continua sendo apenas o endereço base da API compartilhada.

## Limpeza editorial

O parser remove elementos HTML riscados (`del`, `s`, `strike`) e notas editoriais reconhecíveis, preservando o texto normativo. O projeto não mantém uma cópia permanente da legislação no repositório; o texto é consultado nas fontes oficiais no momento da geração.

## Princípios

1. Fonte oficial primeiro.
2. Configuração do usuário no navegador, sem banco de dados.
3. Atualização do texto sob demanda.
4. Recorte programático dos artigos selecionados.
5. Remoção de ruído editorial sem substituir o texto normativo.
6. A publicação oficial da norma prevalece em caso de divergência.
