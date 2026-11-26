# Relatório da Etapa 2: Envio Real como Rascunho (Parada Obrigatória de Configuração)

Data/Hora: 2026-11-17T07:55:00-03:00  
Repositório: `agente-chocolicia`  
Branch: `simplificar`

---

## 1. Descoberta Fundamental da Auditoria Cruzada (Site ↔ Agente)

Examinamos diretamente o código-fonte em execução no site (`c:\Users\miche\Projetos\chocolicia`):

1. **Endpoint existente no site:**
   - O site possui o endpoint `POST /api/recipes` implementado em `server/recipesRoutes.ts` (linhas 103-145).
   - O site **NÃO** possui o contrato v1 (`subcategorySlug`, `cover.mode = stock/generate`), e **NÃO** possui `POST /api/articles`.
   - O schema real exigido pelo site é o **legado** definido em `shared/recipes.ts` (`recipeInputSchema`):
     - `title`: string (min 5, max 180)
     - `excerpt`: string (min 20, max 160)
     - `category`: Enum `"Bolos"`, `"Brigadeiros e docinhos"`, `"Tortas"`, `"Sobremesas"`, `"Chocolates"`, `"Festas e buffet"`, `"Datas especiais"`
     - `coverImageUrl`: URL válida de imagem HTTP/HTTPS
     - `coverImageAlt`: string (min 8, max 240)
     - `ingredients`: seções com `name` e `items` (`name`, `quantity`, `unit`)
     - `steps`: lista de passos com `instruction` (mínimo 2 passos)
     - `prepTimeMin`, `cookTimeMin`, `servings`, `difficulty`
     - `status`: `"draft"` ou `"published"` (padrão `"published"`, mas aceita `"draft"`)

2. **Autenticação no site:**
   - Em `server/recipesRoutes.ts`, linha 104:
     ```typescript
     const expected = process.env.RECIPES_AGENT_TOKEN;
     if (!expected) {
       res.status(503).json({ error: "A publicação por agente não está configurada." });
       return;
     }
     if (!timingSafeTokenEquals(readBearer(req), expected)) {
       res.status(401).json({ error: "Não autorizado." });
       return;
     }
     ```
   - No `.env` local do site (`c:\Users\miche\Projetos\chocolicia\.env`), a variável `RECIPES_AGENT_TOKEN` **não está configurada**.
   - Na Vercel (em produção), é necessário conferir se a variável `RECIPES_AGENT_TOKEN` foi cadastrada com o mesmo valor que será fornecido ao agente como `SITE_TOKEN_DRAFT`.

---

## 2. Teste Isolado (`testa_site.py`)

Criamos e testamos o `testa_site.py` que envia exatamente o payload compatível com o schema do site (`recipeInputSchema`).

- Execução em modo `--dry-run`:
  - **Comando:** `.venv\Scripts\python.exe testa_site.py --dry-run`
  - **Código de saída:** `0`
  - **Resultado:** Payload 100% validado contra o Zod schema de `shared/recipes.ts`.

---

## 3. CONDIÇÃO DE PARADA OBRIGATÓRIA (Regra 4 do Prompt)

Para o disparo real da **Etapa 2** (`POST /api/recipes` com `status: "draft"`):

> **Atenção:** Como o agente roda em isolamento e nunca lê segredos nem grava senhas em arquivo:
> 
> Precisamos que você defina temporariamente no terminal as variáveis:
> ```powershell
> $env:SITE_BASE_URL = "https://www.chocolicia.com"  # ou a URL do seu site / preview na Vercel
> $env:SITE_TOKEN_DRAFT = "o_token_definido_na_vercel" # o valor configurado em RECIPES_AGENT_TOKEN na Vercel
> ```
> E execute o teste direto:
> ```powershell
> .venv\Scripts\python.exe testa_site.py
> ```

Assim que você rodar esse comando e colar a resposta (sem o token), teremos o código HTTP exato (`201` de sucesso ou o erro da Vercel) para dar seguimento imediato às Etapas 3, 4 e 5!

