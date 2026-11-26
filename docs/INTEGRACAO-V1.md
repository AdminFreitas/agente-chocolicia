# Integração V1 Chocolícia

Este documento é a referência operacional atual para o agente e substitui instruções antigas baseadas em `articles`, `content_type` ou Ollama.

## Contratos

- Receitas: `POST /api/recipes`.
- Conteúdo educativo: `POST /api/tips`.
- Cabeçalho obrigatório: `X-Contract-Version: 1`.
- Escrita idempotente: `Idempotency-Key` com SHA-256 hexadecimal de 64 caracteres.
- Conteúdo educativo usa `type`: `dica`, `tecnica` ou `materia`.
- `dica` pode ser publicada somente quando todas as validações e a permissão de publicação estiverem ativas.
- `tecnica` e `materia` entram como `draft` para revisão.

## Tokens

O agente envia `Authorization: Bearer <token>`.

- `SITE_TOKEN_DRAFT`/`SITE_TOKEN_DRAFT_PREVIEW`: rascunhos e consultas.
- `SITE_TOKEN_PUBLISH`: publicação explícita em Production, somente com fase e configuração habilitadas.

Um conteúdo com `status=draft` nunca seleciona o token de publicação. Tokens não devem aparecer em logs.

## Imagens

`CHOCOLICIA_COVER_JSON` aceita um objeto de capa `stock` com `provider`, `sourceImageUrl`, `sourcePageUrl`, `author`, `license` e `attributionText`, ou `generate` com `imagePrompt`. Stock é preferível. Geração exige `AGENT_IMAGE_GENERATION_ENABLED=true` e `OPENAI_API_KEY` no site.

## Autores

O agente não usa um ID global. O payload pode enviar `authorId` obtido no ambiente corrente ou `authorSlug`; a API resolve e valida o autor ativo. A distribuição editorial de receitas entre Michel Freitas e Janine Gonçalves permanece uma configuração explícita pendente enquanto a documentação não definir o critério. Na ausência dessa configuração, receitas falham fechadamente; conteúdos educativos com autor válido continuam permitidos.

## Tópicos e banco

Os tópicos educativos são resolvidos por slug. A migration `drizzle/0003_editorial_tips.sql` é uma baseline idempotente versionada, não deve ser executada automaticamente contra o Neon oficial. O Neon oficial é operado externamente; não usar `drizzle-kit push` genérico.

## Agendamento operacional

O código mantém workflows separados para receitas e conteúdo educativo. O responsável operacional por habilitar um único agendador de receitas é o ambiente externo; não se deve habilitar simultaneamente o cron do Vercel e o workflow programado. Execuções manuais de Preview são o caminho de validação.
