# Documentação do Agente Chocolícia

Documentação do agente de IA que gera receitas e conteúdo educativo (dicas, técnicas e matérias) para o site Chocolícia, e dos contratos com o site. O agente e o site são dois repositórios independentes: `agente-chocolicia` (Python) e `chocolicia` (site, backend e banco).

## Ordem de leitura

| Documento | Versão | Conteúdo |
| --- | --- | --- |
| `00-REGISTRO-DE-ALTERACOES.md` | - | O que mudou, decisões aplicadas, pendências de verificação |
| `01-ARQUITETURA.md` | 0.6 | Arquitetura, fases de lançamento, decisões D-01 a D-19, riscos |
| `02-PESQUISA.md` | 0.3 | Fontes, buscas, critérios e limites de uso das referências |
| `PESQUISA-RECEITAS.md` | 0.3 | Procedimento de pesquisa específico para receitas |
| `03-PROMPT-SISTEMA.md` | 0.4 | Persona, regras e prompts do Chef IA por tipo de conteúdo |
| `04-ESTRUTURA-CONTEUDO.md` | 0.4 | Categorias, subcategorias, risco por fase, ingredientes, esquemas de dados, migrations |
| `05-SEO.md` | 0.2 | SEO, dados estruturados, indexação |
| `06-INTEGRACAO.md` | 0.3 | Contratos da API, escopos de token, imagens, idempotência, alterações no site |
| `07-PUBLICACAO.md` | 0.3 | Publicação, fases, disjuntores, reversão, operação |
| `08-VALIDACAO.md` | 0.3 | Verificações por código, testes de mutação, critérios de promoção |
| `CODEX-01-SITE-BASE.md` | - | Prompt de implementação do Bloco 1 (site) |
| `PLANO-REFATORACAO-AGENTE.md` | - | Plano e prompts por passo para refatorar o agente (Blocos 5 a 7) |
| `.github/workflows/gerar-receitas.yml`, `gerar-dicas.yml` | - | Workflows agendados do agente (desligados até `AGENT_ENABLED` = `true`) |
| `seeds/taxonomy.seed.json` | 1.0.0 | Seed da taxonomia: 11 categorias, 74 subcategorias, tags |

## Decisões que orientam todo o projeto

- **Sem revisão humana e sem teste prático das receitas.** A barreira é a validação automática, conservadora (na dúvida, rejeita), com lançamento por fases de risco (Fases 0 a 3).
- **Assinatura:** "Equipe Chocolícia".
- **Alergias:** a receita lista seus ingredientes, e quem prepara decide se pode consumir. Não há detecção nem lista de alérgenos. Toda receita termina com um aviso fixo e simples sobre alergias e rótulos. O texto nunca afirma "sem glúten", "sem lactose", "hipoalergênico" nem "seguro para alérgicos".
- **Imagens:** bancos de imagens reais primeiro; geração por IA somente em último caso. Toda capa recebe a legenda "Imagem ilustrativa".
- **Aviso de IA** no topo de toda receita.
- **Fontes de receitas** servem só como referência e inspiração; o conteúdo é original.
- **O agente só cria conteúdo**, por API, com token de escopo `draft` ou `publish`. Não acessa o banco do site.
- **Dicas** ocupam, na navegação, o lugar das notícias. Não há notícias. Cada dica tem um assunto (preparo, montagem e apresentação, ornamentação, uso e escolha de equipamentos, negócios); dicas de equipamentos não citam marcas nem preços, e dicas de negócios não prometem ganho.
- **Escopo:** vendas e funcionalidades comerciais ficam fora desta documentação.

## Como usar com o Codex

1. Copiar estes arquivos para `docs/agente/` no repositório do site.
2. Criar um branch de teste do banco e configurar `DATABASE_URL_TEST` somente no `.env` do site.
3. Abrir o Codex na raiz do site e colar a Parte B de `CODEX-01-SITE-BASE.md`.
4. Revisar `docs/agente/AUDITORIA-SITE.md` e `RELATORIO-BLOCO-1.md` antes de seguir para o próximo bloco.

## Blocos de implementação

| Bloco | Conteúdo |
| --- | --- |
| 1 | Site: auditoria, migrations, seeds, tokens e escopos, contrato v1, endpoints de leitura |
| 2 | Site: imagens (banco de imagens, geração em último caso, estado `processing`) |
| 3 | Site: denúncias, endpoints administrativos, disjuntor por receita |
| 4 | Site: avisos, assinatura, legendas, páginas, URLs, JSON-LD, sitemap |
| 5 | Agente: estrutura, cliente do site, adaptador, banco do agente |
| 6 | Agente: pesquisa, criação, validadores, imagem, SEO |
| 7 | Agente: testes de mutação, golden set, integração contínua, agendador |

## Convenções

- Português do Brasil, em voz impessoal.
- Nomes em inglês no banco e na API; português na interface e no contrato do agente.
- Slugs sem acento, minúsculos, com hífen.
- Cada alteração relevante é registrada em `00-REGISTRO-DE-ALTERACOES.md`.

## Antes de publicar este repositório

Conferir que nenhum segredo, string de conexão ou caminho local aparece nos arquivos, e manter o repositório do agente privado até a revisão final.
