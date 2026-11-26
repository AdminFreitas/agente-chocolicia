# Relatório de erro — agente Chocolícia

Data: 2026-11-17  
Escopo: somente o repositório `agente-chocolicia`. O site foi tratado apenas como referência de leitura.

## Resumo executivo

O agente não chega a gerar nem enviar uma receita. A falha imediata está na composição da CLI:

1. `rodar_agente.py` solicita `dependencias_receita`.
2. `runtime_adapters/cli_contract.py` chama `build_runtime()` e devolve apenas `runtime`, `buscadores`, `gerar`, `cliente_site`, `catalogo` e `historico`.
3. A chave `dependencias_receita` nunca é criada.
4. A CLI encerra com `composição do pipeline incompleta` antes de pesquisa, Ollama ou API do site.

Há bloqueios adicionais de configuração:

- O workflow usa nomes de variáveis diferentes dos esperados pelo agente.
- O workflow não fornece configuração do Ollama.
- Um disparo agendado assume `producao` e `dry_run=false`.
- O agente ainda não tem uma composição operacional completa para o pipeline de receitas.
- O cliente HTTP do site existe, mas a execução não alcança esse cliente.

## Fluxo efetivo atual

```text
GitHub Actions
  ├─ schedule diário ou workflow_dispatch
  ├─ checkout do agente
  ├─ instala requirements.txt
  └─ chama python rodar_agente.py
       └─ build_services()
            └─ build_runtime()
                 ├─ configura LLM, busca, site e histórico
                 └─ retorna Runtime
       └─ procura dependencias_receita
            └─ não encontrada → erro e encerramento
```

O site não aciona o agente nesse fluxo. O site seria apenas o destino das chamadas HTTP depois que o pipeline fosse composto e executado.

## Erro 1 — dependências da receita não são montadas

Arquivos envolvidos:

- `rodar_agente.py`: depois de `build_services()`, procura `services.get("dependencias_receita")`.
- `runtime_adapters/cli_contract.py`: devolve somente serviços soltos; não instancia `DependenciasReceita`.
- `pipeline/gerar_receitas.py`: define `DependenciasReceita` e exige pesquisa, gerador, cliente, catálogo, selector, histórico e visão.
- `runtime_adapters/compose.py`: monta `Runtime`, mas não faz o adaptador para `DependenciasReceita`.

Sintoma esperado:

```text
composição do pipeline incompleta
```

### Solução

Implementar no próprio agente uma única camada de composição que:

1. Instancie o pesquisador com o buscador, leitor de páginas e analista já existentes.
2. Converta a taxonomia real em objetos aceitos por `agents.planejador`.
3. Instancie `DependenciasReceita` com todas as dependências exigidas.
4. Entregue essa estrutura em `build_services()`.
5. Mantenha `integration/cliente_site.py` como único ponto de comunicação com a API do site.

Não criar endpoint novo nem duplicar o pipeline.

## Erro 2 — variáveis do workflow não coincidem com o código

### Banco do agente

- Workflow: `DATABASE_URL_AGENTE`.
- `runtime_adapters/config.py`: lê `AGENT_DATABASE_URL`.

Resultado: o runtime pode parar com `AGENT_DATABASE_URL ausente`, mesmo que o secret do GitHub esteja preenchido.

### Fase

- Workflow: `AGENT_PHASE`.
- Configuração do runtime: `SITE_PHASE`.

Resultado: a fase informada pelo workflow não chega ao cliente atual, que usa o padrão `0`.

### Busca

- Workflow: `PESQUISA_PROVEDOR` e `PESQUISA_API_KEY`.
- Configuração atual: `SEARCH_PROVIDER` e `BRAVE_SEARCH_API_KEY`.

Resultado: com o padrão `brave`, a validação procura `BRAVE_SEARCH_API_KEY`, que não é fornecida pelo workflow.

### LLM

- Workflow fornece chaves `GEMINI_API_KEY`, `GROQ_API_KEY` e `OPENROUTER_API_KEY`.
- `runtime_adapters/config.py` exige `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL` e `LLM_MODEL_*`/`LLM_FAMILY_*`.
- Ollama local não existe em um runner GitHub hospedado por `ubuntu-latest`.

### Solução

Escolher explicitamente um dos dois modelos de execução:

1. **Ollama local:** usar um runner local/self-hosted com Ollama instalado e manter `OLLAMA_BASE_URL`, `OLLAMA_MODEL` e `LLM_PROVIDER=ollama` nesse runner.
2. **GitHub Actions hospedado:** usar um provedor remoto explicitamente configurado, com as variáveis que o runtime realmente lê. Isso não atende ao requisito de Ollama local.

Não usar fallback silencioso para API paga.

## Erro 3 — agenda pode enviar para produção

No `.github/workflows/gerar-receitas.yml` e em `gerar-dicas.yml`:

```yaml
TARGET: ${{ inputs.target || 'producao' }}
DRY_RUN: ${{ inputs.dry_run && 'true' || 'false' }}
```

Em execução agendada não existem inputs. Portanto:

- `TARGET` vira `producao`.
- `DRY_RUN` vira `false`.

Se `AGENT_ENABLED=true`, a agenda tenta uma execução real em produção. Isso contradiz a regra de testar somente Preview e não publicar em produção.

### Solução

- Agenda deve ser desativada durante a correção.
- Quando reativada, deve usar `preview` e `dry_run=true` por padrão.
- Execução real deve ser manual e explicitamente autorizada.
- Produção deve ficar fora do workflow desta etapa, ou protegida por ambiente GitHub com aprovação.

## Integração com o site

Ponto central existente:

- `integration/cliente_site.py`

Responsabilidades já previstas:

- `GET /api/taxonomy`.
- Seleção de subcategorias válidas.
- `POST /api/recipes`.
- `categorySlug` e `subcategorySlug`.
- Token bearer.
- `Idempotency-Key`.
- Tratamento de erros HTTP.
- Confirmação por lookup/status.

Arquivos de apoio:

- `integration/contratos.py`: contrato v1.
- `integration/adaptador_receita.py`: montagem do payload.
- `runtime_adapters/catalog.py`: consulta da taxonomia.
- `runtime_adapters/site.py`: construção do cliente do site.

### Estado da integração

O cliente existe, mas não é alcançado porque a composição falha antes. Também não foi comprovado nesta execução:

- URL HTTPS da Preview.
- Token de rascunho.
- Consulta real da taxonomia.
- Criação do rascunho.
- Persistência no banco do site.
- Mecanismo de transição de `draft` para `published`.

O agente não deve acessar o PostgreSQL do site para inserir receita. A gravação deve ocorrer exclusivamente pela API do site.

## Integração com GitHub

### O que o workflow faz

O workflow usa:

- `actions/checkout@v4` para obter o código do agente.
- `actions/setup-python@v5` para preparar Python 3.11.
- `pip install -r requirements.txt`.
- `python rodar_agente.py`.

O workflow possui `permissions: contents: read` e `persist-credentials: false`. Portanto, ele não está autorizado a fazer commit ou push.

### O que não está conectado

O pipeline ativo de receitas não chama `services/github_service.py` nem publica Markdown em outro repositório. Essa integração pertence ao fluxo legado de artigos/notícias e não deve ser usada para substituir `POST /api/recipes`.

### Solução

Para esta tarefa, GitHub deve ser apenas:

- repositório do código;
- armazenamento dos secrets/variables;
- executor do workflow, se for usado runner adequado;
- registro dos logs.

Não é necessário token de escrita do GitHub para enviar receita ao site. O agente deve chamar a API do site diretamente.

## Qual é o acionador?

Existem três formas distintas:

| Acionador | Onde nasce | O que executa |
|---|---|---|
| Agenda | GitHub Actions `schedule` | Inicia o job automaticamente |
| Manual | GitHub Actions `workflow_dispatch` | Inicia o job com inputs |
| Local | Usuário executando `rodar_agente.py` | Inicia o agente diretamente |

Conclusão: no fluxo automatizado documentado, o acionador é do **GitHub Actions**, não do agente. O agente é o executor chamado pelo workflow. O site não dispara esse workflow.

## Ordem recomendada de correção

1. Corrigir `runtime_adapters/cli_contract.py` para produzir `DependenciasReceita`.
2. Alinhar nomes de variáveis entre workflow e `runtime_adapters/config.py`.
3. Escolher runner local/self-hosted para Ollama, ou declarar explicitamente que o workflow usará LLM remoto.
4. Desativar agenda e bloquear produção durante a validação.
5. Configurar somente Preview, branch Neon de teste, token draft e URL HTTPS da Preview.
6. Consultar a taxonomia real.
7. Gerar uma única receita.
8. Enviar como `draft` e confirmar por API.
9. Verificar se existe endpoint seguro de publicação; se não existir, manter `draft`.
10. Só depois reativar o `workflow_dispatch` controlado.

## Critério de encerramento

O erro só deve ser considerado resolvido quando uma execução real demonstrar:

```text
Ollama → composição do agente → taxonomia → geração → validação
→ POST /api/recipes → confirmação por API → status esperado na Preview
```

Até essa confirmação, não declarar integração concluída e não criar commit de conclusão.
