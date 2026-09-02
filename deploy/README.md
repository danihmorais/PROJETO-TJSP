# Deploy compartilhado no servidor Ubuntu

O `PROJETO-TJSP` e o `danihmorais.github.io` usam o mesmo servidor Ubuntu e o mesmo endpoint Tailscale para deploy.

## Arquitetura

```text
GitHub Actions (PROJETO-TJSP) ─────┐
                                  ├── POST /deploy ──> dispatcher no Ubuntu
GitHub Actions (danihmorais.github.io) ─┘                    │
                                                            ├── projeto PROJETO-TJSP
                                                            │     └── git pull + restart FastAPI TJSP
                                                            │
                                                            └── projeto DANIHMORAIS-GITHUB-PAGES
                                                                  └── git pull + restart aplicação existente
```

Não é necessário criar outro servidor, outra máquina ou outro hostname. O dispatcher diferencia os projetos pelo campo `project` e pelo `repository.full_name` enviados pelos workflows.

## Variáveis do dispatcher

O processo central deve manter:

- `GITHUB_WEBHOOK_SECRET`: mesmo segredo usado nos dois repositórios;
- `PROJETO_TJSP_REPO`: `danihmorais/PROJETO-TJSP`;
- `PROJETO_TJSP_DIR`: diretório do clone do backend no Ubuntu;
- `PROJETO_TJSP_COMMAND`: comando de atualização/reinício do FastAPI;
- `DANIHMORAIS_PAGES_REPO`: `danihmorais/danihmorais.github.io`;
- `DANIHMORAIS_PAGES_DIR`: diretório usado pela aplicação existente;
- `DANIHMORAIS_PAGES_COMMAND`: comando de atualização/reinício da aplicação existente.

Os caminhos e comandos devem ser os mesmos que já são usados atualmente no servidor. Não coloque credenciais de GitHub ou tokens no repositório.

## Regra importante de segurança

O servidor deve aceitar somente os dois repositórios explicitamente cadastrados. O valor enviado pelo cliente não deve ser usado diretamente como caminho ou comando shell.

O dispatcher deve:

1. validar `X-Hub-Signature-256` com `GITHUB_WEBHOOK_SECRET`;
2. aceitar apenas `POST /deploy`;
3. obter `repository.full_name`, `project` e `after` do JSON;
4. validar o par repositório/projeto em uma tabela fixa;
5. registrar o estado separadamente por `project + SHA`;
6. executar o deploy correspondente;
7. expor `GET /deploy-status?project=...&sha=...` para o workflow acompanhar o resultado.

## Fluxo do backend TJSP

O workflow `.github/workflows/deploy-backend.yml` executa os testes primeiro. Somente se os testes passarem ele chama o dispatcher. O dispatcher atualiza o clone do backend no Ubuntu e reinicia o serviço FastAPI.

## API de Documentos Modelo

Os modelos agora ficam fora do GitHub, no diretório de documentos do servidor. O FastAPI expõe:

- `GET /files`: lista os arquivos em JSON;
- `GET /files/<caminho>`: baixa um arquivo específico.

Por padrão, o backend usa `/run/media/daniel/c1eb5cb7-675f-4e8c-9564-4dabc66d9164`. É possível sobrescrever esse diretório com a variável de ambiente `DOCUMENTOS_MODELO_DIR`.

Para o GitHub Pages acessar essa API, o Funnel não deve mais servir uma pasta diretamente em `/files/`. Configure uma vez no servidor:

```bash
sudo tailscale funnel --https=443 --set-path=/files/ off
sudo tailscale funnel --https=443 --set-path=/files http://127.0.0.1:8000/files --bg
```

Depois confirme com:

```bash
sudo tailscale funnel status
curl http://127.0.0.1:8000/files
curl https://servidor.tail7d4aa4.ts.net/files
```

A rota pública `/files` deve aparecer como `proxy http://127.0.0.1:8000/files`, e não mais como um `path` apontando diretamente para `/run/media/...`.

## Fluxo do GitHub Pages

O workflow `.github/workflows/pages.yml` continua responsável pelo GitHub Pages. Ele também executa os testes e injeta `secrets.API_URL` no frontend durante o build.

Assim, o deploy do frontend e o deploy do backend são independentes: uma falha no deploy do backend não publica uma alteração do Pages, e vice-versa.

## Segredos nos dois repositórios

Configure nos dois repositórios:

- `API_URL`: URL pública do endpoint Tailscale do dispatcher, sem `/deploy` no final;
- `DEPLOY_WEBHOOK_SECRET`: exatamente o mesmo valor usado pelo dispatcher.

`API_URL` é uma URL pública, não um segredo de autenticação. O segredo real é `DEPLOY_WEBHOOK_SECRET`.
