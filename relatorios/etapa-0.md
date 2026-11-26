# Relatório da Etapa 0: Pré-checagem (Somente Leitura)

Data/Hora: 2026-11-17T07:48:00-03:00  
Repositório: `agente-chocolicia`  
Branch atual: `simplificar`

---

## a) Como o `rodar_agente.py` chama o site e qual contrato usa

- **Ponto de chamada:**
  - `rodar_agente.py`, linha 10: `from runtime_adapters.cli_contract import build_services`
  - `rodar_agente.py`, linha 47: chama `build_services(...)`, que instancia o cliente do site via `runtime_adapters/compose.py` (linha 68) chamando `runtime_adapters/site.py` (função `build_site_client`).
  - `runtime_adapters/site.py`, linha 2: importa diretamente `from integration.cliente_site import ClienteSite`.
  - O pipeline real (`pipeline/gerar_receitas.py` e `pipeline/gerar_conteudo_educativo.py`) recebe `cliente_site` injetado como dependência e chama:
    - `cliente.criar_receita(...)` -> invoca `ClienteSite._criar('/api/recipes', 'recipe', ReceitaV1, ...)` (`integration/cliente_site.py`, linhas 301-303).
    - `cliente.criar_artigo(...)` -> invoca `ClienteSite._criar('/api/articles', tipo, ArtigoV1, ...)` (`integration/cliente_site.py`, linhas 304-309).
- **Contrato em uso:**
  - `contrato="v1"` (padrão em `rodar_agente.py`, linha 25 e `runtime_adapters/compose.py`, linha 37: `if contrato != "v1": raise ConfigurationError("somente v1 está implementado...")`).
  - Cabeçalho HTTP enviado: `X-Contract-Version: 1` (`integration/cliente_site.py`, linhas 35 e 238).

---

## b) Endpoint e campos exigidos pelo site

### 1. `POST /api/recipes`
- **Validador:** Modelo Pydantic `ReceitaV1` em `integration/contratos.py` (linhas 131-158):
  - `title`: str (5 a 180 chars)
  - `slug`: str opcional (slug válido)
  - `excerpt`: str (20 a 160 chars)
  - `intro`: str opcional
  - `subcategorySlug`: str (slug da subcategoria no site)
  - `secondarySubcategorySlugs`: list[str] (até 2)
  - `prepTimeMin`: int (1 a 1440)
  - `cookTimeMin`: int opcional (0 a 1440)
  - `restTimeMin`: int opcional (0 a 10080)
  - `servings`: int (1 a 500)
  - `yieldLabel`: str opcional
  - `difficulty`: Literal["Fácil", "Média", "Difícil"]
  - `ingredients`: list[SecaoIngredientesV1] (mínimo 1 seção, cada uma com `name` e `items`, onde cada item possui `name`, `quantity`, `unit`, `ingredientSlug` opcional)
  - `steps`: list[PassoV1] (mínimo 4 passos com `instruction`)
  - `tips`: list[str] (até 5)
  - `storageNotes`: str opcional
  - `faq`: list[FaqV1] (até 12 perguntas e respostas)
  - `tags`: list[str] (até 12 slugs)
  - `cover`: Union[CoverStock, CoverGenerate] (modo `"stock"` com `provider`, `sourceImageUrl`, `sourcePageUrl`, `author`, `license`, `attributionText`)
  - `coverImageAlt`: str (8 a 240 chars)
  - `status`: Literal["draft", "published"] (padrão "draft")
  - `aiModel`: str
  - `generationMeta`: objeto com `run_id`, `topic_slug`, `prompt_version`, `phase`, `sources`, `validators_version`

### 2. `POST /api/articles`
- **Validador:** Modelo Pydantic `ArtigoV1` em `integration/contratos.py` (linhas 185-203):
  - `type`: Literal["technique", "tip", "feature"] (dica usa `"tip"`)
  - `title`: str (5 a 180 chars)
  - `excerpt`: str (20 a 160 chars)
  - `subcategorySlug`: str opcional (obrigatório se não for dica)
  - `tipTopic`: str opcional (obrigatório se for `"tip"`)
  - `bodyMd`: str (conteúdo em Markdown)
  - `sources`: list[FonteArtigoV1]
  - `tags`: list[str]
  - `relatedTopics`: list[str] (2 a 6 itens se preenchido)
  - `cover`: Cover (mesmo de receitas)
  - `coverImageAlt`: str (8 a 240 chars)
  - `status`: Literal["draft", "published"] (padrão "draft")
  - `aiModel`: str
  - `generationMeta`: objeto GenerationMetaV1

---

## c) Lista das variáveis de ambiente lidas pelo agente (somente nomes)

Conforme mapeado em `runtime_adapters/config.py`, `rodar_agente.py` e `.github/workflows/gerar-receitas.yml`:

1. `AGENT_ENABLED`
2. `AGENT_ENV`
3. `AGENT_RUN_ID`
4. `AGENT_REQUEST_TIMEOUT`
5. `AGENT_PHASE`
6. `AGENT_DATABASE_URL` / `DATABASE_URL_AGENTE`
7. `SITE_BASE_URL` (ou `SITE_BASE_URL_PROD` / `SITE_BASE_URL_PREVIEW`)
8. `SITE_TOKEN_DRAFT` (ou `SITE_TOKEN_DRAFT_PROD` / `SITE_TOKEN_DRAFT_PREVIEW`)
9. `SITE_TOKEN_PUBLISH` (ou `SITE_TOKEN_PUBLISH_PROD`)
10. `SITE_PHASE`
11. `SITE_CONTRACT`
12. `SEARCH_PROVIDER` / `PESQUISA_PROVEDOR`
13. `SEARCH_MAX_QUERIES`
14. `SEARCH_MAX_RESULTS`
15. `BRAVE_SEARCH_API_KEY` / `PESQUISA_API_KEY`
16. `LLM_PROVIDER`
17. `LLM_API_KEY`
18. `LLM_BASE_URL`
19. `LLM_MODEL_CREATION`, `LLM_FAMILY_CREATION`
20. `LLM_MODEL_REPAIR`, `LLM_FAMILY_REPAIR`
21. `LLM_MODEL_REVIEW`, `LLM_FAMILY_REVIEW`
22. `LLM_MODEL_SEO`, `LLM_FAMILY_SEO`
23. `LLM_MODEL_EXTRACTION`, `LLM_FAMILY_EXTRACTION`
24. `LLM_MODEL_VISION`, `LLM_FAMILY_VISION`
25. `PIXABAY_API_KEY`
26. `PIXABAY_ENABLED`
27. `PEXELS_API_KEY`
28. `PEXELS_ENABLED`
29. `OPENVERSE_ENABLED`
30. `WIKIMEDIA_ENABLED`
31. `IMAGE_STORAGE_DIR`
32. `PUBLICAR_AUTOMATICO` (para workflow do GitHub Actions)

---

## d) Provedores de busca e LLM em nuvem configuráveis

- **Busca na Web:**
  - Provedor configurado: **Brave Search API** (`runtime_adapters/search.py` via `BRAVE_SEARCH_API_KEY`).
  - Também há serviço legado `services/busca_service.py` que suporta Brave e DuckDuckGo/Tavily.
- **LLM em nuvem:**
  - O adapter `runtime_adapters/llm.py` implementa `OpenAICompatibleGenerator` que aceita qualquer endpoint compatível com a API OpenAI (Chat Completions: `base_url + "/chat/completions"`).
  - Funciona diretamente com:
    - **Groq** (`https://api.groq.com/openai/v1` - possui tier gratuito)
    - **Google Gemini via endpoint OpenAI** (`https://generativelanguage.googleapis.com/v1beta/openai/`)
    - **OpenRouter** (`https://openrouter.ai/api/v1`)
    - **OpenAI** (`https://api.openai.com/v1`)
  - Em `services/llm_service.py` e `services/gemini_service.py`, também há suporte nativo para Gemini e Ollama local.

---

## Status da Etapa 0: CONCLUÍDA (Sem impedimentos bloqueantes)
- A arquitetura está identificada.
- Os contratos `POST /api/recipes` e `POST /api/articles` estão especificados em `integration/contratos.py`.

