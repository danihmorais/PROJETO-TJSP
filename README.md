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

A tela foi organizada como uma pequena biblioteca de estudo: pesquisa por nome, matéria ou recorte; filtro por matéria; seleção em massa; edição e exclusão; inclusão de novas legislações; e restauração do programa padrão. As alterações continuam somente no `localStorage` do navegador.

A interface não exibe a infraestrutura do backend. O `API_URL` é injetado pelo GitHub Actions durante a publicação a partir do secret `API_URL`. O frontend aceita tanto uma URL-base do servidor quanto uma URL que já contenha `/estudos`.

## Geração do material

A geração HTML foi redesenhada para privilegiar a **lei seca** e, ao mesmo tempo, reduzir a sensação de texto corrido. O material gerado possui:

- índice lateral por matéria, legislação e artigo;
- busca instantânea no texto consultado;
- navegação direta para cada artigo e cópia do link do dispositivo;
- separação visual do **caput**, parágrafos, incisos e alíneas quando identificáveis;
- modo de leitura compacta para revisão;
- modo foco, tema escuro e suporte à impressão;
- fonte oficial e data da consulta destacadas;
- contador de artigos efetivamente localizados.

A expressão “condensado” aqui significa **condensação visual e estrutural**, não um resumo jurídico automático: o texto normativo não é reescrito para produzir uma falsa síntese. A organização procura tornar mais rápida a revisão da redação legal original.

O Markdown também utiliza a mesma estrutura de dispositivo, com os marcadores de parágrafos e incisos destacados. O JSON continua disponível para uso programático.

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

O repositório possui workflows separados para publicação estática e deploy do backend.

- `.github/workflows/static.yml` valida os arquivos estáticos, injeta `API_URL` e publica `docs/` no GitHub Pages.
- `.github/workflows/deploy-fastapi.yml` aciona o webhook compartilhado de deploy usando `API_URL` e `DEPLOY_WEBHOOK_SECRET`, identifica o projeto como `PROJETO-TJSP` e aguarda o endpoint `/deploy-status`.

## Limpeza editorial

O parser remove elementos HTML riscados (`del`, `s`, `strike`) e notas editoriais reconhecíveis, preservando o texto normativo. O projeto não mantém uma cópia permanente da legislação; o texto é consultado nas fontes oficiais no momento da geração.

## Princípios

1. Fonte oficial primeiro.
2. Configuração do usuário no navegador, sem banco de dados.
3. Atualização do texto sob demanda.
4. Recorte programático dos artigos selecionados.
5. Organização visual sem substituir a redação normativa.
6. Remoção de ruído editorial sem reescrever o dispositivo.
7. A publicação oficial da norma prevalece em caso de divergência.
