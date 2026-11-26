# Etapa de integração do agente com o site

## Conclusão

A integração ponta a ponta permanece bloqueada, sem publicação ou conteúdo enviado. A verificação foi feita contra o site local de teste (`http://127.0.0.1:3000`), sem alterar o repositório do site e sem usar produção.

**Contrato v1 não implantado no destino.** O destino local não fornece o contrato documentado de taxonomia/artigos; o agente foi adaptado para o contrato legado de receitas em `POST /api/recipes` com `category`, sem `subcategorySlug`. A aceitação do payload legado ainda não pôde ser confirmada porque a autenticação de agente do site responde com erro antes da validação do corpo.

Na solicitação posterior, a origem local do agente foi configurada para produção, mas não houve chamada à produção. O único secret local de publicação esperado é `RECIPES_AGENT_TOKEN`, que não está configurado.

## Verificações empíricas do destino

- `GET /api/taxonomy`: HTTP 200; 11 categorias e 74 subcategorias. A resposta usa `riskLevel` e `agentEnabled` em camelCase. Nenhuma subcategoria veio com `agentEnabled: true`; portanto não há categoria/subcategoria autorizada para geração pelo agente.
- `GET /api/articles`: HTTP 200 com HTML da aplicação de desenvolvimento, não uma resposta JSON do contrato de artigos. Um POST vazio anterior também retornou HTML. `OPTIONS /api/articles` retornou 204, o que por si só não comprova a existência do endpoint POST.
- POST vazio em `/api/recipes`: HTTP 503 por configuração/autorização do agente ausente. Não houve persistência de receita.
- `SITE_TOKEN_DRAFT` não está disponível na configuração local verificada. Nenhum token foi impresso ou registrado aqui.

### Registro da resposta de taxonomia

Resposta `GET /api/taxonomy` (HTTP 200): categorias têm `parentId: null`, `sortOrder` de 1 a 11, `active: true`, `riskLevel: null` e `agentEnabled: false`. Subcategorias têm `parentId` igual ao id da categoria agrupadora, `sortOrder` conforme a ordem abaixo, `active: true` e `agentEnabled: false`. `description`, `seoTitle` e `seoDescription` são `null` em todos os itens. A tabela registra id, slug, nome e `riskLevel`; nenhum item habilita geração.

| Categoria (id; slug) | Subcategorias retornadas (`id slug` / nome: `riskLevel`) |
|---|---|
| Bolos e tortas (1; `bolos-e-tortas`) | 12 `bolos-simples` / Bolos simples: low; 13 `bolos-recheados-e-cobertos` / Bolos recheados e cobertos: medium; 14 `bolos-de-festa` / Bolos de festa: medium; 15 `bolos-de-pote` / Bolos de pote: medium; 16 `tortas-doces` / Tortas doces: medium; 17 `tortas-salgadas` / Tortas salgadas: medium; 18 `cheesecakes` / Cheesecakes: medium |
| Carnes (2; `carnes`) | 19 `bovina` / Bovina: high; 20 `suina` / Suína: high; 21 `assados-e-churrasco` / Assados e churrasco: high; 22 `carne-moida` / Carne moída: high; 23 `carnes-de-panela` / Carnes de panela: high; 24 `embutidos-e-linguicas` / Embutidos e linguiças: high |
| Aves (3; `aves`) | 25 `frango-assado` / Frango assado: high; 26 `frango-frito-e-empanado` / Frango frito e empanado: high; 27 `frango-de-panela` / Frango de panela: high; 28 `peito-de-frango` / Peito de frango: high; 29 `frango-desfiado` / Frango desfiado: high; 30 `frango-cremoso` / Frango cremoso: high; 31 `peru-e-chester` / Peru e chester: high |
| Peixes e frutos do mar (4; `peixes-e-frutos-do-mar`) | 32 `peixes-assados` / Peixes assados: high; 33 `peixes-fritos` / Peixes fritos: high; 34 `moquecas` / Moquecas: high; 35 `camarao` / Camarão: high; 36 `lula-e-polvo` / Lula e polvo: high; 37 `mariscos` / Mariscos: high; 38 `bacalhau` / Bacalhau: high |
| Saladas e molhos (5; `saladas-e-molhos`) | 39 `saladas-verdes` / Saladas verdes: medium; 40 `saladas-de-legumes` / Saladas de legumes: medium; 41 `saladas-com-proteina` / Saladas com proteína: high; 42 `saladas-de-massa-e-graos` / Saladas de massa e grãos: medium; 43 `molhos-para-salada` / Molhos para salada: medium; 44 `molhos-quentes` / Molhos quentes: medium; 45 `molhos-para-carnes` / Molhos para carnes: medium; 46 `maioneses-e-pastas` / Maioneses e pastas: high |
| Sopas (6; `sopas`) | 47 `caldos` / Caldos: medium; 48 `sopas-cremosas` / Sopas cremosas: medium; 49 `sopas-de-legumes` / Sopas de legumes: medium; 50 `sopas-com-carne` / Sopas com carne: high; 51 `sopas-leves` / Sopas leves: medium |
| Massas (7; `massas`) | 52 `macarrao-ao-molho` / Macarrão ao molho: medium; 53 `lasanhas-e-gratinados` / Lasanhas e gratinados: medium; 54 `massas-recheadas` / Massas recheadas: medium; 55 `massas-caseiras` / Massas caseiras: medium; 56 `molhos-para-massa` / Molhos para massa: medium; 57 `nhoque` / Nhoque: medium; 58 `massas-frias` / Massas frias: medium |
| Bebidas (8; `bebidas`) | 59 `sucos` / Sucos: medium; 60 `sucos-detox` / Sucos detox: high; 61 `vitaminas-e-smoothies` / Vitaminas e smoothies: medium; 62 `chas` / Chás: medium; 63 `bebidas-quentes` / Bebidas quentes: medium; 64 `bebidas-geladas-e-cremosas` / Bebidas geladas e cremosas: medium; 65 `drinks-sem-alcool` / Drinks sem álcool: medium; 66 `drinks-com-alcool` / Drinks com álcool: high |
| Doces e sobremesas (9; `doces-e-sobremesas`) | 67 `brigadeiros-e-docinhos` / Brigadeiros e docinhos: low; 68 `trufas-e-bombons` / Trufas e bombons: low; 69 `pudins-e-flans` / Pudins e flans: medium; 70 `mousses` / Mousses: medium; 71 `sorvetes-e-geladinhos` / Sorvetes e geladinhos: medium; 72 `doces-de-colher` / Doces de colher: low; 73 `paves-e-sobremesas-geladas` / Pavês e sobremesas geladas: medium; 74 `doces-regionais` / Doces regionais: medium; 75 `panetones-e-chocotones` / Panetones e chocotones: medium |
| Lanches (10; `lanches`) | 76 `sanduiches` / Sanduíches: medium; 77 `salgados-assados` / Salgados assados: medium; 78 `salgados-fritos` / Salgados fritos: high; 79 `paes-e-recheios` / Pães e recheios: medium; 80 `pizzas` / Pizzas: medium; 81 `lanches-rapidos` / Lanches rápidos: medium |
| Alimentação saudável (11; `alimentacao-saudavel`) | 82 `receitas-leves` / Receitas leves: medium; 83 `fit-e-low-carb` / Fit e low carb: high; 84 `poucos-ingredientes` / Poucos ingredientes: medium; 85 `refeicoes-completas` / Refeições completas: medium |

## Implementação no agente

- Configuração carrega o `.env` da raiz absoluta do agente, sem sobrescrever variáveis já presentes no processo. HTTP é permitido apenas para loopback com `AGENT_ENV=test`; Preview exige HTTPS `.vercel.app`; produção exige `AGENT_ENV=production` e exatamente `https://www.chocolicia.site`.
- O `.env` local do agente agora aponta para `AGENT_ENV=production`, `SITE_BASE_URL=https://www.chocolicia.site` e Ollama em `127.0.0.1:11434`. Nenhum token foi adicionado; `.env` permanece ignorado pelo Git.
- O cliente centralizado usa o contrato legado somente para receitas, exige rascunho e não envia `subcategorySlug`. Timeout de rede no POST legado é tratado como resultado incerto, sem reenvio automático.
- O envio de artigos/dicas permanece bloqueado por padrão. O cliente só aceita artigos se `SITE_ARTICLES_ENABLED=true`, mas a composição de geração de dicas ainda não possui pesquisa/seleção de tópico própria e a rota local não foi confirmada.
- `build_services()` compõe dependências reais de receitas. O alvo de produção exige contrato legado, fase de publicação, `RECIPES_AGENT_TOKEN` e banco do agente para bloquear `topic_slug` repetido e registrar o ID/slug da resposta.
- Ollama é o provedor local padrão, usa o modelo configurado por `OLLAMA_MODEL`, não tenta baixar modelos e não faz fallback para API comercial. O endpoint `localhost:11434` é normalizado para `127.0.0.1:11434`; o timeout padrão de geração local é 180 segundos.

## Validação de geração

`GET http://127.0.0.1:11434/api/tags` respondeu com modelos locais disponíveis, incluindo `qwen2.5:3b`, `qwen3:latest` e `llama3:latest`. O adaptador configurado gerou a resposta `OK` para uma solicitação mínima, sem baixar modelos nem chamar API comercial. Isso confirma a comunicação com o modelo, mas não equivale à geração e validação de uma receita completa. Não foi feita geração de conteúdo para publicação: não há subcategoria habilitada, chave/token de envio nem endpoint de artigos confirmado.

## Próximos passos necessários

1. Configurar `RECIPES_AGENT_TOKEN` como secret local e do GitHub Actions antes de qualquer publicação.
2. Configurar o runner self-hosted Windows com Ollama e as variáveis/secrets listadas em `docs/CONFIGURACAO-GITHUB-ACTIONS.md`.
3. Manter a publicação bloqueada na Fase 0 e até os critérios da fase seguinte serem cumpridos.
4. Manter dicas/artigos no armazenamento interno; o workflow permanece bloqueado enquanto o pipeline de pesquisa/armazenamento interno não estiver composto e `POST /api/articles` não existir.

## Agendamento pelo GitHub Actions

- Receitas: cron diário às 08:00 em `America/Sao_Paulo`; publicação de produção só ocorre no branch padrão, com `AGENT_ENABLED=true`, fase autorizada, token e banco interno configurados.
- Dicas: cron às terças e sextas às 09:00 em `America/Sao_Paulo`; requer runner self-hosted Windows com Ollama, mas permanece bloqueado até `dependencias_dica` estar composta e persistir conteúdo internamente. Não envia ao site.
- O token `RECIPES_AGENT_TOKEN` está ausente no ambiente local. Não foram executados workflows, testes, dry-runs ou chamadas de rede nesta etapa; nenhuma publicação foi feita.

Nenhuma chamada de publicação foi feita; nenhuma receita ou dica foi enviada; nenhuma alteração foi feita no repositório do site.
