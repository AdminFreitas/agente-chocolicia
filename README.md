# agente-chocolicia

Agente Python responsável por pesquisar, gerar, validar e publicar automaticamente receitas e conteúdos culinários da Chocolícia.

**Documento de decisão obrigatório:** [Decisões canônicas do projeto Chocolícia](docs/DECISOES-CANONICAS-CHOCOLICIA.md). Em caso de conflito, ele prevalece sobre documentação histórica.

## Responsabilidades

- O agente é responsável por gerar receitas, dicas, técnicas e matérias culinárias.
- O agente executa validações de qualidade culinária, estrutura, SEO e contrato.
- A publicação ocorre pela API oficial da Chocolícia.
- O site recebe, armazena e apresenta o conteúdo; não gera conteúdo em paralelo.
- O agente não acessa diretamente o banco Neon do site.

## Conteúdo e ingredientes

Receitas apresentam ingredientes, quantidades e modo de preparo com clareza. Não há detecção de alergias individuais, catálogo obrigatório de alérgenos, bloqueio por ingredientes, avisos médicos genéricos ou recomendações de marcas/substituições por motivos médicos. A decisão de utilizar e consumir os ingredientes é do leitor.

A validação trata de qualidade culinária e integridade: coerência entre ingredientes e etapas, quantidades, unidades, tempos, temperaturas, rendimento, estrutura, originalidade e contrato da API.

## Execução

Os pontos de entrada operacionais são `rodar_conteudo.py` para receitas e `python -m pipeline.gerar_dica` para dicas. Os workflows correspondentes estão em `.github/workflows/`.

O serviço Python compartilhado de IA utiliza provedores em nuvem configurados por variáveis de ambiente. Ollama não é requisito operacional.

## Integração

URLs e credenciais são configuradas por variáveis de ambiente; nunca registrar valores secretos no repositório. O agente comunica-se com o site exclusivamente pela API. A disponibilidade dos endpoints e a compatibilidade integral dos contratos ainda dependem da validação autorizada.

## Desenvolvimento

As alterações desta etapa permanecem em `fix/gemini-client-lifecycle`. Não executar testes, workflows, geração/publicação real, migrações ou deploy sem autorização explícita.
