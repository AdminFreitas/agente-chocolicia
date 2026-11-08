# Prompt: mapa do projeto do agente (para o assistente do VS Code)

Use este prompt com o assistente do VS Code, aberto na pasta do agente. Ele **só lê** o projeto e gera um arquivo pequeno (`MAPA-DO-PROJETO.md`) que você pode anexar aqui. Gasta poucos tokens porque a saída é um resumo, não o código.

---

**COLE A PARTIR DAQUI**

Leia este projeto (o agente que gera artigos e notícias de tecnologia) e crie o arquivo `MAPA-DO-PROJETO.md` na raiz. **Não altere nenhum outro arquivo.**

Regras:
- Nunca abra, leia, copie ou mostre arquivos `.env` (apenas `.env.example`, e sem copiar valores). Em nenhuma parte da resposta escreva chaves, tokens, senhas ou strings de conexão.
- Ignore `node_modules`, `.git`, `__pycache__`, ambientes virtuais, logs e arquivos binários.
- Não cole trechos longos de código. No máximo 5 linhas por exemplo.
- O arquivo final deve ter no máximo 400 linhas, em português.

O arquivo deve conter:

1. **Estrutura:** árvore de pastas e arquivos (até 3 níveis).
2. **Por arquivo de código** (um bloco curto cada): para que serve, funções e classes principais (nome e uma linha de descrição), serviços externos que usa e quais variáveis de ambiente lê (**só os nomes**).
3. **Fluxo de execução:** como `rodar_agente.py` (ou o ponto de entrada) chama cada etapa até a publicação, passo a passo.
4. **Banco de dados:** tabelas, colunas e quem lê e grava cada uma.
5. **Modelos de IA:** quais provedores e modelos, em que ordem de fallback, e onde os prompts ficam.
6. **Pesquisa e imagens:** fontes de dados e serviços usados.
7. **Publicação:** como o conteúdo sai do agente (GitHub, banco, API).
8. **Agendamento e testes:** workflows, cron, testes existentes.
9. **Dependências:** conteúdo resumido de `requirements.txt`.
10. **O que é específico de tecnologia/DigitalTech:** liste cada lugar (arquivo e função) com prompts, categorias, feeds RSS, termos de busca de imagem, nomes de repositório e textos que falam de tecnologia.
11. **Código morto ou duplicado** que você notar.
12. **Pontos de atenção:** erros prováveis, tratamento de erros ausente, lugares que gravam direto no banco ou no GitHub.

Termine com uma tabela: `arquivo | o que faz | manter / refatorar / remover (sua sugestão)`.

---

## Como usar o resultado

- Anexe aqui o `MAPA-DO-PROJETO.md` (ele é pequeno). Com ele, escrevo os prompts do agente (Blocos 5 a 7) com os nomes reais das suas funções.
- Se eu precisar ver o código de algum arquivo, peço só aquele arquivo ou uso o `snapshot_projeto.py`.
