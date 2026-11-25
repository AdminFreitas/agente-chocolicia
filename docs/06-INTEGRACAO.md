# Integração entre o agente e o site Chocolícia

## Princípio

O agente Python gera e valida o conteúdo. O site recebe, autentica, persiste e apresenta esse conteúdo. O agente não acessa diretamente o banco Neon do site.

## Receitas

O ponto de entrada atual é `rodar_conteudo.py`. O fluxo usa `integration.content`, `services.llm_service` e `integration.site_client`.

O endpoint e o contrato de receitas utilizados por esse cliente ainda precisam ser comparados com a implementação do site durante a validação autorizada. Não considerar a publicação confirmada apenas porque o cliente e o workflow existem.

## Dicas, técnicas e matérias

O fluxo de dicas é iniciado por `python -m pipeline.gerar_dica`. Ele utiliza `agente_receitas.integration.ClienteSite` e o modelo Pydantic `ArtigoV1`, com envio para `POST /api/articles`.

A implementação do endpoint no repositório do site e sua disponibilidade em Preview/produção devem ser verificadas antes da ativação. O código do agente, isoladamente, não comprova que a rota esteja implantada ou que aceite o contrato esperado.

## Autenticação e configuração

URLs e tokens são fornecidos por variáveis de ambiente e secrets do GitHub Actions. Não registrar valores secretos em arquivos versionados, logs ou documentação.

Os workflows selecionam o ambiente de destino e o token correspondente. O agente deve chamar apenas a API do site; não utilizar conexões diretas ao Neon do site nem publicar conteúdo por commits em repositórios de código.

## Validação pendente

Na etapa de validação autorizada, confirmar:

1. Assinaturas e formatos esperados por `integration.content` e `integration.site_client`.
2. Campos obrigatórios e validações do payload de receitas.
3. Campos obrigatórios de `ArtigoV1` e compatibilidade com `POST /api/articles`.
4. Autenticação, URL e seleção correta de Preview/produção.
5. Resposta de sucesso da API e persistência/exibição pelo site.

Até essa validação, não afirmar que os fluxos de publicação estão operacionais.
