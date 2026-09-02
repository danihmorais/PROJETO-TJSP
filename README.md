# PROJETO-TJSP

Compilador legislativo para estudos voltados ao TJSP. A aplicação usa **FastAPI** e consulta as versões oficiais das normas, extraindo somente os dispositivos previstos no programa e removendo notas editoriais de alteração, como `Redação dada pela Lei...`, `Incluído pela Lei...`, `Revogado pela Lei...` e links de referência inseridos no texto.

## Escopo

- Direito Penal — Código Penal: arts. 293–305, 307, 308, 311-A, 312–317, 319–333, 336–337, 339–347, 357 e 359.
- Direito Processual Penal — CPP: arts. 251–258, 261–267, 274, 351–372, 394–497, 531–538, 541–548 e 574–667; Lei 9.099/1995: arts. 60–83, 88 e 89.
- Direito Processual Civil — CPC: arts. 144–155, 188–275, 294–311, 318–538 e 994–1026; Lei 9.099/1995: arts. 3º–19; Lei 12.153/2009 integral.
- Direito Constitucional — CF: Título II, Capítulos I–III; Título III, Capítulo VII, Seções I–II; art. 92.
- Direito Administrativo — Lei 10.261/1968: arts. 1º–86, 171–175 e 239–323; Lei 8.429/1992 integral.

## Execução

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Acesse `http://127.0.0.1:8000/`.

### API

- `GET /health` — status.
- `GET /fontes` — fontes oficiais e recortes configurados.
- `GET /compilado?format=html` — compilado HTML, pronto para imprimir/salvar como PDF pelo navegador.
- `GET /compilado?format=markdown` — compilado em Markdown.
- `GET /compilado?format=json` — metadados e artigos efetivamente extraídos.
- `POST /api/compilar` — permite selecionar fontes e formato, por exemplo `{"keys":["cp","cpp"],"format":"html"}`.

A documentação interativa fica em `/docs`.

## Limpeza e segurança editorial

O parser remove elementos HTML riscados (`del`, `s`, `strike`) e notas editoriais reconhecíveis. Referências internas como `conforme o art. 294` são preservadas porque somente marcadores de artigo no início de uma linha iniciam um novo dispositivo.

O projeto **não grava uma cópia permanente da legislação no GitHub**: o texto é buscado no momento da geração. Isso reduz o risco de estudar uma versão antiga por engano.

## Princípios

1. **Fonte oficial primeiro:** não usar agregadores jurídicos como fonte do texto normativo.
2. **Rastreabilidade:** cada norma mantém a URL oficial e o horário da consulta.
3. **Recorte programático:** artigos fora do edital não entram no compilado, salvo normas marcadas como integrais.
4. **Limpeza editorial:** remove links e expressões de histórico legislativo sem alterar o texto dispositivo deliberadamente.
5. **Atualização sob demanda:** o conteúdo é consultado novamente a cada geração, evitando manter legislação desatualizada no repositório.
6. **Prevalência da fonte oficial:** o compilado é ferramenta de estudo e não substitui a publicação oficial.
