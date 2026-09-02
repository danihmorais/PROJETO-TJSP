# PROJETO-TJSP

Compilador legislativo para estudos voltados ao TJSP. A aplicação usa **FastAPI** como backend e uma interface estática publicada no **GitHub Pages**.

## Arquitetura

- **GitHub Pages:** interface web estática em `docs/index.html`.
- **FastAPI:** roda no mesmo servidor e no mesmo processo do agregador FastAPI já utilizado pelos demais projetos.
- **Rota da aplicação:** o agregador monta este aplicativo em `/estudos`, como faz com os demais módulos; não existe uma porta exclusiva para o TJSP.
- **localStorage:** guarda no navegador a seleção, inclusão, alteração e exclusão de legislações. O backend não usa SQLite nem outro banco para essas preferências.
- **Fontes oficiais:** o backend consulta a legislação diretamente no momento da geração.

## Programa padrão

- Direito Penal — Código Penal: arts. 293–305, 307, 308, 311-A, 312–317, 319–333, 336–337, 339–347, 357 e 359.
- Direito Processual Penal — CPP: arts. 251–258, 261–267, 274, 351–372, 394–497, 531–538, 541–548 e 574–667; Lei 9.099/1995: arts. 60–83, 88 e 89.
- Direito Processual Civil — CPC: arts. 144–155, 188–275, 294–311, 318–538 e 994–1026; Lei 9.099/1995: arts. 3º–19; Lei 12.153/2009 integral.
- Direito Constitucional — CF: arts. 5º–17, 37–41 e 92, correspondentes ao recorte indicado do Título II e do Título III.
- Direito Administrativo — Lei 10.261/1968: arts. 1º–86, 171–175 e 239–323; Lei 8.429/1992 integral.

O mesmo programa está disponível no frontend em `docs/defaults.js`, para que a tela carregue imediatamente mesmo sem depender de uma consulta ao backend.

## Interface

A página permite selecionar/desmarcar legislações, adicionar normas, editar matéria/título/fonte/recorte, excluir itens, pesquisar e restaurar o programa padrão. As alterações ficam somente no `localStorage` do navegador.

O endereço e a infraestrutura do backend não são exibidos ao usuário. O `API_URL` é injetado pelo GitHub Actions durante a publicação a partir do secret `API_URL`.

## Backend

Para execução isolada do projeto:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Quando executado pelo agregador compartilhado, o entrypoint utilizado é `tjsp_main:app` e a aplicação é montada em `/estudos`.

Endpoints dentro do namespace da aplicação:

- `GET /estudos/health` — status do backend.
- `GET /estudos/api/defaults` — programa padrão.
- `GET /estudos/fontes` — fontes padrão.
- `POST /estudos/api/compilar` — recebe a configuração atual do navegador e gera o material.
- `GET /estudos/docs` — documentação interativa do FastAPI.

O backend não mantém a configuração do usuário. Cada compilação recebe explicitamente as fontes selecionadas pela interface.

## GitHub Actions

Existe um único workflow em `.github/workflows/ci-cd.yml`.

Em pull requests, ele executa os testes e as validações estáticas.

Em pushes para `main` e em execuções manuais, após os testes passarem, ele:

1. chama o webhook compartilhado `/deploy` usando `API_URL` e `DEPLOY_WEBHOOK_SECRET`;
2. informa ao dispatcher que o projeto é `PROJETO-TJSP`;
3. aguarda `/deploy-status` até o backend estar atualizado;
4. injeta `API_URL` no frontend durante o build;
5. publica `docs/` no GitHub Pages.

O mesmo endpoint de deploy atende também o repositório `danihmorais/danihmorais.github.io`; o dispatcher diferencia os projetos pelo repositório informado no payload.

## Limpeza editorial

O parser remove elementos HTML riscados (`del`, `s`, `strike`) e notas editoriais reconhecíveis, preservando o texto normativo. O projeto não mantém uma cópia permanente da legislação; o texto é consultado nas fontes oficiais no momento da geração.

## Princípios

1. Fonte oficial primeiro.
2. Configuração do usuário no navegador, sem banco de dados.
3. Atualização do texto sob demanda.
4. Recorte programático dos artigos selecionados.
5. Remoção de ruído editorial sem substituir o texto normativo.
6. A publicação oficial da norma prevalece em caso de divergência.
