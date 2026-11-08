# Plano de refatoração do agente (DigitalTech para Chocolícia)

Base: `MAPA-DO-PROJETO.md` do agente e a documentação em `docs/` (`01` a `08`). Este plano cobre os Blocos 5 a 7 do `README.md`.

---

## 1. O que o mapa mostra

| Achado | Consequência |
| --- | --- |
| O projeto é grande e tem muita coisa fora do caminho: API e painel, notícias, backlog, social, camada TypeScript, SQLite legado, arquivos `.bak` | Limpar antes de refatorar reduz o que a IA precisa ler (e os tokens gastos) |
| O caminho ativo de artigos (`rodar_agente` → `gerar_artigos` → editor → revisor → imagem → SEO → banco → GitHub) | É o esqueleto da pipeline de receitas |
| A camada de imagens já foi parcialmente adaptada ao Chocolícia (Pixabay, Pexels, Openverse, Wikimedia, seletor, download seguro, proveniência) | Reaproveitar; falta licença, deduplicação, verificação por visão e remover o armazenamento local |
| Não há busca na web (só RSS e LLM) | Falta o provedor de busca; sem ele a pesquisa de receitas não roda |
| Prompts embutidos nos `.py`; `prompts/*.md` parcialmente ignorados; briefing comentado na pipeline | Prompts passam a viver só em `prompts/`, versionados |
| 14 provedores de LLM no fallback | Reduzir a uma lista aprovada por tarefa |
| Chave de API literal em `services/pixabay_service.py` | Corrigir e **revogar a chave** antes de qualquer commit público |
| Dois workflows agendados do DigitalTech | Remover, para não rodarem no repositório novo |

## 2. Estratégia: limpar e portar, não reescrever tudo

1. **Limpar primeiro** (Passo 1): apagar o que é do DigitalTech ou está morto. Tudo o que sobra é pequeno o bastante para a IA ler em partes.
2. **Portar por módulo**, um passo por vez, sempre com teste.
3. **Novo histórico git** (Passo 0): o repositório nunca foi publicado, então é seguro começar limpo. O backup em `.zip` guarda o passado, e o histórico antigo (com a chave literal) não vai para o GitHub.

## 3. Arquivo por arquivo (decisão)

| Arquivo ou pasta | Decisão | Passo |
| --- | --- | --- |
| `rodar_agente.py` | Refatorar (novos comandos) | 9 |
| `workflow.py` | Remover | 9 |
| `app.py`, `api.py` (FastAPI e painel) | Remover | 1 |
| `pipeline/gerar_artigos.py` | Portar para `gerar_receitas.py` | 9 |
| `pipeline/gerar_noticias.py`, `agents/editor_chefe.py` | Remover | 1 |
| `agents/pesquisador.py` | Reescrever (fontes, busca, extração) | 5 |
| `agents/editor.py` | Reescrever (Chef IA, prompts em arquivo, JSON validado) | 6 |
| `agents/revisor.py`, `agents/seo.py` | Refatorar | 6 |
| `agents/publisher.py` | Substituir pelo cliente do site | 4 |
| `services/llm_service.py` | Refatorar (lista aprovada, contadores) | 2 |
| `services/gemini_service.py`, `services/ollama_service.py` | Remover | 1 |
| `services/github_service.py` | Remover | 1 |
| `services/imagem_service.py`, `services/image_providers/*` | Refatorar | 8 |
| `services/pixabay_service.py` | Corrigir a chave literal; remover se duplicar o seletor | 2 |
| `repositories/artigo_repository.py`, `noticia_repository.py`, `produto_repository.py` | Remover (não migrar); histórico novo em `historico_repository.py` | 1 e 3 |
| `config/database.py` | Manter, ajustando variáveis | 2 |
| `models.py` (SQLite legado) | Remover | 1 |
| `agents/backlog/*`, `social/*`, `passo1-instagram/*`, `scripts/agente/*.ts` | Remover | 1 |
| `*.bak` | Remover | 1 |
| `prompts/*`, `templates/*` | Remover os de tecnologia; criar os novos a partir de `docs/03` | 1 e 6 |
| `scripts/diagnostico_llm.py` | Remover (lógica duplicada) | 1 |
| `.github/workflows/gerar-artigos.yml`, `gerar-noticias.yml` | Substituídos por `gerar-receitas.yml` e `gerar-dicas.yml` (já escritos; ficam desligados até `AGENT_ENABLED` = `true`) | 9 |
| `tests/*` | Manter só o que ainda se aplica (imagens); testes novos por passo | 1 |

## 4. Passo 0: preparação (humano, sem IA)

1. Fazer um `.zip` da pasta do agente, fora do repositório, como backup do projeto atual.
2. `git remote -v`: se houver remoto do DigitalTech, anotar e remover (`git remote remove origin`).
3. **Revogar a chave do Pixabay** (gerar outra na conta) e guardar a nova só em `.env`.
4. Procurar outros segredos literais: `grep -rnE "(api_key|token|secret|password)\s*=\s*['\"][^'\"]{8,}" --include=*.py .` e abrir o `.env.example` para ver se há valores reais.
5. Conferir que `.env` está no `.gitignore`.
6. Depois do Passo 1 (limpeza) e do Passo 2 (segurança): apagar a pasta `.git` e rodar `git init` de novo, para o repositório novo nascer sem o histórico antigo.
7. Copiar os documentos (`docs/`) e apagar `COMO-APLICAR_1.md`, `COMO-APLICAR-agente_1.md`, `LEIA-ME-AGENTE_1.md` e `README_1.md`.

## 5. Ordem e dependências

| Passo | Conteúdo | Depende de |
| --- | --- | --- |
| 1 | Limpeza | Passo 0 |
| 2 | Segurança, configuração e LLM | 1 |
| 3 | Banco do agente (histórico, fila, custo) | 2 |
| 4 | Integração com o site (cliente, contratos, adaptador) | 2; usa o contrato do site (`contracts/`) e roda contra um servidor falso até o Bloco 1 do site terminar |
| 5 | Pesquisa e análise | 2; provedor de busca escolhido |
| 6 | Criação e prompts | 2 |
| 7 | Validadores (7a a 7c) | 5 e 6 (fichas e conteúdo de exemplo) |
| 8 | Imagens | 2 |
| 7d | Verificações de imagem, SEO e contrato | 4 e 8 |
| 9 | Pipeline, CLI e workflows | 3 a 8 |
| 10 | Testes de mutação e golden set | 7 e 9 |
| 11 | Conteúdo educativo (dica, técnica, matéria) | 9 e 10 |

Os passos 1 e 2 podem começar agora. Os passos 3, 5, 6 e 8 são independentes entre si.

## 6. Decisões do responsável antes dos passos que as usam

| Decisão | Necessária no passo | Observação |
| --- | --- | --- |
| Provedor de busca na web | 5 | Verificar plano gratuito, filtro por domínio e termos de uso |
| Modelos aprovados por tarefa (criação, reparo, revisão, visão, extração) | 2 | Provedores com plano gratuito; o revisor precisa de família diferente da do gerador |
| Curadoria de `config/seguranca.json`, `razoes.json`, `plausibilidade.json`, `conversoes.json` | 7 | Por pessoa, para as subcategorias de risco baixo; sem curadoria a família fica desabilitada |
| Catálogo inicial de ingredientes de confeitaria | 7 | Importado no site (Bloco 1) |
| Domínio do Sabores Ajinomoto e termos de uso das fontes | 5 | Portão antes da coleta real |

## 7. Preâmbulo comum (colar no início de **todo** prompt)

```text
Contexto: projeto agente-chocolicia. A especificação está em docs/ (leia
somente as seções citadas, não o diretório inteiro). Regras: trabalhe no
branch atual; nunca leia, imprima ou copie .env, tokens, chaves ou strings de
conexão; nada contra produção; mudanças pequenas, um commit por tarefa; rode
os testes ao final; se algo não bater com o código, pare e relate em vez de
improvisar; responda em português; ao terminar, escreva um resumo de no máximo
15 linhas (o que mudou, testes, pendências).
```

## 8. Prompts por passo

### Passo 1: limpeza

```text
Tarefa: remover do projeto tudo o que é do DigitalTech ou está morto, sem
mexer no caminho principal. Remova com git rm: arquivos *.bak; agents/backlog/;
social/; passo1-instagram/; scripts/agente/ (TypeScript); models.py; app.py;
api.py; pipeline/gerar_noticias.py; agents/editor_chefe.py;
repositories/noticia_repository.py; repositories/produto_repository.py (e o que
for de chats ou produtos); services/gemini_service.py;
services/ollama_service.py; services/github_service.py;
scripts/diagnostico_llm.py. Não apague nem altere .github/workflows/ (os workflows de receitas e dicas já foram escritos). Prompts e templates específicos de tecnologia: liste antes
e mova para _legado/ em caso de dúvida. Não toque em services/image_providers/,
services/llm_service.py, agents/ e pipeline/gerar_artigos.py, exceto para
ajustar imports quebrados (sem criar funcionalidade). Ao final:
python -c "import rodar_agente" deve funcionar e os testes que sobraram devem
rodar. Entregue a lista do que foi removido e do que foi para _legado/.
```

### Passo 2: segurança, configuração e LLM

```text
Leia docs/01-ARQUITETURA.md (seções 14 e 15) e docs/03-PROMPT-SISTEMA.md
(seção 13). Tarefa:
1. Procure e remova qualquer chave ou token literal no código (começando por
   services/pixabay_service.py); leia só de variáveis de ambiente.
2. Crie .gitignore (.env, *.db, output/, content/, logs, __pycache__) e reduza
   .env.example às variáveis realmente usadas, sem valores.
3. Crie config/settings.py com leitura e validação das variáveis, sem expor
   segredos em log.
4. Crie config/modelos_aprovados.json (tarefas: criacao, reparo, revisao,
   extracao, seo, visao; cada uma com lista de {provedor, modelo, familia}),
   deixando o preenchimento dos modelos como comentário/exemplo.
5. Em services/llm_service.py: mantenha só os provedores presentes na lista
   aprovada; remova lógica duplicada e os prompts do DigitalTech; crie
   gerar_texto(tarefa, prompt, ...) que escolhe entre os modelos aprovados da
   tarefa e lança ModeloNaoAprovado se não houver nenhum; contabilize
   requisições e tokens por chamada; mantenha o auxiliar de parse de JSON.
Testes com provedores simulados (mock) para a aprovação e os contadores.
```

### Passo 3: banco do agente

```text
Leia docs/04-ESTRUTURA-CONTEUDO.md (seção 8.9) e docs/07-PUBLICACAO.md
(seção 4). Tarefa: criar db/schema_agente.sql e
repositories/historico_repository.py para agent_runs, agent_generations,
agent_topic_queue e agent_costs, com UNIQUE (content_type, topic_slug) e os
CHECKs da seção 8.9. Funções: reservar_pauta (INSERT ... ON CONFLICT DO
NOTHING, devolve verdadeiro ou falso), atualizar_status, registrar_custo
(unidades em requisições e tokens), proxima_pauta, resumo_cobertura. Crie
scripts/criar_tabelas_agente.py idempotente, que só roda com a variável
DATABASE_URL_AGENTE_TESTE definida (nunca produção) e exige confirmação para
outro banco. Não mexa nas tabelas legadas. Testes das funções.
```

### Passo 4: integração com o site

```text
Leia docs/06-INTEGRACAO.md (seções 4 a 11 e 14) e docs/01-ARQUITETURA.md
(seção 8.4). Tarefa:
1. integration/contratos.py: modelos Pydantic de receita e artigo v1
   (seções 6 e 8). Teste que compara o JSON Schema gerado com o arquivo em
   contracts/ (cópia do site).
2. integration/cliente_site.py (httpx): cabeçalhos Authorization,
   Idempotency-Key, X-Contract-Version e X-Request-Id; tentativas e códigos de
   erro conforme a seção 11; Retry-After; fluxo de confirmação após 409 ou
   timeout (seção 10); nunca registrar o token. Métodos: taxonomia, catálogo,
   cobertura, lookup, criar receita, criar artigo, status.
3. integration/adaptador_receita.py: converte a saída do Chef IA
   (docs/03 seção 6.2) para o payload v1 (docs/06 seção 6.2).
4. Opção --dry-run que imprime o payload sem enviar.
Testes com httpx.MockTransport simulando 201, 400, 401, 403, 409 (reenvio),
422, 429 com Retry-After, 5xx e timeout.
```

### Passo 5: pesquisa e análise

```text
Leia docs/02-PESQUISA.md (inteiro) e docs/PESQUISA-RECEITAS.md (seções 3 a 6,
11 e 12). Tarefa:
1. services/busca_service.py: interface Buscador (consulta, domínios, máximo)
   com um provedor de teste (mock) e o provedor escolhido (a definir); limites
   da seção 4.2 do docs/02.
2. config/fontes.json com os domínios, tipos e pesos da seção 3.1.
3. Reescreva agents/pesquisador.py: planejar consultas, selecionar páginas,
   extrair fichas de fonte (seção 7.1) com a tarefa "extracao" do LLM, saída
   em JSON validado, vocabulário controlado para tecnica_flags. Defesa de
   injeção (seção 10): padrões detectados em código ANTES do LLM e descarte da
   página; o extrator não recebe ferramentas nem segredos. O texto bruto das
   páginas fica só em memória (objeto descartável) para a checagem de
   similaridade.
4. Crie agents/analista.py: normalização de medidas (config/conversoes.json),
   cruzamento de proporções (mediana, outliers de 25%), ficha consolidada
   (seção 7.2) e o gate de aprovação (PESQUISA-RECEITAS seção 12), com rejeição
   e motivo.
Testes com páginas falsas em fixtures (sem rede real).
```

### Passo 6: criação e prompts

```text
Leia docs/03-PROMPT-SISTEMA.md (seções 2, 4 a 6, 10 a 12) e docs/05-SEO.md
(seção 13). Tarefa:
1. Crie prompts/base.md, receita.md, reparo.md, revisor.md e seo.md com os
   textos do documento e o cabeçalho de versão. Remova os prompts de
   tecnologia.
2. Carregador de prompts em camadas (base + módulo + dados entre
   delimitadores + contrato de saída).
3. Reescreva agents/editor.py: criar_receita(ficha, pauta), saída JSON
   validada por Pydantic (SCH), laço de reparo de até 2 tentativas,
   registrando versão do prompt, modelo e tentativas. Remova o bypass
   "briefing=None".
4. Ajuste agents/seo.py conforme a seção 13 do docs/05 (sem alterar fatos).
5. Ajuste agents/revisor.py ao escopo semântico da seção 12.3 do docs/03,
   usando modelo de família diferente da do gerador.
Testes com LLM simulado (JSON válido, inválido, reparo).
```

### Passo 7: validadores (um prompt por parte)

Cada parte cria `validators/` com uma função por verificação, o ID do `08-VALIDACAO.md` como código de rejeição, e testes por ID.

**7a: base, SCH, TAX, HON**

```text
Leia docs/08-VALIDACAO.md (seções 1 a 4.2 e 4.7). Crie validators/base.py
(resultado, gravidade, executor, política de decisão da seção 3) e as
verificações SCH-01 a SCH-07, TAX-01 a TAX-05 e HON-01 a HON-06, lendo
config/frases_proibidas.json, marcas.json e pautas_bloqueadas.json (crie
modelos com poucos exemplos e a estrutura de cada arquivo). Um teste por ID.
```

**7b: NUM e CUL**

```text
Leia docs/08-VALIDACAO.md (seções 4.3 e 4.4) e docs/04 (seções 6.3 e 9). Crie
as verificações NUM-01 a NUM-09 e CUL-01 a CUL-08: extração de números e
unidades dos passos por expressões regulares, comparação com a ficha e com os
campos, regras de precedência de passos, dificuldade calculada. Leia
config/plausibilidade.json, razoes.json e conversoes.json (crie os modelos
vazios com a estrutura; família sem curadoria é bloqueada). Um teste por ID,
incluindo casos de falso positivo.
```

**7c: ALG, SEG, SIM**

```text
Leia docs/08-VALIDACAO.md (seções 4.5, 4.6, 4.8 e 6) e docs/04 (seção 7). Crie
ALG-01 a ALG-05 (catálogo vindo do cliente do site, em cache; etiquetas de
dieta; alegações proibidas), SEG-01 a SEG-07 (sinais de risco por código,
config/seguranca.json; sinal sem entrada rejeita a pauta) e SIM-01 a SIM-04
(sequências de palavras e grupos de 4 palavras contra o texto bruto em
memória; título; duplicidade interna via lookup). Um teste por ID.
```

**7d: IMG, SEO, API (depois dos passos 4 e 8)**

```text
Leia docs/08-VALIDACAO.md (seções 4.9 a 4.11) e docs/05-SEO.md (seção 14).
Crie IMG-01 a IMG-08, SEO-01 a SEO-08 e API-01 a API-04, usando os módulos de
imagem e de integração já existentes. Um teste por ID.
```

### Passo 8: imagens

```text
Leia docs/01-ARQUITETURA.md (seção 8.2) e docs/08-VALIDACAO.md (seção 4.9).
Em services/image_providers/ e services/imagem_service.py:
1. Mantenha ImageSelector, os provedores e o download seguro contra SSRF
   (usado só em memória, para a verificação por visão).
2. Remova o armazenamento local de imagens e o registro SQLite de proveniência;
   a proveniência passa a ser devolvida no formato cover.mode = "stock"
   (docs/06 seção 7.1).
3. Filtro de licença: aceitar CC0, domínio público, licenças próprias dos
   provedores aprovados e CC BY com atribuição; recusar NC, ND, SA e licença
   desconhecida (em Openverse e Wikimedia especialmente).
4. Largura mínima de 1280 px; deduplicação por hash e por URL (consulta ao
   site); descartar imagens com pessoa, texto, logotipo ou marca d'água pela
   tarefa "visao" do LLM (preview em memória).
5. Termos de busca vindos de termos_busca_imagem; trocar o termo de reserva e o
   User-Agent para o Chocolícia; se nenhum candidato servir, devolver
   cover.mode = "generate" com o prompt_imagem.
Testes com respostas simuladas dos provedores (sem rede real).
```

### Passo 9: pipeline, CLI e workflows

```text
Leia docs/01-ARQUITETURA.md (seções 7, 10 e 15) e docs/07-PUBLICACAO.md
(seções 3 a 5, 9 e 13). Tarefa:
1. pipeline/gerar_receitas.py (a partir de pipeline/gerar_artigos.py): etapas
   da seção 7.2, reserva de pauta, fase, tetos de custo, lista de modelos
   aprovados (aborta fora dela), interruptor, teste de fumaça pós-publicação.
2. rodar_agente.py: comandos --receita, --dica, --assunto <slug>, --dry-run e
   --target preview|producao; remover workflow.py e os comandos de notícia.
   Ao final de toda execução, gravar output/resumo-execucao.md (pauta, estado,
   motivo de rejeição, custo; nunca segredos), lido pelos workflows.
3. Conferir que .github/workflows/gerar-receitas.yml e gerar-dicas.yml (já
   escritos) chamam comandos que existem e que as variáveis de ambiente que
   eles definem são as lidas por config/settings.py (SITE_BASE_URL,
   SITE_TOKEN_DRAFT, SITE_TOKEN_PUBLISH, DATABASE_URL_AGENTE, PESQUISA_*,
   chaves dos provedores aprovados, AGENT_PHASE, CONTRACT_VERSION, TARGET,
   DRY_RUN, ASSUNTO). Criar verificador-ausencia.yml (alarme de 36 horas).
Teste de ponta a ponta com LLM, busca e site simulados, conferindo os estados
gravados no histórico.
```

### Passo 10: mutação e golden set

```text
Leia docs/08-VALIDACAO.md (seções 7 a 9). Crie tests/fixtures/receitas_validas/
(10 receitas de risco baixo, escritas à mão para teste), tests/test_mutacao.py
dirigido pela tabela de 51 mutações (a fixture válida deve passar e cada
mutação deve ser rejeitada pela verificação esperada), o golden set com fichas
congeladas e um workflow testes.yml. Falhar a integração contínua se qualquer
mutação determinística passar.
```

### Passo 11: conteúdo educativo (depois)

Dicas nos seis assuntos de `docs/04` (seção 6.7), técnicas e matérias, com `pipeline/gerar_conteudo_educativo.py`, módulos de prompt de `docs/03` (seções 7 a 9) e `POST /api/articles`. Os assuntos de dica `equipamentos-compra` e `negocios` exigem as verificações HON-07 e HON-08. O prompt é escrito depois que as receitas estiverem estáveis.

## 9. Como gastar menos tokens (planos gratuitos)

- Um passo por conversa; abrir conversa nova a cada passo.
- O assistente lê só as seções de `docs/` citadas, não o diretório.
- Não colar logs inteiros; só as últimas linhas do erro.
- Commit depois de cada passo, para poder voltar.
- Testes com dados simulados: nenhuma chamada real a LLM, busca ou site durante o desenvolvimento.
- Se o limite acabar no meio de um passo, parar no último commit e retomar depois; os prompts são independentes.
