# agente-chocolicia

Agente Python responsável por pesquisar, gerar, validar e publicar automaticamente receitas e conteúdos culinários da Chocolícia.

**Documento de decisão obrigatório:** [Decisões canônicas do projeto Chocolícia](docs/DECISOES-CANONICAS-CHOCOLICIA.md). Em caso de conflito, ele prevalece sobre documentação histórica.

## Responsabilidades

- O agente é o único responsável por gerar receitas, dicas, técnicas e matérias culinárias.
- O agente executa a validação automática de qualidade culinária, estrutura, SEO e contrato.
- A publicação é automática pelo cliente/API oficial da Chocolícia; não existe revisão humana obrigatória.
- O site recebe, armazena e apresenta o conteúdo. Não gera receitas ou dicas em paralelo.
- O agente não acessa diretamente o banco Neon do site.

## Conteúdo e ingredientes

A receita deve apresentar ingredientes, quantidades e modo de preparo com clareza. Não há detecção de alergias individuais, catálogo de alérgenos, bloqueio por presença de ingredientes, aviso médico genérico ou recomendação de marcas/substituições por motivos médicos. A decisão de utilizar e consumir os ingredientes é do leitor.

A validação deve tratar de qualidade culinária e integridade: coerência entre ingredientes e etapas, quantidades, unidades, tempos, temperaturas, rendimento, estrutura, originalidade e contrato da API.

## Execução

O ponto de entrada e os comandos operacionais devem ser mantidos na documentação do próprio agente e alinhados ao serviço Python compartilhado de IA. Ollama está fora do escopo operacional atual e não é pré-requisito.

Não utilizar fluxos antigos de artigos/notícias, feeds RSS de tecnologia, publicação no GitHub DigitalTech ou acesso a tabelas antigas de artigos.

## Integração

O agente publica pelo cliente oficial da API Chocolícia. Credenciais e URLs são configuradas por variáveis de ambiente; nunca registrar valores secretos no repositório.

## Desenvolvimento

As alterações desta etapa permanecem em `fix/gemini-client-lifecycle`. Não executar testes, workflows, geração/publicação real, migrações ou deploy sem autorização explícita.
