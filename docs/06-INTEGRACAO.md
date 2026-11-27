# Integração entre o agente e o site Chocolícia

## Princípio

O agente Python gera e valida o conteúdo. O site recebe, autentica, persiste e apresenta esse conteúdo. O agente não acessa diretamente o banco Neon do site.

## Receitas

O ponto de entrada atual é `rodar_conteudo.py`. O fluxo usa `integration.content`, `services.llm_service` e `integration.site_client`.

O endpoint e o contrato de receitas utilizados por esse cliente ainda precisam ser comparados com a implementação do site durante a validação autorizada. Não considerar a publicação confirmada apenas porque o cliente e o workflow existem.

## Dicas

O fluxo de dicas é iniciado por `python -m pipeline.gerar_dica`. O agente envia o payload do contrato do site para `POST /api/tips`, autenticado pelo Bearer `TIPS_AGENT_TOKEN` (ou pelo token compartilhado `RECIPES_AGENT_TOKEN`, quando configurado assim).

Campos obrigatórios: `title`, `content`, `topicSlug` e `agentIdempotencyKey`. `topicSlug` precisa corresponder a um registro ativo em `tip_topics`; o agente não cria tópicos. A chave de idempotência é estável durante retries da mesma execução. A publicação pública requer `status=published`, `reviewStatus=approved` e `publishedAt` definido pelo backend.

## Autenticação e configuração

URLs e tokens são fornecidos por variáveis de ambiente e secrets do GitHub Actions. Não registrar valores secretos em arquivos versionados, logs ou documentação.

Os workflows selecionam o ambiente de destino e o token correspondente. O agente deve chamar apenas a API do site; não utilizar conexões diretas ao Neon do site nem publicar conteúdo por commits em repositórios de código.

## Validação pendente

Na etapa de validação autorizada, confirmar:

1. Assinaturas e formatos esperados por `integration.content` e `integration.site_client`.
2. Campos obrigatórios e validações do payload de receitas.
3. Campos obrigatórios de dicas e compatibilidade com `POST /api/tips`.
4. Autenticação, URL e seleção correta de Preview/produção.
5. Resposta de sucesso da API e persistência/exibição pelo site.

Até essa validação, não afirmar que os fluxos de publicação estão operacionais.
