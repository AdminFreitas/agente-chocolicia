# Diagnóstico Chocolícia — funil Geração → Persistência → Integração → Publicação

Gerado em: 2026-11-19 07:22:41
- Site: `C:\Users\miche\Projetos\chocolicia`
- Agente: `C:\Users\miche\Projetos\agente-chocolicia`

## Resumo do funil

- ✅ **1) Geração — o agente consegue gerar uma receita?**
- ❌ **2) Persistência — agente e site têm onde guardar o conteúdo?**
- ❌ **3) Integração — agente e site falam o mesmo contrato?**
- ⚠️ **4) Publicação — o site expõe o que recebe?**

## Detalhe

### 1) Geração — o agente consegue gerar uma receita?

- ✅ **services/llm_service.py chama algum provedor de LLM** — Encontrada referência a um provedor de LLM ou a uma função gerar_texto  
  _Fonte: PLANO-REFATORACAO-AGENTE.md Passo 2, item 5_
- ✅ **agents/editor.py (Chef IA / criação de receita)** — Presente  
  _Fonte: 01-ARQUITETURA.md §11 e §12; PLANO-REFATORACAO-AGENTE.md Passo 6_
- ✅ **Arquivos de prompt versionados em prompts/** — Encontrados: base.md, dica.md, extracao.md, receita.md, reparo.md, revisor.md, seo.md  
  _Fonte: 03-PROMPT-SISTEMA.md §2 e §5_
- ✅ **Pipeline executável (gerar_receitas.py)** — Encontrado: pipeline/gerar_receitas.py  
  _Fonte: 01-ARQUITETURA.md §7.2 e §11; PLANO-REFATORACAO-AGENTE.md Passo 9_
- ✅ **config/modelos_aprovados.json** — Presente  
  _Fonte: 01-ARQUITETURA.md §12 e §15_

### 2) Persistência — agente e site têm onde guardar o conteúdo?

- ✅ **Banco próprio do agente (agent_runs/agent_generations)** — Encontrado: [WindowsPath('C:/Users/miche/Projetos/agente-chocolicia/db/schema_agente.sql')]  
  _Fonte: 04-ESTRUTURA-CONTEUDO.md §8.9; PLANO-REFATORACAO-AGENTE.md Passo 3_
- ✅ **Tabela `recipes` no site (drizzle/schema.ts)** — Definida  
  _Fonte: drizzle/schema.ts_
- ✅ **server/recipeDb.ts expõe insertRecipe()** — Presente  
  _Fonte: server/recipeDb.ts_
- ❌ **Tabelas novas da taxonomia (categories/ingredients/articles)** — Ausentes em drizzle/schema.ts: categories, ingredients, recipe_ingredients, articles — Bloco 1 de CODEX-01-SITE-BASE.md ainda não foi aplicado ao site  
  _Fonte: 04-ESTRUTURA-CONTEUDO.md §8; CODEX-01-SITE-BASE.md Etapa 1_

### 3) Integração — agente e site falam o mesmo contrato?

- ✅ **integration/cliente_site.py (lado do agente)** — Presente  
  _Fonte: 01-ARQUITETURA.md §11; PLANO-REFATORACAO-AGENTE.md Passo 4_
- ✅ **integration/adaptador_receita.py (lado do agente)** — Presente  
  _Fonte: 01-ARQUITETURA.md §11; PLANO-REFATORACAO-AGENTE.md Passo 4_
- ✅ **Variáveis de ambiente do agente para falar com o site** — Todas presentes  
  _Fonte: 06-INTEGRACAO.md §3_
- ❌ **Token do agente no site ainda é único (sem escopo draft/publish)** — server/recipesRoutes.ts valida contra process.env.RECIPES_AGENT_TOKEN — um token só, sem os escopos draft/publish que 06-INTEGRACAO.md §4 e CODEX-01-SITE-BASE.md Etapa 2 exigem. Se o agente enviar o payload novo (contrato v1) para este endpoint, a validação Zod atual (que ainda espera `category` do enum antigo e `coverImageUrl` obrigatório) muito provavelmente vai rejeitar com 400.  
  _Fonte: 06-INTEGRACAO.md §4 e §6; server/recipesRoutes.ts_
- ❌ **Site lê o cabeçalho X-Contract-Version** — Não encontrado — sem isso o site não consegue distinguir o payload legado do contrato v1 (06-INTEGRACAO.md §6.1), então qualquer envio no formato novo cai na validação antiga  
  _Fonte: 06-INTEGRACAO.md §6.1 e §14_
- ✅ **Schema do site já aceita subcategorySlug** — Confirmado  
  _Fonte: 06-INTEGRACAO.md §6.2_

### 4) Publicação — o site expõe o que recebe?

- ✅ **POST /api/recipes existe** — Encontrado  
  _Fonte: server/recipesRoutes.ts_
- ⚠️ **Sitemap inclui só conteúdo `published`** — Não confirmado por busca estática — revisar manualmente  
  _Fonte: 05-SEO.md §10.1_
- ⚠️ **Cron interno `generate-daily` ainda ativo** — Ainda ativo — é esperado até o agente entrar em produção (01-ARQUITETURA.md §7.3); mas se o agente também estiver tentando publicar, as duas fontes podem gerar receitas duplicadas ou brigar pelo limite diário  
  _Fonte: 01-ARQUITETURA.md §7.3_

> Auditoria estática: só lê arquivos. `FALTA` indica padrão/arquivo esperado e não encontrado; `ATENÇÃO` indica algo que merece revisão manual, não necessariamente um erro; `NÃO VERIFICADO` indica que a checagem automática não pôde concluir (e nesse caso o script não quebra: só marca o item e segue).