# agente-chocolicia

Repositório do agente de conteúdo do site Chocolícia.

## Geração local com Ollama e envio para o site

O conector local é `rodar_conteudo.py`. Ele gera receitas ou dicas com Ollama e, quando explicitamente habilitado, envia para a API versionada do site. A execução é **dry-run por padrão** e cria rascunhos por padrão; publicação exige opção explícita e token de escopo `publish`.

### Pré-requisitos e configuração

1. Instale e inicie [Ollama](https://ollama.com/) na máquina que executará o script e baixe um modelo, por exemplo:

   ```bash
   ollama pull mistral:7b-instruct
   ```

2. Instale as dependências do agente e copie `.env.example` para `.env`:

   ```bash
   python -m pip install -r requirements.txt
   cp .env.example .env
   ```

3. Configure no `.env`:
   - `OLLAMA_HOST`: endereço do serviço Ollama, normalmente `http://localhost:11434`.
   - `OLLAMA_MODEL`: nome idêntico ao modelo baixado com `ollama pull`.
   - `CHOCOLICIA_API_URL`: origem do site, sem segredo; padrão `https://www.chocolicia.site`.
   - `CHOCOLICIA_TOKEN_DRAFT` ou `CHOCOLICIA_TOKEN_PUBLISH`: tokens Bearer com o escopo correspondente. `CRON_SECRET` é aceito como fallback de compatibilidade, mas prefira os tokens de escopo do contrato do site.
   - `CHOCOLICIA_COVER_JSON`: JSON com a origem de imagem exigida pela API. Use uma fonte autorizada pelo site; o agente não inventa créditos nem URLs.
   - `AGENT_ENABLED=true` habilita chamadas de rede para publicação. Mantenha `false` para geração local e dry-run.

   Exemplo de configuração de capa (use dados reais e verificados do provedor, não copie os valores fictícios):

   ```json
   {"mode":"stock","provider":"pexels","sourceImageUrl":"https://...","sourcePageUrl":"https://...","author":"...","license":"...","attributionText":"..."}
   ```

4. Gere e confira o payload sem enviá-lo:

   ```bash
   python rodar_conteudo.py --tipo receita --tema "Brigadeiro de colher" --subcategoria brigadeiros-e-docinhos
   python rodar_conteudo.py --tipo dica --tema "Como evitar que a ganache talhe" --assunto preparo
   ```

   Os arquivos JSON são gravados em `output/`. Para enviar um **rascunho**, habilite `AGENT_ENABLED=true` e acrescente `--send`. Para publicar, configure `CHOCOLICIA_TOKEN_PUBLISH` e use também `--publish`. A publicação direta deve ser usada apenas quando validações do site e operação estiverem habilitadas.

### Contrato e limites importantes

O conector segue o contrato do repositório em `docs/06-INTEGRACAO.md`: receitas vão para `POST /api/recipes`, dicas para `POST /api/articles`, com `X-Contract-Version`, `X-Request-Id`, `Idempotency-Key` e Bearer. Os campos são convertidos para o contrato documentado (por exemplo, `excerpt`, `prepTimeMin`, `subcategorySlug` e ingredientes em seções). A dificuldade segue os valores documentados pelo site (`Fácil`, `Média`, `Difícil`).

O contrato v1 documentado não aceita `meta_description` ou `schema_org` como campos extras na API. O agente gera a descrição SEO como `excerpt` e grava JSON-LD Schema.org Recipe localmente em `output/<slug>.schema.jsonld`, sem incluir campos não contratados no POST. Confira/atualize a API do site antes de enviar campos adicionais.

**Ollama em GitHub Actions:** um runner hospedado pelo GitHub não consegue acessar `localhost` da sua máquina. Este modo é para execução local; para Actions, use um runner self-hosted com Ollama instalado e mantenha segredos em Actions Secrets. Os workflows agendados existentes não foram alterados para expor tokens ou acessar um serviço local.

Falhas de inferência e de rede são registradas, resultam em `status: failed` no resultado salvo e não geram POST inválido. A camada de cliente repete falhas temporárias do servidor/conexão com a mesma chave de idempotência; erros 4xx não são repetidos.


## Acionamento diário de receitas no site

O workflow `.github/workflows/gerar-receitas.yml` agora aciona o backend do site por meio de `scripts/gerar_receita_blog.py`. A geração de texto, imagem, armazenamento e persistência continuam exclusivamente no site; o agente não acessa o banco Neon do site.

Configure em **Settings → Secrets and variables → Actions**:
- Secret obrigatório `CRON_SECRET`: mesmo valor definido no projeto Vercel do site.
- Variable opcional `CHOCOLICIA_SITE_URL`: origem HTTPS do site. O padrão é `https://www.chocolicia.site`.

O workflow mantém o horário existente (08h de Brasília) e só executa quando a variável `AGENT_ENABLED` estiver como `true`. O acionamento manual inicia em `dry_run=true`; desmarque apenas para enviar o POST real.

**Evite geração duplicada:** o site possui cron próprio em `vercel.json` para `/api/recipes/generate-daily`. Antes de habilitar `AGENT_ENABLED=true`, desative esse cron no projeto Vercel. Não altere os demais crons. O agente envia uma única requisição e não repete automaticamente em caso de timeout; confira o site antes de reexecutar.
