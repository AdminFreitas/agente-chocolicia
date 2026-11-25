# Documentação do Agente Chocolícia

Esta documentação descreve exclusivamente o agente Python que gera, valida e publica receitas e conteúdos culinários no site Chocolícia.

**Fonte de verdade:** [Decisões canônicas do projeto](DECISOES-CANONICAS-CHOCOLICIA.md). Documentos antigos só permanecem válidos quando não contradizem esse documento.

## Regras operacionais

- O agente gera receitas, dicas, técnicas e matérias culinárias.
- O agente valida automaticamente a qualidade culinária e a integridade do conteúdo.
- O agente publica automaticamente pela API oficial do site; revisão humana não é obrigatória.
- O site recebe, persiste e apresenta o conteúdo. Não realiza uma segunda geração.
- O agente não acessa diretamente o banco Neon do site.
- Ollama está temporariamente fora do escopo e não é requisito.
- Não existem bloqueios por alergias individuais, identificação de alérgenos, avisos médicos genéricos ou exigência de recomendar marcas/substituições.
- Ingredientes como leite, camarão, ovos, margarina e outros devem ser listados normalmente quando fizerem parte da receita. O leitor decide quais ingredientes pode utilizar.
- Não inserir avisos fixos sobre alergias, rótulos ou condições médicas.
- Não fazer promessas de cura, tratamento ou benefício médico. Isso não restringe receitas culinárias comuns.

## Escopo

Inclui pesquisa culinária, geração de receitas e dicas, técnicas de preparo, conteúdos educativos, validação culinária, imagens, SEO, metadados e integração com a API Chocolícia.

Exclui notícias, artigos de tecnologia, feeds RSS de tecnologia, classificadores de notícias, categorias e prompts DigitalTech, banco/tabelas antigos de artigos e publicação no repositório GitHub DigitalTech.

## Documentos

Os documentos numerados existentes estão em processo de alinhamento. Quando houver divergência, prevalece `DECISOES-CANONICAS-CHOCOLICIA.md`. Não executar instruções antigas de fases, aprovações humanas, bloqueios por alergias, publicação em GitHub ou geração pelo backend do site.
