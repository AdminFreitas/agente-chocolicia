# Pipeline de receitas — modo `legacy`

Pipeline Python (pesquisa → criação → validação → revisão → SEO → capa → publicação) que
publica **direto em produção** pelo `POST /api/recipes` que o site tem hoje. Vive no pacote
isolado `agente_receitas/` para não colidir com os módulos da `main` (dicas/artigos seguem em
`rodar_agente.py`). Vem do PR #3 (`integracao/publicacao-manual`), sem a reorganização do PR.

## Por que `legacy`
O pipeline do PR foi escrito para o contrato `v1`, que depende de `/api/taxonomy`,
`/api/catalog/ingredients`, `/api/coverage`, `/api/content/lookup`, `/api/uploads` e
`POST /api/recipes/{slug}/publish`. O site atual só tem `GET/POST /api/recipes` e
`/api/recipes/generate-daily`. O modo legacy **não** chama as rotas ausentes.

## Ativação (explícita)
- `SITE_CONTRACT=legacy` — nunca é inferido. Em produção, sem isso o CLI recusa.
- `python rodar_receita.py --target production --assunto automatico`
- Exige `AGENT_ENV=production`, `AGENT_PHASE>=1`, `DRY_RUN=false`, `AGENT_PUBLISHING_ENABLED=true`,
  `SITE_BASE_URL=https://www.chocolicia.site`.
- Workflow: `.github/workflows/publicar-receita-legacy.yml` (`workflow_dispatch`; cron pronto,
  comentado até a validação).

## Contrato real do site (`server/recipesRoutes.ts`, `shared/recipes.ts`)
- Autenticação: `Authorization: Bearer $RECIPES_AGENT_TOKEN` (o mesmo valor da env do Vercel do site).
  Sem a env no site → 503; token errado → 401.
- Corpo (JSON, ≤ 1 MB), campos validados pelo zod do site: `title` (5–180), `excerpt` (20–160),
  `category` (enum fixo de 7 categorias), `coverImageUrl` (URL http/https), `coverImageAlt` (≥ 8),
  `ingredients` (seções com itens `name/quantity/unit`), `steps` (≥ 2, `instruction`),
  `prepTimeMin`, `cookTimeMin`, `servings`, `difficulty` (`Fácil|Média|Difícil`),
  `status` (`published` por padrão no site; o pipeline envia `published`).
- `subcategorySlug` não é enviado (o site recusa se não pertencer à categoria).
- Duplicata de título → 409 (slug único). Sem `Idempotency-Key` no site.

## Diferenças em relação ao v1 / ao PR
- Categoria vem do enum do site (`SiteCatalogLegado.selecionar_categoria_legada`).
- `SiteCatalogLegado` não usa rede; marca `needs_label_check` (nenhuma etiqueta de dieta é inferida).
- Capa: somente banco de imagens (Pexels/Pixabay/Openverse/Wikimedia), porque não há `/api/uploads`;
  `AGENT_IMAGE_GENERATION_ENABLED=false`.
- Removido o bloqueio incondicional de produção por "tetos de custo" do `compose.py` do PR; no
  legacy o teto efetivo é **uma receita por execução**. O v1 em produção continua bloqueado.
- Duplicatas: quando `AGENT_DATABASE_URL` está configurada, `claim_topic` mantém histórico persistente de pautas e execuções. Sem essa variável, o pipeline usa histórico em memória e a API do site continua sendo a proteção final contra slug duplicado (HTTP 409). Nesse modo, não há histórico persistente de execuções nem deduplicação de imagens entre execuções.

## Segredos (só os nomes)
`RECIPES_AGENT_TOKEN`, `BRAVE_SEARCH_API_KEY`, ao menos uma chave de LLM
(`GEMINI_API_KEY`/`GROQ_API_KEY`/`OPENROUTER_API_KEY`) e uma de imagens (`PEXELS_API_KEY`/`PIXABAY_API_KEY`).
O job usa `environment: production`; se os segredos estiverem no ambiente do repositório, é o que os expõe.

## Agendadores que geram receitas (evitar publicação em duplicidade)
1. Vercel Cron do site (`vercel.json`): `/api/recipes/generate-daily` às `0 13 * * *` (10:00 BRT).
2. `.github/workflows/gerar-receitas.yml` (main): `0 11 * * *`, só roda com `AGENT_ENABLED=true`.
3. Este workflow, quando o `schedule` for descomentado.
Ative apenas um deles.
