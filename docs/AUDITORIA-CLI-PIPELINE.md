# Auditoria CLI e Pipeline de Receitas (Etapa 0)

Data: 2026-11-22  
Ambiente: Windows / branch `fix/cli-pipeline-receitas`  
Objetivo: Diagnóstico do CLI (`rodar_agente.py`), workflows do GitHub Actions e etapas do pipeline de receitas (`pipeline/gerar_receitas.py`), sem alterações de código.

---

## 1. Verificação da Hipótese Inicial

### Hipótese
> Os workflows chamam `rodar_agente.py --receita --target preview --dry-run`, mas `rodar_agente.py` reconheceria apenas `--artigo`, causando erro do argparse (código 2). Também suspeitava-se que `pipeline/gerar_receitas.py` não chamaria os agentes de verdade.

### Resultado: REFUTADA PARCIALMENTE / CONFIRMADA EM OUTRO PONTO
1. **Parser do argparse:** O argumento `--artigo` **já foi removido** de `rodar_agente.py`. O parser atual já define um grupo mutuamente exclusivo com `--receita` e `--dica`, além de `--dry-run`, `--target` (`preview`, `production`), `--assunto` e `--subcategoria`.
2. **Execução de `python rodar_agente.py --help`:**
   - **Saída:**
     ```text
     usage: rodar_agente.py [-h] (--receita | --dica) [--dry-run]
                            [--target {preview,production}] [--assunto ASSUNTO]
                            [--subcategoria SUBCATEGORIA]
     ```
   - **Código de saída:** `0` (sucesso).
3. **Execução de `python rodar_agente.py --receita --dry-run`:**
   - **Saída:**
     ```json
     {"estado": "erro", "tipo": "receita", "etapa": "composicao", "erro": "ConfigurationError", "motivo": "SITE_BASE_URL_PREVIEW ausente para target=preview"}
     ```
   - **Código de saída:** `2` (erro de configuração/uso).
   - **Causa real do erro:** O CLI falhou não por erro de sintaxe do argparse em `--receita`, mas porque o módulo de composição (`runtime_adapters/compose.py`) exige `SITE_BASE_URL_PREVIEW` mesmo em `--dry-run` quando `target=preview`.

---

## 2. Comandos e Variáveis de Ambiente: Workflows vs CLI vs Settings

### Workflows Ativos
- `.github/workflows/chocolicia-gerar-receitas.yml`
  - Comando: `python rodar_agente.py --receita --target preview --assunto "$ASSUNTO"`
  - Modo: lê `DRY_RUN` do ambiente (`true` no agendado, configurável no dispatch).
- `.github/workflows/chocolicia-gerar-dicas.yml`
  - Comando: `python rodar_agente.py --dica --target preview --assunto "$ASSUNTO"`
- Workflows arquivados (`.disabled`):
  - Chamavam opções legadas como `--enviar`, `--contrato legacy`, `--fase`.

### Tabela Comparativa de Variáveis

| Variável nos Workflows | Em `config/settings.py` | No `runtime_adapters/config.py` | Observação |
|---|---|---|---|
| `TARGET` | Sim (`TARGET`) | Sim (`target`) | `preview` ou `production` |
| `DRY_RUN` | Sim (`DRY_RUN`) | Sim (`dry_run`) | Booleano (`true`/`false`) |
| `SITE_BASE_URL_PREVIEW` | Sim (`SITE_BASE_URL_PREVIEW`) | Sim (`site_base_url_preview`) | URL base do preview Vercel |
| `SITE_BASE_URL` | Sim (`SITE_BASE_URL`) | Sim (`site_base_url`) | Produção (`https://www.chocolicia.site`) |
| `SITE_TOKEN_DRAFT_PREVIEW` | Sim | Sim (`site_token_draft_preview`) | Token de rascunho preview |
| `SITE_TOKEN_DRAFT` | Sim | Sim (`site_token_draft`) | Token de rascunho produção |
| `SITE_TOKEN_PUBLISH` | Sim | Sim (`site_token_publish`) | Token de publicação produção |
| `AGENT_DATABASE_URL` | **Divergente**: `DATABASE_URL_AGENTE` | Sim (`agent_database_url`) | Workflow usa `AGENT_DATABASE_URL`, settings usa `DATABASE_URL_AGENTE` |
| `BRAVE_SEARCH_API_KEY` | **Divergente**: `PESQUISA_API_KEY` | Sim (`brave_search_api_key`) | Workflows usam `BRAVE_SEARCH_API_KEY` |
| `CONTRACT_VERSION` / `SITE_CONTRACT` | Sim (`CONTRACT_VERSION`) | Sim (`site_contract`) | Versão do contrato da API (v1) |
| `AGENT_ENABLED` | Sim | Sim | Portão em CI |
| `AGENT_PHASE` | Sim | Sim | Fase de risco (0 sombra, 1 baixo) |
| `ASSUNTO` | Sim | Sim | Pauta ou `automatico` |

---

## 3. Mapeamento de Etapas em `pipeline/gerar_receitas.py`

| # | Etapa (docs/01 §7.2) | Função Invocada | Status | Observações |
|---|---|---|---|---|
| 1 | Pauta e Reserva | Validação de `topic_slug`/`subcategoria` | **Parcial** | Validação existe; reserva real no banco do agente (`claim_topic`) está em `rodar_agente.py`, não centralizada no pipeline. |
| 2 | Pesquisa | `deps.pesquisar(pauta)` | **Chamada real** | Invoca `agents/pesquisador.py:pesquisar_receita` com fallback de buscadores e leitor HTTP. |
| 3 | Análise | `Analista(catalogo, fase)` | **Chamada real** | Integrada internamente na pesquisa culinária (`agents/analista.py`). |
| 4 | Criação | `editor.criar_receita(...)` | **Chamada real** | Invoca `agents/editor.py` com persona Chef IA e reparo de até 2 tentativas. |
| 5 | Validação | `validador.validar(...)` | **Chamada real** | Usa `ValidadorPontoUnico` -> `validators.validar_conteudo`. |
| 6 | Revisão | `revisor.revisar_conteudo(...)` | **Chamada real** | Invoca `agents/revisor.py` com checagem de família diferente. |
| 7 | SEO | `seo.ajustar_seo(...)` | **Chamada real** | Invoca `agents/seo.py`. |
| 8 | Imagem | `escolher_capa(...)` | **Chamada real** | Invoca `services/imagem_service.py` (modo `stock` via Pexels/Pixabay/Wikimedia/Openverse com fallback `generate`). |
| 9 | Adaptador | `montar_payload_receita(...)` | **Chamada real** | Converte para `ReceitaV1` (Pydantic estrito) ou legado. |
| 10 | Envio | `deps.cliente.criar_receita(...)` | **Chamada real** | Invoca `integration/cliente_site.py` com suporte a `dry_run` e tratamento de erros. |
| 11 | Resumo de Execução | Gravação de `output/resumo-execucao.md` | **Ausente** | Não há emissão de `output/resumo-execucao.md` no encerramento da execução. |

---

## 4. Conclusão e Próximos Passos (Plano Ajustado)

1. **Ajuste da CLI (`rodar_agente.py`):**
   - Permitir execução `--dry-run` limpa sem exigir dependências remotas do site quando nenhum envio real for requisitado.
   - Gerar sempre o artefato `output/resumo-execucao.md` com pauta, estado, motivo de rejeição e custo (sem segredos).
   - Padronizar códigos de saída: `0` para sucesso ou pauta rejeitada com motivo registrado; `1` para erro técnico; `2` para uso incorreto.
2. **Pipeline (`pipeline/gerar_receitas.py`):**
   - Em `--dry-run`, gerar, validar e imprimir no stdout o payload v1 completo sem enviar à rede.
   - Verificar lista de modelos aprovados (`config/modelos_aprovados.json`) e abortar imediatamente se o modelo estiver fora dela.
   - Respeitar interruptor de emergência e tetos de custo.
3. **Contrato:**
   - Validar payload contra `contracts/recipe.v1.schema.json`.
4. **Testes:**
   - Manter cobertura isolada (sem rede externa) com `httpx.MockTransport`.
