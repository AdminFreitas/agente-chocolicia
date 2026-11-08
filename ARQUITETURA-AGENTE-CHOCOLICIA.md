# 01 - Arquitetura do Agente Chocolícia

| Item | Valor |
| --- | --- |
| Projeto | agente-chocolicia |
| Caminho local | `C:\Users\miche\Projetos\agente-chocolicia` |
| Versão do documento | 0.2 (reescrita após a decisão arquitetural) |
| Data | 05/11/2026 |
| Base | Auditoria somente leitura do site `chocolicia` e do agente atual, mais a decisão de arquitetura de 05/11/2026 |
| Próximo documento | `02-PESQUISA.md` |

---

## 1. Objetivo

Transformar a página de receitas do site Chocolícia em um canal de conteúdo automatizado, alimentado por um agente de IA especializado em culinária e confeitaria, e abrir um segundo canal de conteúdo educativo (dicas, técnicas e matérias) que sirva de base para futuros infoprodutos (e-books, PDFs e cursos).

O agente deve:

1. Planejar a pauta editorial respeitando a árvore de categorias do site.
2. Pesquisar referências em sites culinários, sem copiar texto, fotos ou instruções.
3. Gerar conteúdo original, estruturado e validado.
4. Entregar o conteúdo ao site por API autenticada, sempre como rascunho.
5. Registrar o que foi gerado, enviado, publicado e rejeitado.

---

## 2. Decisão arquitetural

Quatro princípios, aprovados em 05/11/2026:

1. **O agente Python é o cérebro editorial do Chocolícia.** Pauta, pesquisa, prompts, geração e validação vivem nele. O gerador interno do site (`server/recipeAgent.ts`) não substitui o agente.
2. **O site é a plataforma de apresentação e publicação.** Recebe o conteúdo do agente, valida, trata imagens, armazena e exibe.
3. **O Neon é a fonte central de dados**, sujeito à confirmação da conexão existente (decisão D-01).
4. **O agente executa em infraestrutura independente.** É iniciado por um agendador, executa a tarefa e finaliza. Não fica residente na memória do servidor do site.

Estrutura de repositórios: **dois repositórios GitHub independentes**, `chocolicia` (site, backend, banco e APIs) e `agente-chocolicia` (agente completo). Uma migração para monorepo não traz vantagem agora, com o site já publicado. Ela continua possível no futuro sem mudar os contratos descritos aqui.

---

## 3. Diagnóstico do estado atual

### 3.1 Agente (`agente-chocolicia`)

- É, na prática, o código do blog de tecnologia **DigitalTech**: prompts, feeds RSS, categorias e imagens são de tecnologia.
- Stack: Python, SQLAlchemy, FastAPI (`api.py`), CLI (`rodar_agente.py --artigo --noticia`).
- Cadeia de LLMs com fallback configurável (`FALLBACK_ORDER`): Groq, Gemini, Ollama, OpenAI, Claude, DeepSeek e outros.
- Imagens: Openverse, Unsplash, Pexels, Pixabay e Pollinations, com termos de busca de computação.
- Publicação: salva `rascunho` na tabela `artigos` e faz commit de `.md` no repositório `AdminFreitas/digitaltech` pela API do GitHub.
- Agendamento: `FEATURE_AGENDAMENTO=false` e nenhum workflow em `.github/workflows/`.
- Banco: Neon próprio (região `sa-east-1`), com tabelas `artigos`, `noticias` e `categorias` de tecnologia.

### 3.2 Site (`chocolicia`)

- Possui motor culinário próprio: `server/recipeAgent.ts` (geração diária), `server/recipesRoutes.ts` (API) e Drizzle ORM (tabela `recipes`).
- Gera imagem por IA (`gpt-image-1`), processa com Sharp (6 variantes: 480, 800 e 1280 px em WebP e AVIF) e grava no armazenamento do projeto.
- `POST /api/recipes` exige `Authorization: Bearer <RECIPES_AGENT_TOKEN>`, limite de 1 MB, sanitização anti-XSS e validação Zod.
- O campo `status` da API tem padrão **`published`**. Um envio sem `status` publica direto (ver D-06).
- O campo `coverImageUrl` é **obrigatório** e deve ser uma URL pública já hospedada (ver D-09).
- Aceita apenas **7 categorias** hoje; tags são um array de texto na própria tabela `recipes`.
- Existe um adaptador em `integrations/agente-chocolicia-recipes/` (script `gerar_receita_blog.py` e workflow `gerar-receita-blog.yml`) que aciona `POST /api/recipes/generate-daily`. Com a decisão arquitetural, ele passa a ser contingência, não o caminho principal.

### 3.3 Banco de dados

Não há evidência de que os dois projetos usem o mesmo banco Neon. O `.env` do agente aponta para um Neon; `DATABASE_URL` do site está vazio localmente (o valor de produção fica na Vercel). Ver D-01.

### 3.4 Incompatibilidades de contrato

| Aspecto | Site exige | Agente atual entrega |
| --- | --- | --- |
| Formato | JSON estruturado | Markdown contínuo |
| Campos | `title`, `excerpt`, `coverImageUrl`, `ingredients`, `steps`... | `titulo`, `conteudo_md`... |
| Categorias | 7 de confeitaria e festas | 10 de tecnologia |
| Métricas | `prepTimeMin`, `servings`, `difficulty` | `readTime` |
| Destino | `POST /api/recipes` | Commit no GitHub |

O JSON da documentação original não pode ser enviado direto à API. É necessário um adaptador de contrato (seção 8).

---

## 4. Princípios de engenharia

1. **Responsabilidade única.** Cada projeto faz o que já faz bem; nada é duplicado sem necessidade.
2. **Uma fonte de verdade para taxonomia.** Categorias, subcategorias e tags são definidas em um lugar só.
3. **Privilégio mínimo.** O agente só tem permissão para criar e atualizar receitas, artigos, imagens e relacionamentos. Não altera outros dados do site e não recebe a senha do banco do site.
4. **Conteúdo original e honesto.** O agente não copia fontes e não afirma que testou fisicamente uma receita.
5. **Revisão antes de publicar.** Todo conteúdo do agente entra como `draft`, e isso é **imposto pelo servidor**, não só pelo agente.
6. **Mudanças aditivas.** Nada que já está publicado no site pode quebrar.
7. **Idempotência.** Reexecutar uma etapa não duplica receitas, categorias ou artigos (uso de slugs).

---

## 5. Divisão de responsabilidades

| Camada | Responsabilidade |
| --- | --- |
| **Agente Python** | Pauta editorial, pesquisa, análise de referências, geração de receitas e artigos educativos, revisão, SEO, prompt de imagem, histórico de gerações, controle de cobertura |
| **Camada de integração** | Contratos validados, autenticação por token, tradução entre o formato do agente e o do site, tentativas e tratamento de erros |
| **Backend Chocolícia (Vercel)** | Validação final, sanitização, geração e tratamento de imagens (reaproveitando o código existente), armazenamento, publicação, rotas e páginas |
| **Neon PostgreSQL** | Receitas, artigos, categorias, tags, relacionamentos e histórico |
| **Site Chocolícia** | Exibição de receitas e da seção de conteúdo educativo, painel de revisão |

---

## 6. Visão geral

```text
        Agendador (GitHub Actions ou worker)
                     |
                     v
+--------------------------------------------+
|  AGENTE CHOCOLÍCIA (Python, repo próprio)  |
|  1 Pauta -> 2 Pesquisa -> 3 Análise        |
|  4 Criação -> 5 Revisão -> 6 SEO           |
+--------------------------------------------+
                     |  JSON validado + token do agente
                     v
+--------------------------------------------+
|  CAMADA DE INTEGRAÇÃO (adaptador)          |
+--------------------------------------------+
                     |  HTTPS
                     v
+--------------------------------------------+
|  BACKEND CHOCOLÍCIA (Vercel)               |
|  /api/recipes   /api/articles (futuro)     |
|  validação, imagens, rascunho              |
+--------------------------------------------+
                     |
                     v
+--------------------------------------------+
|  NEON POSTGRESQL                           |
+--------------------------------------------+
                     |  revisão e aprovação
                     v
              SITE CHOCOLÍCIA
```

---

## 7. Fluxo diário e as oito etapas

### 7.1 Exemplo de execução diária (08h, horário de Brasília)

| Horário | Evento |
| --- | --- |
| 08h00 | O agendador dispara o processo Python |
| 08h00-08h10 | Pauta, pesquisa, análise e criação do conteúdo |
| 08h10-08h15 | Revisão, validação, SEO e envio à API |
| 08h15 | O backend valida, trata a imagem e grava como `draft` |
| Depois | Revisão humana e aprovação; só então o conteúdo vira público |

O cron do GitHub Actions usa UTC. Como o Brasil está em UTC-3 sem horário de verão, 08h em Brasília corresponde a `0 11 * * *`.

### 7.2 Etapas

| # | Etapa | Entrada | Saída | Origem do código |
| --- | --- | --- | --- | --- |
| 1 | Agendamento e pauta | Árvore de categorias, histórico, cobertura por subcategoria | Tema, categoria, subcategoria, tipo de conteúdo | Refatorar `pesquisador.py` |
| 2 | Pesquisa | Tema da pauta | Referências resumidas de fontes culinárias | Refatorar `pesquisador.py` |
| 3 | Análise e cruzamento | Referências | Proporções, técnicas e pontos de consenso | Novo (`agents/analista.py`) |
| 4 | Criação original | Análise + regras do Chef IA | Receita ou artigo estruturado | Refatorar `editor.py` |
| 5 | Revisão e validação | Rascunho | Rascunho validado ou rejeitado, com motivo | Refatorar `revisor.py` + validador de receitas |
| 6 | SEO e visual | Conteúdo validado | Título, excerpt, tags, texto alternativo, prompt de imagem | Refatorar `seo.py` |
| 7 | Integração | Conteúdo final | Chamada à API do site (rascunho) | Novo (`integration/`) |
| 8 | Publicação e monitoramento | Resposta da API | Registro de status, logs, métricas | Refatorar `publisher.py` |

### 7.3 Papel do gerador interno do site

O motor `runDailyRecipeGeneration` e o endpoint `generate-daily` **não são removidos**, mas deixam de ser o caminho principal. Para evitar receitas duplicadas, o cron interno de receitas do site deve ser desativado quando o agente entrar em produção, ficando o gerador interno como contingência manual. Os módulos de imagem e persistência dele são reaproveitados (D-09).

---

## 8. Camada de integração

Contratos do agente em português, do site em inglês. O adaptador converte, e o contrato do site é a referência.

### 8.1 Receita: mapeamento de campos

| Campo do agente | Campo da API (`POST /api/recipes`) | Observação |
| --- | --- | --- |
| `titulo` | `title` | 5 a 180 caracteres |
| `descricao_curta` | `excerpt` | 20 a 160 caracteres |
| `categoria_principal` | `category` | Deve existir na lista do site (D-02) |
| `tempo_preparo_min` | `prepTimeMin` | Inteiro, 1 a 1440 |
| `tempo_cozimento_min` | `cookTimeMin` | Opcional |
| `rendimento_porcoes` | `servings` | Inteiro, 1 a 500 |
| `dificuldade` | `difficulty` | `Fácil`, `Média` ou `Difícil` |
| `ingredientes` | `ingredients` | Lista de seções com itens (`quantity`, `unit`, `name`, `note`) |
| `modo_preparo` | `steps` | Mínimo 2 passos (`title` opcional, `instruction`) |
| `dicas` | `tips` | Até 12 |
| `armazenamento` | `storageNotes` | Até 3000 caracteres |
| `perguntas_frequentes` | `faq` | Até 12 |
| `tags` | `tags` | Até 12, 40 caracteres cada |
| `prompt_imagem` | `imagePrompt` | Até 2000 caracteres |
| `texto_alt_imagem` | `coverImageAlt` | 8 a 240 caracteres |
| `status` | `status` | Sempre `draft` |
| `modelo_ia` | `aiModel` | Registro de origem |
| `meta_geracao` | `generationMeta` | Fontes consultadas, versão do prompt, data |

Campos do agente sem equivalente atual no site (`subcategorias`, `ocasiao`, `dieta`) ficam em `generationMeta` até o site ganhar suporte (D-04).

### 8.2 Imagens (D-09)

O contrato atual exige `coverImageUrl` pública e o site já tem um pipeline completo de imagem (geração, Sharp, 6 variantes, armazenamento). Duplicar isso em Python obrigaria a dar ao agente credenciais de armazenamento do site, contra o princípio de privilégio mínimo. Proposta:

- O agente produz o `imagePrompt` (e o `coverImageAlt`) como parte do conteúdo.
- O site passa a aceitar o envio **sem** `coverImageUrl` quando houver `imagePrompt`, e gera e trata a imagem com o código que já existe, gravando as URLs e as variantes.
- Alternativa, se for preferível não mexer no `POST /api/recipes`: um endpoint separado de imagem para receitas já gravadas como rascunho.

Isso exige uma alteração no site, a ser especificada em `06-INTEGRACAO.md`.

### 8.3 Conteúdo educativo (dica, técnica, matéria)

Não existe endpoint no site para esse tipo. Será definido em `06-INTEGRACAO.md`, junto com a tabela `artigos` do site, mantida separada de `recipes`.

### 8.4 Autenticação, permissões e erros

- Header `Authorization: Bearer <token>`. O token do agente fica em variável de ambiente ou secret, nunca no código.
- O token do agente só dá acesso aos endpoints de criação e atualização de conteúdo. Não dá acesso a rotas administrativas.
- **Rascunho imposto no servidor:** requisições autenticadas com o token do agente são gravadas como `draft`, mesmo que enviem `status: "published"`. A publicação só acontece por ação autenticada de um administrador.
- Rate limit e validação de payload no backend (já existem validação Zod, sanitização e limite de 1 MB; o rate limit deve ser confirmado).
- `HTTP 400`: erro de validação; o agente registra o motivo e não reenvia o mesmo JSON.
- `HTTP 409`: slug duplicado; o agente trata como "já existe" e escolhe nova pauta.
- `HTTP 5xx` e timeouts: até 3 tentativas com espera crescente, depois registro de falha.

### 8.5 Fonte canônica dos contratos

Como o site é dono da API, o contrato canônico fica no repositório `chocolicia` (schema derivado do Zod, versionado). O agente mantém uma cópia e roda um teste de contrato a cada alteração, para que uma mudança no site que quebre o agente seja detectada antes da execução agendada.

---

## 9. Dados e banco

- **Conteúdo editorial** (receitas, artigos, categorias, tags, relacionamentos) fica no Neon do site e é gravado **somente pela API**.
- O agente não recebe a string de conexão das tabelas do site.
- O **histórico de gerações e o controle de cobertura** precisam de armazenamento próprio. Opções, a decidir em D-05: tabela `geracoes_agente` no Neon do site, em schema separado e com papel de banco restrito, ou um banco leve do próprio agente. Para ler a cobertura por subcategoria, o agente usa um endpoint de leitura da API do site.
- Seeds de categorias idempotentes, por slug (sem IDs fixos). Corrigir o erro de nomenclatura `Bacanhao` para `Bacalhau`.
- Relacionamentos entre conteúdos com chaves estrangeiras reais (sem tabela polimórfica sem integridade referencial).
- Nenhuma migration é executada antes de fechar D-01 e D-02.

---

## 10. Hospedagem e agendamento do agente

O fornecedor não precisa ser decidido agora. Recomendação provisória para a primeira fase, que cumpre o princípio de "iniciar, executar e finalizar":

| Opção | Avaliação |
| --- | --- |
| GitHub Actions agendado (repositório privado) | Mais simples para começar: agenda, secrets e logs já existem. Atenção: o agendamento usa UTC, pode atrasar alguns minutos, e o Ollama local não existe lá, então a cadeia de LLMs deve usar provedores em nuvem |
| Worker Python dedicado ou serviço de containers | Melhor se a duração ou o volume crescerem (várias receitas por dia, imagens, pesquisas longas) |
| VPS | Mais controle, mas exige administração |
| Vercel Functions | Boa para APIs e tarefas curtas; não é a melhor escolha para o agente completo |

O agente deve ser empacotado de forma que a mudança de GitHub Actions para worker seja apenas troca do agendador, sem alterar o código.

---

## 11. Estrutura de pastas alvo

```text
agente-chocolicia/
├── docs/                      # documentação (01 a 08)
├── config/
│   ├── categorias.json        # cópia versionada da árvore editorial (ou leitura via API)
│   └── settings.py
├── agents/
│   ├── planejador.py          # etapa 1
│   ├── pesquisador.py         # etapa 2
│   ├── analista.py            # etapa 3 (novo)
│   ├── editor.py              # etapa 4
│   ├── revisor.py             # etapa 5
│   └── seo.py                 # etapa 6
├── integration/
│   ├── contratos.py           # modelos Pydantic dos payloads
│   ├── adaptador_receita.py   # agente -> API do site
│   └── cliente_site.py        # HTTP, token, tentativas
├── pipeline/
│   ├── gerar_receitas.py
│   └── gerar_conteudo_educativo.py
├── prompts/                   # prompts versionados, fora do código
├── services/
│   └── llm_service.py         # reaproveitado
├── tests/                     # inclui testes de contrato
├── .github/workflows/
├── .env.example
└── rodar_agente.py
```

---

## 12. O que reaproveitar, refatorar, criar e remover

| Componente | Decisão | Motivo |
| --- | --- | --- |
| `services/llm_service.py` | Reaproveitar | Fallback de LLMs já validado |
| `rodar_agente.py` | Refatorar | Novos comandos (`--receita`, `--dica`, `--tecnica`, `--materia`) |
| `agents/editor.py` | Refatorar | Trocar persona de tecnologia pelo Chef IA e saída estruturada em JSON |
| `agents/pesquisador.py` | Refatorar | Trocar feeds de tecnologia por fontes culinárias e pauta por categoria |
| `agents/revisor.py`, `seo.py` | Refatorar | Regras culinárias e SEO de receitas |
| `services/imagem_service.py` | Reduzir | O agente só gera o prompt da imagem; a geração e o tratamento ficam no site |
| `agents/publisher.py`, `github_service.py` | Substituir | O commit para `AdminFreitas/digitaltech` não pode existir neste projeto |
| `api.py` (dashboard DigitalTech) | Remover ou isolar | Não pertence ao Chocolícia |
| `pipeline/gerar_noticias.py`, `noticia_repository.py` | Remover | Fora do escopo |
| Tabelas `artigos`, `noticias` do banco atual | Não migrar | Estrutura de tecnologia; o conteúdo do Chocolícia nasce no banco do site |

---

## 13. Registro de decisões

| ID | Decisão | Status | Observação |
| --- | --- | --- | --- |
| D-01 | Neon do site como central; agente grava somente por API | Aprovada em princípio, **depende de confirmar a conexão do site** | Verificar o `DATABASE_URL` de produção na Vercel antes das migrations |
| D-02 | Ampliar categorias do site de 7 para 11, com subcategorias | Aprovada, **a implementar** | Alterar o enum do site e o seed; corrigir `Bacalhau` |
| D-03 | Agente gera o JSON da receita e envia por `POST /api/recipes` (Rota B); `generate-daily` vira contingência | Aprovada | Desativar o cron interno de receitas do site na entrada em produção |
| D-04 | Tags e taxonomia compartilhadas | **Pendente** | Hoje tags são array em `recipes`; avaliar tabela de tags e campos para ocasião e dieta |
| D-05 | Onde guardar o histórico e a cobertura do agente | **Pendente** | Schema separado no Neon com papel restrito, ou banco leve do agente |
| D-06 | Tudo entra como `draft`, imposto pelo servidor para o token do agente | Aprovada, **exige ajuste no site** | O padrão atual da API é `published` |
| D-07 | Relacionamentos com integridade referencial | Aprovada | Evitar tabela polimórfica sem chaves estrangeiras |
| D-08 | Seeds idempotentes por slug | Aprovada | Sem IDs fixos |
| D-09 | Imagem tratada pelo site a partir do `imagePrompt` | **Proposta, exige ajuste no site** | Evita dar ao agente acesso ao armazenamento |
| D-10 | Hospedagem do agente | Adiada | Recomendação provisória: GitHub Actions privado na primeira fase |
| D-11 | Contrato canônico no repositório do site, com teste de contrato no agente | Proposta | Evita divergência entre os dois repositórios |
| D-12 | Mecanismo de revisão e aprovação humana | **Pendente** | Verificar se o site tem painel administrativo para aprovar rascunhos; se não, especificá-lo |

---

## 14. Segurança e boas práticas antes de subir ao GitHub

O projeto ainda não está no GitHub. Antes do primeiro commit:

1. Criar um `.gitignore` que exclua `.env`, `*.db`, `__pycache__/` e logs. O `.env` atual contém credenciais de vários provedores de LLM, banco e GitHub.
2. Versionar apenas o `.env.example`, sem valores reais. O arquivo atual tem mais de 500 linhas; reduzir às variáveis que o Chocolícia usa.
3. Como o `.env` já existiu em disco com chaves ativas, trocar as chaves dos provedores que não serão usados e confirmar que nenhuma chave real entra no histórico do repositório novo.
4. Remover referências ao repositório `AdminFreitas/digitaltech` e ao token do GitHub usado para commit de artigos.
5. Criar o repositório como **privado**.
6. Guardar o token do agente e as chaves de LLM em GitHub Secrets (e na Vercel o que for do site). Ao rotacionar, usar tokens separados por ambiente.

---

## 15. Observabilidade

- Log estruturado por execução: data, tema, categoria, etapa, modelo de IA usado, duração e resultado.
- Histórico de gerações (`geracoes_agente`) com status: `planejada`, `gerada`, `reprovada`, `enviada`, `aprovada`, `publicada`, `erro`.
- Controle de cobertura: contagem de conteúdos por subcategoria para priorizar as vazias e evitar repetição de tema.
- Alerta (e-mail ou notificação do GitHub Actions) quando uma execução falhar duas vezes seguidas.

---

## 16. Riscos conhecidos

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Envio sem `status` publica direto (padrão da API) | Conteúdo sem revisão no ar | D-06: rascunho imposto no servidor |
| Receita com medidas incoerentes | Qualidade e reputação | Validador de proporções e revisão humana inicial |
| Cópia de texto de fontes | Jurídico e SEO | Fontes só para pesquisa; verificação de similaridade; texto sempre reescrito |
| Afirmar teste físico inexistente | Honestidade com o leitor | Regra explícita no prompt e no validador |
| Divergência de categorias ou campos entre os repositórios | Erros 400 | D-11: contrato canônico e teste de contrato |
| Receitas duplicadas pelo cron interno do site e pelo agente | Conteúdo repetido | Desativar o cron interno na entrada em produção |
| Dois bancos desalinhados | Dados duplicados | D-01 antes de qualquer migration |
| Falha de capacidade de um modelo de IA | Execução interrompida | Fallback já existente no `llm_service.py` |
| Chaves vazadas ao publicar o repositório | Segurança | Seção 14 |

---

## 17. Sequência da documentação

| Documento | Conteúdo |
| --- | --- |
| `01-ARQUITETURA.md` | Este documento |
| `02-PESQUISA.md` | Fontes, buscas, critérios de seleção, limites de uso das referências |
| `03-PROMPT-SISTEMA.md` | Persona e instruções do Chef IA, por tipo de conteúdo |
| `04-ESTRUTURA-CONTEUDO.md` | Padrão de dados de receitas e artigos, categorias, subcategorias, tags |
| `05-SEO.md` | Regras de SEO e dados estruturados |
| `06-INTEGRACAO.md` | Contratos, endpoints, autenticação, alterações no site e migrations |
| `07-PUBLICACAO.md` | Fluxo de rascunho, revisão, publicação e atualização |
| `08-VALIDACAO.md` | Testes e critérios de qualidade |
