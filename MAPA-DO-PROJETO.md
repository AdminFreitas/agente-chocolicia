# Mapa do projeto — agente DigitalTech

Mapa estático produzido por inspeção do repositório. Arquivos sensíveis (`.env`) não foram lidos; nomes de variáveis abaixo vêm apenas de referências no código e nos workflows.

## 1. Estrutura (até três níveis)

```text
.
├── rodar_agente.py / workflow.py       entradas de CLI e GitHub Actions
├── app.py / api.py                      APIs FastAPI e painel
├── agents/                              pesquisa, edição, revisão, SEO e publicação
│   ├── pesquisador.py
│   ├── editor.py / editor_chefe.py
│   ├── revisor.py / seo.py / publisher.py
│   └── backlog/                          agentes planejados (ebook, vídeo, social etc.)
├── pipeline/                            orquestração de artigos, notícias e publicação
├── services/                            LLM, GitHub, imagens e Ollama
├── repositories/                        acesso SQL a artigos, notícias, produtos e chats
├── config/                              settings e conexão SQLAlchemy
├── prompts/ / templates/                prompts e modelos Markdown
├── scripts/                             diagnóstico, setup, testes e camada TypeScript
├── social/ / passo1-instagram/          publicadores sociais e integrações parciais
├── tests/                               testes automatizados
├── .github/workflows/                   agendas de geração
├── content/ / output/                   conteúdo e imagens gerados
└── requirements.txt / Dockerfile       dependências e empacotamento
```

## 2. Arquivos de código principais

| arquivo | finalidade, funções/classes principais | serviços externos | variáveis de ambiente (nomes) |
|---|---|---|---|
| `rodar_agente.py` | `rodar_artigo` escolhe categoria/tema; `rodar_noticia` chama o pipeline; CLI retorna exit code. | banco, LLM, GitHub via pipelines | nenhuma direta |
| `workflow.py` | `main` seleciona notícia, artigo ou ambos. | GitHub Actions | nenhuma direta |
| `pipeline/gerar_artigos.py` | `gerar_e_processar_artigo`: editor → revisor → imagem → SEO → banco → GitHub. | LLM, provedores de imagem, PostgreSQL/Neon, GitHub | indiretas |
| `pipeline/gerar_noticias.py` | RSS → deduplicação/pauta → editor → revisão/SEO → `og:image` → banco → GitHub. | RSS, HTTP, LLM, PostgreSQL/Neon, GitHub | indiretas |
| `agents/pesquisador.py` | `pesquisar_tema`, `pesquisar_noticias`, `sugerir_tema`; dataclasses `BriefingEvergreen` e `CandidatoNoticia`. | LLM e feeds RSS | nenhuma direta |
| `agents/editor.py` | `gerar_artigo_base`/`gerar_noticia_base`; monta prompts e parseia JSON/Markdown. | LLM | nenhuma direta |
| `agents/editor_chefe.py` | `EditorChefe.montar_pauta`; score, recência e deduplicação de notícias. | nenhum direto | nenhuma |
| `agents/revisor.py` | `revisar_artigo`; prompt e validação da resposta. | LLM | nenhuma direta |
| `agents/seo.py` | `otimizar_seo`; extrai/valida SEO, GEO, tags e fallbacks. | LLM | nenhuma direta |
| `agents/publisher.py` | `salvar_artigo`, `publicar`, montagem de frontmatter e publicação. | banco e GitHub | `AGENTE_AUTOR_ID` via repository |
| `services/llm_service.py` | prompts, parse, slug e `gerar_texto*`; cadeia configurável de provedores. | Ollama e APIs de LLM | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `HUGGINGFACE_API_KEY`, `GROK_API_KEY`, `PERPLEXITY_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`, `TOGETHER_API_KEY`, `KIMI_API_KEY`, `MOONSHOT_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_URL`, `OLLAMA_MODEL`, `*_MODEL`, `FALLBACK_ORDER`, `KIMI_BASE_URL`, `MOONSHOT_BASE_URL`, `OPENROUTER_BASE_URL`, `OPENROUTER_SITE_URL`, `OPENROUTER_APP_NAME` |
| `services/ollama_service.py` | cliente alternativo `OllamaService`. | Ollama | `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODEL`, `OLLAMA_NUM_THREADS`, `OLLAMA_TIMEOUT`, `OLLAMA_NUM_PREDICT`, `OLLAMA_NUM_CTX` |
| `services/gemini_service.py` | cliente legado `gerar_artigo`. | Google Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| `services/github_service.py` | `publicar_artigo`/`publicar_noticia`, existência e escrita de Markdown via GitHub API. | GitHub API | `DIGITALTECH_GITHUB_TOKEN`, `GITHUB_OWNER`, `DIGITALTECH_GITHUB_REPOSITORY`, `GITHUB_BRANCH`, `GITHUB_CONTENT_PATH` |
| `services/imagem_service.py` | adaptador para capa de artigo/receita/notícia. | APIs de imagens e armazenamento | indiretas |
| `services/image_providers/*` | `ImageSelector`, quatro providers, download SSRF-safe e registro local de proveniência. | Pixabay, Pexels, Openverse, Wikimedia | `PIXABAY_API_KEY`, `PIXABAY_ENABLED`, `PEXELS_API_KEY`, `PEXELS_ENABLED`, `OPENVERSE_ENABLED`, `WIKIMEDIA_ENABLED`, `IMAGE_STORAGE_DIR` |
| `repositories/artigo_repository.py` | CRUD SQL em `artigos`; categoria, slug e status. | PostgreSQL/Neon | `AGENTE_AUTOR_ID` |
| `repositories/noticia_repository.py` | CRUD SQL em `noticias`; dedup por slug/GUID/hash; cria `imagens`. | PostgreSQL/Neon | `AGENTE_AUTOR_ID` |
| `repositories/produto_repository.py` | CRUD de `produtos`, com exclusão lógica. | PostgreSQL/Neon | nenhuma |
| `config/database.py` | constrói engine e `SessionLocal`, dependência `get_db`. | PostgreSQL/SQLAlchemy | `SKIP_DOTENV`, `DATABASE_URL`, `DB_NAME`, `POSTGRES_DB`, `DB_USER`, `POSTGRES_USER`, `DB_PASSWORD`, `POSTGRES_PASSWORD`, `DB_HOST`, `DB_PORT` |
| `models.py` | modelo legado `Conteudo` e setup SQLite `agente_digital.db`. | SQLite/SQLAlchemy | nenhuma |
| `app.py` / `api.py` | endpoints de saúde, dashboard, CRUD, geração e publicação; `api.py` também normaliza IDs compostos. | FastAPI e banco | dependências indiretas |
| `scripts/*.py` | setup/diagnóstico, testes dos providers de imagem e verificação de LLM. | APIs, banco e Ollama | conforme cada script |
| `scripts/agente/*.ts` | camada TypeScript paralela: busca, geração, imagem, publicação e cliente Ollama. | Ollama e APIs definidas nos scripts | conforme cada script |

Arquivos `.bak`, `agents/backlog/*`, módulos sociais e `models.py` parecem não participar do caminho principal confirmado.

## 3. Fluxo de execução

### Artigo evergreen

1. `rodar_agente.py --artigo` escolhe uma das categorias técnicas e consulta títulos recentes.
2. `pesquisador.sugerir_tema` usa LLM e, em falha, tema fallback.
3. `gerar_e_processar_artigo` chama `editor.gerar_artigo_base`.
4. Confere slug no banco em sessão curta.
5. `revisor.revisar_artigo`, `imagem_service.buscar_imagem_capa` e `seo.otimizar_seo` enriquecem o artigo.
6. `publisher.salvar_artigo` grava `artigos`.
7. Com publicação imediata, `publisher.publicar` monta Markdown, grava no GitHub e marca o artigo como publicado.

### Notícia

1. `rodar_agente.py --noticia` chama `pesquisar_noticias`.
2. São lidos TechCrunch, The Verge, Ars Technica Technology Lab e Hacker News RSS.
3. O pesquisador filtra spam/fora de tecnologia, calcula recência, confiabilidade, veracidade e similaridade.
4. `EditorChefe` elimina duplicatas e monta a pauta priorizada.
5. Para até três itens, `editor.gerar_noticia_base` gera o texto e o slug é checado no banco.
6. Revisor e SEO processam o texto; a pipeline baixa a fonte e extrai `og:image`.
7. `NoticiaRepository.criar` grava `noticias` e, se houver imagem, `imagens`.
8. Com publicação imediata, `publicar_noticia` escreve no GitHub e atualiza status.

## 4. Banco de dados

O caminho ativo usa tabelas existentes no PostgreSQL/Neon e SQL textual: `artigos` (id, slug, título, conteúdo, categoria, status, imagem/metadados, autor, datas), `noticias` (campos equivalentes mais `fonte`, `url_fonte`, `rss_guid`, hash e metadados LLM/imagem), `imagens` (notícia, URL, alt, principal), `categorias` (id/nome), `produtos` e possivelmente `chats`/compartilhamentos sociais.

* `ArtigoRepository`: lê/grava `artigos` e lê `categorias`; `publisher` grava e publica.
* `NoticiaRepository`: lê/grava `noticias`, lê `categorias`, grava/atualiza `imagens`.
* `ProdutoRepository`: CRUD em `produtos`; endpoints de `app.py`.
* `services/image_providers/database.py`: cria/usa a tabela SQLite local `imagens_banco`, separada do PostgreSQL.
* `models.py`: define `conteudos` no SQLite legado; não há evidência de uso pelo pipeline principal.

## 5. Modelos de IA e prompts

`services/llm_service.py` usa `FALLBACK_ORDER`, cujo padrão é: Ollama → Gemini → Groq → OpenAI → Claude → DeepSeek → Grok → Perplexity → Hugging Face → Mistral → Cohere → Together → Kimi → OpenRouter. Os modelos são configuráveis por `*_MODEL`; defaults aparecem no mesmo arquivo. Cada provedor recebe tentativas configuráveis. `services/ollama_service.py` é uma implementação paralela/legada.

Prompts principais estão embutidos em `agents/pesquisador.py`, `agents/editor.py`, `agents/revisor.py`, `agents/seo.py` e `services/llm_service.py`. Existem também `prompts/artigo.md`, `noticia.md`, `revisao.md`, `seo.md` e `sistema.md`, mas o uso direto pelo caminho Python não ficou comprovado.

## 6. Pesquisa e imagens

Pesquisa de notícias: quatro RSS listados acima; HTTP `requests` busca `og:image` da matéria original. Pesquisa evergreen e sugestão de tema usam LLM, sem um crawler web ativo no caminho confirmado.

Imagens de capa de artigos: `ImageSelector` tenta Pixabay, Pexels, Openverse e Wikimedia, nessa ordem, com queries derivadas do título/categoria e fallback `chocolate dessert`; baixa, valida SSRF, redimensiona/processa e registra proveniência. Notícias usam preferencialmente a `og:image` original e não a busca genérica.

## 7. Publicação

O agente grava primeiro no PostgreSQL/Neon. A publicação escreve um Markdown via GitHub Contents API no repositório configurado por `GITHUB_OWNER` + `DIGITALTECH_GITHUB_REPOSITORY`, em `GITHUB_CONTENT_PATH`, com subpastas de artigos/notícias. O deploy do site é externo ao agente e presumivelmente acionado pelo repositório. API/painel também permitem publicação manual.

## 8. Agendamento e testes

* `.github/workflows/gerar-artigos.yml`: cron `0 9,17 * * *` UTC, executa artigo e depois notícia (`always`).
* `.github/workflows/gerar-noticias.yml`: cron `0 7,11,15,19 * * *` UTC, executa notícia.
* Há `workflow_dispatch`, `workflow.py` e CLI em `rodar_agente.py`.
* Testes: `tests/test_hardening.py`, `test_image_providers_real.py`, `test_pixabay_service.py` e scripts `test_phase1...4`; `scripts/run_tests_completo.py` agrega verificações.

## 9. Dependências

FastAPI/Uvicorn/Pydantic para API; SQLAlchemy e psycopg2 para banco; python-dotenv para configuração; `google-genai`, OpenAI e Anthropic para LLM; `httpx`/`requests` para HTTP; `feedparser` para RSS; `markdown` para conversão/apoio de conteúdo.

## 10. O que é específico de tecnologia/DigitalTech

* `rodar_agente.py`: categorias Inteligência Artificial, Programação, Banco de Dados, Cibersegurança, Cloud e DevOps, Desenvolvimento Web, Engenharia de Software, Hardware, Open Source e Carreira.
* `agents/pesquisador.py`: identidade DigitalTech; feeds TechCrunch, The Verge, Ars Technica e Hacker News; prompt de pauta; filtros e termos técnicos (`github`, `gitlab`, `api`, `framework`, entre outros).
* `agents/editor.py`, `revisor.py`, `seo.py`: prompts para artigos/notícias técnicas, preservação de código, links e SEO.
* `services/github_service.py`: URLs e publicação do site `digitaltech.digital`; repositório configurável, workflow define `AdminFreitas/digitaltech`.
* `pipeline/gerar_noticias.py`: User-Agent `DigitalTechBot` e fluxo de notícias.
* `services/llm_service.py`: prompt de escritor técnico brasileiro e modelos/provedores de IA.
* `services/image_providers/*`: parte reutilizada da camada Chocolícia; termos e User-Agents ainda citam Chocolícia/culinária, o que é inadequado para conteúdo DigitalTech.

## 11. Código morto ou duplicado observado

* `services/llm_service.py` e `scripts/diagnostico_llm.py` repetem lógica de fallback/parsing.
* `services/ollama_service.py` e a implementação Ollama de `llm_service.py` são paralelas.
* `services/gemini_service.py` é cliente alternativo ao fluxo central.
* `models.py`/SQLite `Conteudo` conflita conceitualmente com repositórios SQL de `artigos` e `noticias`.
* `pipeline/gerar_artigos.py.bak`, `services/*.bak`, `agents/editor.py.bak` e `pipeline/gerar_artigos.py` têm cópias de versões anteriores.
* `agents/backlog/*`, `social/*`, `passo1-instagram/*` e TypeScript em `scripts/agente/` parecem trilhas paralelas/incompletas; precisam de confirmação antes de remover.
* `pesquisador.pesquisar_tema` e arquivos em `prompts/` parecem parcialmente bypassados: a pipeline comenta a chamada de briefing e o editor recebe `briefing=None`.

## 12. Pontos de atenção

* `services/pixabay_service.py` contém fallback literal para uma chave de API; deve ser removido e a chave deve vir exclusivamente do ambiente.
* Há muitos nomes de variáveis divergentes entre workflows e código (`HF_TOKEN`/`HUGGINGFACE_API_KEY`, por exemplo); validar o contrato de configuração.
* O workflow agenda em UTC, enquanto comentários descrevem BRT; confirmar horários desejados.
* `publisher`, repositories e `github_service` gravam diretamente no banco/GitHub; falhas parciais entre banco e GitHub podem deixar status inconsistente.
* RSS e `og:image` dependem de rede e parsing regex; há fallback sem imagem, mas a disponibilidade do feed precisa de observabilidade.
* A camada de imagens usa nomes, domínios e termos de Chocolícia; separar configuração/licença e queries para DigitalTech.
* A API executa chamadas LLM potencialmente longas em endpoints síncronos; timeouts e concorrência merecem revisão.
* `api.py`, `app.py`, SQLite legado e PostgreSQL ativo oferecem superfícies duplicadas; definir uma única fonte de verdade.

## Tabela final

| arquivo | o que faz | manter / refatorar / remover (sugestão) |
|---|---|---|
| `rodar_agente.py` | entrada principal e controle de erro | manter |
| `pipeline/gerar_artigos.py` | pipeline evergreen | manter; refatorar briefing comentado |
| `pipeline/gerar_noticias.py` | pipeline RSS | manter; refatorar extração/parsing |
| `agents/pesquisador.py` | pauta, RSS e filtros | manter; separar regras DigitalTech |
| `agents/editor.py`, `revisor.py`, `seo.py` | conteúdo, revisão e SEO | manter |
| `services/llm_service.py` | fallback LLM | manter; consolidar duplicatas |
| `services/image_providers/*` | busca e proveniência de imagens | refatorar para remover herança Chocolícia |
| `repositories/*` | persistência | manter; padronizar schema/ORM |
| `models.py` | modelo SQLite legado | remover após migração confirmada |
| `services/gemini_service.py` / `ollama_service.py` | clientes alternativos | refatorar ou remover se não usados |
| `scripts/diagnostico_llm.py` | diagnóstico duplicado | manter só como ferramenta, ou consolidar |
| `agents/backlog/*` | agentes futuros | manter fora do caminho; remover apenas após confirmação |
| `*.bak` | cópias de versões anteriores | remover após backup/versionamento confirmado |
| `social/*` e `passo1-instagram/*` | integrações sociais parciais | refatorar quando houver escopo; não misturar ao pipeline |
| `prompts/*` | prompts externos | manter se forem fonte oficial; caso contrário consolidar |
