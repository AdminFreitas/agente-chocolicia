# CODEX 01 - Site: base para o agente (migrations, API e escopos de token)

Este arquivo tem duas partes. A **Parte A** é para o responsável pelo projeto (preparação). A **Parte B** é o prompt a colar no Codex, aberto na raiz do repositório `chocolicia`.

---

## Parte A - Preparação (antes de colar o prompt)

1. **Copiar a documentação para o repositório do site**, em `docs/agente/`: os arquivos `00` a `08`, `PESQUISA-RECEITAS.md` e a pasta `seeds/` (com `taxonomy.seed.json`). O Codex lê esses arquivos como especificação.
2. **Criar um branch de teste no Neon** (cópia do banco, sem dados sensíveis, de preferência) e guardar a string de conexão em uma variável chamada `DATABASE_URL_TEST`, no `.env` local. **Nunca** usar a string de produção nesta tarefa.
3. **Não executar nada em produção** até a revisão. As migrations e os scripts de backfill serão aplicados em produção por você, com o roteiro que o Codex deixar em `docs/agente/MIGRATIONS-RUNBOOK.md`.
4. Fazer um backup do banco de produção antes de qualquer aplicação futura.
5. Ao final, **trazer de volta** para revisão: `docs/agente/AUDITORIA-SITE.md`, `docs/agente/RELATORIO-BLOCO-1.md` e a lista de arquivos alterados. Com eles, o Bloco 2 é escrito já com os nomes reais do código.

### Sequência dos blocos

| Bloco | Conteúdo | Depende de |
| --- | --- | --- |
| 1 (este) | Auditoria, migrations, seeds, tokens e escopos, contrato v1 da API, endpoints de leitura, `POST /api/articles`, contrato exportado, testes | Documentação em `docs/agente/` |
| 2 | Imagens: download de banco de imagens com proteção contra SSRF, geração em último caso, estado `processing`, proveniência | Bloco 1 |
| 3 | Denúncias, endpoints administrativos (arquivar, restaurar, arquivar em lote), disjuntor por receita, desativar o cron interno | Bloco 1 |
| 4 | Front: avisos, assinatura, legendas, páginas de categoria e Aprenda, URLs, JSON-LD, sitemap | Blocos 1 a 3 |
| 5 | Agente: estrutura do projeto, cliente do site, adaptador, banco do agente | Bloco 1 |
| 6 | Agente: pesquisa, criação, validadores, imagem, SEO | Blocos 1 e 5 |
| 7 | Agente: testes de mutação, golden set, integração contínua, agendador | Blocos 5 e 6 |

---

## Parte B - Prompt para o Codex

**COLE A PARTIR DAQUI**

# Tarefa: Bloco 1 - base do site para o agente de receitas

## Papel e contexto

Você trabalha no repositório do site **Chocolícia** (`chocolicia`). Um agente de IA externo (projeto separado, em Python) vai gerar receitas e artigos e enviá-los ao site por API. Esta tarefa prepara o **site** para isso: banco de dados, autenticação por escopos e a API. A especificação completa está em `docs/agente/`. **Leia antes de escrever qualquer código:**

- `docs/agente/04-ESTRUTURA-CONTEUDO.md`: seções 5 a 8, 12, 14 e 15.
- `docs/agente/06-INTEGRACAO.md`: inteiro.
- `docs/agente/01-ARQUITETURA.md`: seções 3.2, 7.4, 8.4, 8.5 e 13.
- `docs/agente/08-VALIDACAO.md`: seções 4.11 (API) e 4.12 (pós-publicação).
- `docs/agente/seeds/taxonomy.seed.json`: dados de seed da taxonomia (fonte de verdade para o seed).

O site já tem, segundo auditoria anterior: `server/recipesRoutes.ts`, `server/recipeAgent.ts`, `shared/recipes.ts`, `drizzle/schema.ts` (tabela `recipes`), `POST /api/recipes` com `Authorization: Bearer <RECIPES_AGENT_TOKEN>`, validação Zod (`recipeInputSchema`), `sanitizeDeep` e um adaptador em `integrations/agente-chocolicia-recipes/`. **Essas premissas devem ser confirmadas na Etapa 0.**

## Regras invioláveis

1. Trabalhe no branch `feat/agente-base`. Nunca faça commit na `main`. Commits pequenos, com mensagem descritiva.
2. **Nunca execute migrations, scripts ou testes contra o banco de produção.** Use somente `DATABASE_URL_TEST` (branch Neon de teste) ou um Postgres local (Docker ou PGlite). Se `DATABASE_URL_TEST` não existir, escreva as migrations, os scripts e os testes, rode tudo em Postgres local, e **informe** no relatório que a validação no Neon ficou pendente.
3. **Nunca leia, imprima, copie ou faça commit de `.env`, tokens, senhas ou strings de conexão.** Em logs, mascare qualquer segredo.
4. **Mudanças aditivas.** O site publicado e o fluxo atual (`POST /api/recipes` legado, `generate-daily`, cron interno) continuam funcionando. Não remova nem renomeie colunas, rotas ou variáveis existentes.
5. **Não invente dados.** Não preencha o catálogo de ingredientes. O seed fornecido cobre apenas taxonomia e tags. As tabelas de ingredientes ficam vazias, com ferramenta de importação validada. **Não há** detecção, catálogo nem lista de alérgenos neste projeto.
6. Siga as convenções do repositório (TypeScript, lint, formatação, estrutura do Drizzle). Não adicione dependências sem justificar no relatório.
7. **Se uma premissa deste prompt não bater com o código, pare e relate.** Não improvise nem adapte em silêncio.
8. Mensagens de erro em português; **códigos** de erro em inglês, `snake_case`.
9. **Não altere o visual do site** neste bloco (nada de componentes, estilos ou páginas). É backend, banco e contratos.

## Etapa 0 - Auditoria somente leitura

Gere `docs/agente/AUDITORIA-SITE.md` respondendo, com caminhos de arquivo e trechos curtos (sem segredos):

1. Estrutura real da tabela `recipes` (nomes de colunas e tipos), onde ficam o schema e as migrations do Drizzle, e como as migrations são geradas e aplicadas (scripts do `package.json`).
2. A lista `RECIPE_CATEGORIES` e todos os lugares que a usam (servidor, cliente, compartilhado).
3. Autenticação: como `RECIPES_AGENT_TOKEN` é lido e comparado; como `generate-daily` é protegido; se existe autenticação de administrador e onde.
4. **Todos os pontos que criam receitas** e como tratam `status`: `POST /api/recipes`, `generate-daily`, o adaptador em `integrations/`, o cron `runDailyRecipeGeneration`. Cada um envia `status` explícito? (Isso condiciona a troca do padrão para `draft`.)
5. Se existe rate limit (qualquer middleware) e como está configurado.
6. Como o servidor roda (Express, serverless etc.) e os limites de execução da Vercel (`vercel.json`, `maxDuration`).
7. Estrutura atual de URLs de receitas; existência de `sitemap.xml`, `robots.txt` e JSON-LD.
8. Framework de testes e scripts disponíveis.
9. Versão do PostgreSQL do banco de teste (`SHOW server_version_num`).
10. Quantidade de receitas no banco de teste (se for cópia dos dados reais).

Se alguma premissa crítica falhar (tabela, rota ou autenticação diferentes do esperado), **pare** e relate antes de seguir.

## Etapa 1 - Migrations e seeds

Crie migrations Drizzle **aditivas e idempotentes** (`IF NOT EXISTS` quando fizer sentido), uma por tema, cada uma com nota de rollback. Referência: `04-ESTRUTURA-CONTEUDO.md`, seções 7 e 8.

1. **`categories`** (seção 8.1): `id`, `slug` único, `name`, `parent_id` (auto-relação), `sort_order`, `active`, `risk_level`, `agent_enabled` (padrão falso), `description`, `seo_title`, `seo_description`. Regras: `risk_level` obrigatório e restrito a `low`, `medium`, `high` em subcategorias; subcategoria não pode ser pai de outra (trigger simples ou validação na camada de dados, documentada).
2. **Tags e autores:** `tags` (`slug` único, `name`, `kind` em `topic`, `occasion`, `diet`, `collection`, `enabled`), `recipe_tags`, `authors` (com seed `equipe-chocolicia`, nome "Equipe Chocolícia").
3. **Ingredientes** (seção 7): `ingredients` (com `needs_label_check`, `vegetarian_ok` e `vegan_ok`), `ingredient_aliases` e `recipe_ingredients`. Todas ficam vazias; não há tabela de alérgenos.
   - Crie `scripts/import-ingredients.ts`: valida um arquivo JSON de catálogo (slug único, `canonical_unit` em `g`, `ml`, `un`, conversões numéricas, aliases únicos, sinalizadores booleanos) e faz upsert idempotente. Documente o formato em `docs/agente/INGREDIENTS-IMPORT.md`, com um exemplo marcado como **EXEMPLO, NÃO IMPORTAR EM PRODUÇÃO**.
4. **Colunas novas em `recipes`** (seção 8.3), todas anuláveis ou com valor padrão: `category_id`, `subcategory_id`, `intro`, `rest_time_min`, `yield_label`, `diet text[]` (padrão `{}`), `occasions text[]` (padrão `{}`), `author_id` (padrão: Equipe Chocolícia), `cover_image_source jsonb`, `cover_image_is_ai boolean` (padrão falso), `updated_at` (padrão agora; atualizado em toda alteração). Aceite os estados `draft`, `processing`, `published`, `archived` em `status` (ajuste o tipo ou a verificação sem quebrar os valores existentes).
5. **Artigos e relacionamentos:** `tip_topics`, `articles` (com `tip_topic`; `subcategory_id` opcional em dicas), `article_tags`, `content_relations` (com `CHECK (num_nonnulls(...) = 1)` na origem e no destino) e `content_reports` (seções 8.5 a 8.7). No índice único de `content_relations`: a migration verifica `server_version_num` e usa `UNIQUE NULLS NOT DISTINCT` se for 150000 ou mais; senão, índice único por expressão com `COALESCE` (bloco `DO $$ ... $$`).
6. **Infraestrutura da API:** `api_idempotency_keys` (`key`, `endpoint`, `token_scope`, `request_hash`, `response_status`, `response_body jsonb`, `created_at`, `expires_at`, único em `key` + `endpoint`) e `api_rate_limits` (`bucket_key`, `window_start`, `count`, chave composta).
7. **Seed idempotente** a partir de `docs/agente/seeds/taxonomy.seed.json`, por `slug` (`ON CONFLICT (slug) DO UPDATE`): categorias, subcategorias (com `risk_level`, `agent_enabled = false`) tags (`kind`, `enabled`) e assuntos de dica (`tip_topics`: `slug`, `name`, `risk_level`, `agent_enabled`). Teste que confirma **11 categorias, 74 subcategorias (4 `low`, 43 `medium`, 27 `high`)** e que rodar o seed duas vezes não duplica nada.
8. **Backfill** `scripts/backfill-recipe-taxonomy.ts`: *dry-run* por padrão, `--apply` explícito. Usa `legacy_category_map` do seed para preencher `category_id` e `subcategory_id` quando o mapeamento é direto; copia `recipes.tags` para `tags` e `recipe_tags` (`kind = topic`, só tags válidas após normalizar o slug); gera um CSV de **exceções** (receitas que precisam de decisão: `Sobremesas`, `Festas e buffet`, `Datas especiais`, reclassificação de `Bolos`). **Nunca** altera `recipes.category` nem `recipes.tags` (legado).
9. **Runbook** `docs/agente/MIGRATIONS-RUNBOOK.md`: ordem de aplicação, pré-checagens, backup, comandos para produção (**sem executar**), verificações pós-aplicação e rollback de cada migration.

**Fora desta etapa:** tabelas `agent_*` (ficam no banco do agente) e a retirada do enum antigo de categorias.

## Etapa 2 - Tokens, escopos e controles

Referência: `06-INTEGRACAO.md`, seções 3, 4, 10 e 12. Centralize a configuração em um módulo (por exemplo `server/agentConfig.ts`) com validação Zod das variáveis e padrões seguros.

1. **Tokens:** ler `RECIPES_AGENT_TOKEN_DRAFT` e `RECIPES_AGENT_TOKEN_PUBLISH`. Comparar com `timingSafeEqual` sobre **hashes SHA-256** dos valores (evita vazar o comprimento). O token legado `RECIPES_AGENT_TOKEN` continua aceito com escopo `draft`; `RECIPES_AGENT_TOKEN_LEGACY_SCOPE=publish` mantém conscientemente o comportamento antigo. Registrar aviso (sem o token) quando o legado for usado.
2. **Escopos:** `draft` cria rascunho; `publish` pode criar com `status: "published"`. Pedido `published` com escopo `draft` devolve `403 scope_insufficient`. O token do agente **só cria**: nenhuma rota de edição, exclusão ou despublicação aceita esses tokens.
3. **Interruptor:** `AGENT_PUBLISHING_ENABLED` (padrão `false` se ausente). Falso: pedidos `published` do agente devolvem `403 publishing_disabled`; rascunhos continuam permitidos.
4. **Fase:** `AGENT_PHASE` (0 a 3, padrão 0). Para tokens do agente, a subcategoria precisa estar `active` e `agent_enabled`, e o `risk_level` precisa ser permitido pela fase (`phase_allows_risk` do seed): `422 subcategory_not_enabled`. Na Fase 0, pedido com `published` devolve `403 phase_not_allowed`.
5. **Limites diários** (dia calendário em `America/Sao_Paulo`): `AGENT_DAILY_CAP_RECIPES` (padrão 1), `AGENT_DAILY_CAP_ARTICLES` (padrão 1) para conteúdo publicado ou em `processing`, e `AGENT_DAILY_CAP_DRAFTS` (padrão 3) para rascunhos. Excedeu: `429 daily_cap_reached`, com `Retry-After` até a meia-noite de Brasília.
6. **Rate limit** por token: `AGENT_RATE_LIMIT_PER_MIN` (padrão 30), usando a tabela `api_rate_limits` (sem infraestrutura nova): `429 rate_limited` com `Retry-After`.
7. **Idempotência:** `Idempotency-Key` obrigatório no contrato v1. Mesma chave e mesmo `request_hash`: devolve a resposta original, com o cabeçalho `Idempotent-Replay: true`. Mesma chave com corpo diferente: `422 idempotency_key_reuse`. Validade de 24 horas, com limpeza oportunista.
8. **`X-Request-Id`:** aceitar ou gerar, devolver no cabeçalho e registrar em log (sem dados sensíveis).

## Etapa 3 - API

Referência: `06-INTEGRACAO.md`, seções 5, 6, 8, 9, 11 e 14.

1. **`POST /api/recipes`:**
   - Sem `X-Contract-Version`: comportamento **legado** (campo `category`, `coverImageUrl` obrigatório), exceto o padrão de `status` (item 2).
   - `X-Contract-Version: 1`: contrato v1 da seção 6 (campos, limites, `subcategorySlug`, `ingredients[].items[].ingredientSlug`, `restTimeMin`, `yieldLabel`, `intro`, `occasions`, `collections`, `diet`, `generationMeta` etc.).
   - Outro valor: `400 unsupported_contract_version`.
   - **Imagem (provisório neste bloco):** o v1 aceita `coverImageUrl` + `coverImageAlt` (URL pública já existente). O objeto `cover` é validado, mas `cover.mode` igual a `stock` ou `generate` devolve `501 image_mode_not_implemented` até o Bloco 2. Documente isso como TEMPORÁRIO no código e no relatório.
2. **Padrão de `status` = `draft`.** Ordem obrigatória: primeiro atualize **todos os chamadores internos** (`generate-daily`, adaptador, cron) para enviar `status` explícito preservando o comportamento atual; depois mude o padrão no Zod. Teste: pedido sem `status` grava `draft`.
3. **Validações do servidor no v1** (seção 6.4), com os códigos da seção 11:
   - Zod e `sanitizeDeep`.
   - Resolver cada `ingredientSlug` no catálogo e **recalcular** `diet` (pelos sinalizadores `vegetarian_ok` e `vegan_ok`). Divergência: `422 diet_mismatch`. Ingrediente inexistente no catálogo: `422 unknown_ingredient` (nas Fases 0 e 1 não existe modo `unresolved`).
   - Etiquetas de dieta desabilitadas (`sem-gluten`, `sem-lactose`): `422 diet_tag_disabled`.
   - Dificuldade: calcular a esperada pelos passos e por `generationMeta.technique_flags` (critérios de `04`, seção 6.3). Se a enviada divergir: `422 difficulty_mismatch`.
   - Subcategoria, fase, escopo, interruptor e limites (Etapa 2).
   - Persistir também em `recipe_ingredients`, mantendo o JSON legado `ingredients` preenchido para o front atual. Preencher o array legado `recipes.tags` além das tabelas novas. `author_id` padrão: Equipe Chocolícia.
4. **Resposta** `201 {id, slug, status, url}` e erros no formato `{"error": {"code", "message", "details": []}}`, com os códigos HTTP da tabela da seção 11.
5. **Endpoints de leitura** (seção 9), aceitando token `draft` ou `publish`, com `Cache-Control: no-store`: `GET /api/taxonomy`, `GET /api/catalog/ingredients`, `GET /api/coverage`, `GET /api/content/lookup`, `GET /api/recipes/:slug/status`.
6. **`POST /api/articles`** (seção 8): validação por tipo (dica exige `tipTopic` válido e habilitado pela fase; `subcategorySlug` é opcional em dica), `sources` obrigatório em `feature` e `technique`, tags, e `relatedTopics` resolvidos em `content_relations` por tags, subcategoria e título (temas sem correspondência são ignorados e registrados em log). Mesma regra provisória de imagem. Mesmos escopos, limites e idempotência.
7. **Contrato canônico:** exportar JSON Schema (`zod-to-json-schema` ou equivalente) para `contracts/recipe.v1.schema.json` e `contracts/article.v1.schema.json`, com o script `npm run contracts:export` e um teste que falha se os arquivos estiverem desatualizados. Incluir `contracts/examples/recipe.v1.example.json` (exemplo ilustrativo da seção 6.3).

## Etapa 4 - Testes (obrigatórios, no banco de teste)

- **Migrations:** aplicar do zero; aplicar sobre dados legados; seed duas vezes sem duplicar; contagens do seed (11, 74, 4/43/27); escolha correta do índice único conforme a versão do Postgres.
- **Autenticação:** token ausente ou inválido (401); escopo insuficiente (403); token legado como `draft`; comparação em tempo constante.
- **Controles:** interruptor falso; fase 0 com `published`; subcategoria não habilitada ou de risco não permitido; limite diário por tipo; rate limit com `Retry-After`.
- **Idempotência:** replay devolve a mesma resposta; corpo diferente com a mesma chave; expiração.
- **Contrato:** legado continua funcionando; v1 válido; versão não suportada; sem `status` gera `draft`; limites de tamanho (título, excerpt, passos, tags); corpo acima de 1 MB.
- **Validações:** ingrediente desconhecido; etiqueta desabilitada; dificuldade divergente; sanitização contra XSS preservada.
- **Leitura:** os cinco endpoints, com e sem token.
- **Artigos:** criação por tipo; `sources` obrigatório; relacionamentos resolvidos e temas sem correspondência.
- **Contrato exportado:** o teste de desatualização.
- **Regressão:** `generate-daily` e o fluxo atual não quebraram.

Todos os testes existentes precisam continuar passando. Rode lint e verificação de tipos.

## Etapa 5 - Entrega

1. `docs/agente/AUDITORIA-SITE.md`, `MIGRATIONS-RUNBOOK.md`, `INGREDIENTS-IMPORT.md` e `RELATORIO-BLOCO-1.md`.
2. O relatório deve conter: o que foi feito por item deste prompt; **desvios** do prompt e o motivo; decisões que você tomou; **tabela das variáveis de ambiente novas** (nome, padrão, descrição); endpoints novos com exemplos `curl` **sem tokens reais**; comandos para aplicar em produção (**não executados**); riscos; pendências; perguntas abertas.
3. Atualize `.env.example` com as variáveis novas, sem valores.
4. Descrição do PR com resumo, riscos e passos de reversão.

## Definição de pronto

- [ ] Etapa 0 entregue e premissas confirmadas (ou desvios relatados).
- [ ] Migrations aplicam do zero e sobre dados legados, em banco de teste, sem alterar ou remover nada existente.
- [ ] Seed: 11 categorias, 74 subcategorias e tags; idempotente.
- [ ] Tokens por escopo, interruptor, fase, limites, rate limit e idempotência funcionando e testados.
- [ ] Padrão de `status` é `draft`, com os chamadores internos já enviando `status` explícito.
- [ ] Contrato v1, endpoints de leitura e `POST /api/articles` funcionando e testados.
- [ ] Contrato exportado em `contracts/` com teste de desatualização.
- [ ] Nenhum segredo lido, impresso ou commitado; nada executado em produção.
- [ ] Relatório e runbook completos.

## Critérios de parada

Pare e relate, sem continuar, se: `recipes` ou as rotas forem muito diferentes do esperado; houver autenticação de administrador incompatível com o desenho; a troca do padrão de `status` quebrar algum chamador que você não consiga atualizar; ou a única forma de validar for usar o banco de produção.

## O que NÃO fazer neste bloco

Download ou geração de imagem (Bloco 2); denúncias, endpoints administrativos, arquivamento em lote e disjuntor por receita (Bloco 3); qualquer mudança visual, avisos na página, JSON-LD, sitemap e URLs (Bloco 4); desativar o cron interno; preencher o catálogo de ingredientes; tabelas do banco do agente; aplicar qualquer coisa em produção.
