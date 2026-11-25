# Documentação do agente Chocolícia

Este diretório contém a documentação operacional e as decisões canônicas do agente de conteúdo culinário.

## Documento principal

- [Decisões canônicas Chocolícia](DECISOES-CANONICAS-CHOCOLICIA.md): escopo, responsabilidades, regras editoriais, validação e publicação. Em caso de conflito, este documento prevalece.

## Documentos complementares

- [Integração agente–site](06-INTEGRACAO.md): clientes, contratos e comunicação pela API.
- [Pesquisa de receitas](PESQUISA-RECEITAS.md): processo de pesquisa e coleta de referências.
- [Taxonomia inicial](taxonomy.seed.json): estrutura inicial de categorias e subcategorias.

## Escopo

O agente trabalha com receitas, dicas, técnicas e matérias culinárias. Não utiliza fluxos de notícias, RSS de tecnologia, publicação em repositórios de terceiros ou tabelas antigas de artigos. Não acessa diretamente o banco Neon do site.

Ollama está fora do escopo operacional atual. Os provedores de IA ativos são configurados por variáveis de ambiente.

Documentos históricos ou instruções que contrariem as decisões canônicas não devem orientar a implementação.
