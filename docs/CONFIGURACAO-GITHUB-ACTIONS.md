# Agendamento do agente Chocolícia

## Receitas

`.github/workflows/gerar-receitas.yml` agenda uma execução diária às 08:00 em
`America/Sao_Paulo` (`0 11 * * *` em UTC). O agendamento cria somente
rascunhos no branch padrão. Para publicar, informe o slug de um rascunho já
revisado no disparo manual; o job de publicação promove esse rascunho após
aprovação do ambiente `recipe-publish`. O runner precisa ser
um **self-hosted Windows** com as labels `self-hosted`, `windows`, `x64` e
`ollama`, pois o Ollama em `127.0.0.1:11434` não é acessível a um runner
GitHub-hosted. Os dois workflows usam esse runner.

Configure no repositório, em **Settings > Secrets and variables > Actions**:

### Secrets

- `RECIPES_AGENT_TOKEN_DRAFT`: token de escopo draft da API de produção.
- `RECIPES_AGENT_TOKEN_PUBLISH`: token de escopo publish; configure como secret
  do ambiente `recipe-publish`, que deve exigir aprovação.
- `DATABASE_URL_AGENTE`: banco exclusivo do agente, usado para impedir
  reutilização de `topic_slug` e registrar publicação/ID/slug.
- `PESQUISA_API_KEY`: chave do provedor Brave.
- `PEXELS_API_KEY` e `PIXABAY_API_KEY`: provedores usados para obter imagem de
  capa; configure pelo menos um para habilitar a seleção de imagem.

### Variables

- `AGENT_ENABLED=true` para habilitar o job depois que a API, migration,
  secrets e teste real de rascunho estiverem concluídos.
- `AGENT_PUBLISHING_ENABLED=true` somente para permitir publicação manual após
  aprovação; o padrão `false` bloqueia publicação.
- `AGENT_PHASE` entre `1` e `3`, somente quando os critérios da fase já tiverem
  sido cumpridos. A Fase 0 não publica.
- `OLLAMA_MODEL`: modelo já instalado no runner; o padrão do workflow é
  `qwen2.5:3b`.
- `OLLAMA_CREATION_FAMILY`, `OLLAMA_REVIEW_MODEL` e
  `OLLAMA_REVIEW_FAMILY`, `OLLAMA_VISION_MODEL` e `OLLAMA_VISION_FAMILY`:
  obrigatórios para receita. Configure modelos
  efetivamente instalados no runner e famílias realmente distintas, pois o
  agente recusa revisão pelo mesmo grupo do gerador. `OLLAMA_CREATION_MODEL`
  é opcional e, se omitido, usa `OLLAMA_MODEL`.
- `AGENT_PHASE` entre `1` e `3`; a subcategoria é escolhida da taxonomia ativa,
  habilitada para o agente e compatível com a fase. O disparo manual pode
  informar um slug específico.

O workflow gera um tema com Ollama quando `RECIPE_TOPIC` não é fornecido e
registra a reserva no banco antes de gerar/enviar, para bloquear duplicatas.
O POST usa o contrato legado compatível com o endpoint atual, incluindo os
slugs da taxonomia, `Idempotency-Key` estável e `status: draft`. A publicação
não gera uma nova receita: `POST /api/recipes/:slug/publish` promove apenas o
rascunho escolhido e revisado. A API exige token publish e
`AGENT_PUBLISHING_ENABLED=true`; o job confirma status, ID e slug.
O Cron da Vercel deve permanecer removido para evitar geração duplicada.

## Dicas e artigos

`.github/workflows/gerar-dicas.yml` mantém a cadência de terça e sexta às 09:00
em São Paulo (`0 12 * * 2,5` UTC), mas permanece bloqueado até o agente compor
e persistir a geração interna. A composição de `dependencias_dica` ainda não
está pronta. Não defina `AGENT_INTERNAL_CONTENT_READY=true` até isso ser
concluído. O workflow usa Ollama e gravação interna; não recebe token do site e
`SITE_ARTICLES_ENABLED` fica `false`. O destino local não tem `POST /api/articles`;
esse workflow não deve ser habilitado para enviar conteúdo ao site nem usar
`/api/recipes` para dicas. O adaptador v1 existente fica disponível para quando
a API de artigos for implantada.

## Configuração local

O `.env` local do agente aponta para `AGENT_ENV=production`,
`SITE_BASE_URL=https://www.chocolicia.site` e Ollama local. Ele não contém
`RECIPES_AGENT_TOKEN`. Nenhuma chamada de publicação foi executada. Não
versione `.env` nem inclua valores de secrets neste repositório.
