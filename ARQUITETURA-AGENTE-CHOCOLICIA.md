# Arquitetura do agente Chocolícia

## Objetivo

O agente Python pesquisa, gera, valida e publica automaticamente receitas e conteúdos culinários. O site Chocolícia recebe o conteúdo pela API, persiste os dados e apresenta as páginas ao público.

As decisões editoriais e operacionais oficiais estão em [docs/DECISOES-CANONICAS-CHOCOLICIA.md](docs/DECISOES-CANONICAS-CHOCOLICIA.md).

## Responsabilidades

**Agente Python**
- Pesquisa e seleção de referências culinárias.
- Geração de receitas, dicas, técnicas e matérias.
- Validação de coerência culinária, estrutura, originalidade, SEO e contrato.
- Publicação pela API do site.

**Site Chocolícia**
- Autenticação das chamadas do agente.
- Recepção e persistência do conteúdo.
- Exibição pública e recursos editoriais do site.

O agente não acessa diretamente o banco Neon do site. O backend do site não gera conteúdo em paralelo.

## Fluxos presentes no repositório

### Receitas

O ponto de entrada atual é `rodar_conteudo.py`. Ele utiliza `integration.content`, o serviço compartilhado `services.llm_service` e o cliente `integration.site_client`.

A compatibilidade integral do payload e do endpoint de receitas com o site ainda precisa ser confirmada na validação autorizada. A presença do cliente no repositório não comprova que a publicação esteja operacional.

### Dicas

O ponto de entrada atual é `python -m pipeline.gerar_dica`. Ele utiliza o serviço compartilhado de IA e os contratos `ArtigoV1` / `ClienteSite` do pacote `agente_receitas.integration`, com publicação pelo endpoint `POST /api/articles`.

A disponibilidade desse endpoint no ambiente de destino e a aceitação do contrato precisam ser confirmadas antes de considerar o fluxo operacional.

## Provedores de IA

O serviço compartilhado é `services/llm_service.py`. A ordem padrão de fallback é Groq, Gemini e OpenRouter, configurável por `FALLBACK_ORDER`. As credenciais são fornecidas pelo ambiente e nunca devem ser registradas no Git.

Ollama não faz parte do escopo operacional atual.

## Execução e ambientes

Os workflows de receitas e dicas estão em `.github/workflows/` e utilizam runners hospedados Ubuntu. A configuração de Preview e produção é feita por variáveis e secrets do GitHub Actions.

Alterações de código devem permanecer na branch de trabalho até revisão. Testes, execução de workflows, geração/publicação real, migrações e deploy dependem de autorização explícita.

## Limites editoriais

Ingredientes, quantidades e modo de preparo são apresentados normalmente. A validação é culinária e técnica; não há triagem clínica, detecção de alergias individuais, bloqueio de ingredientes ou avisos médicos genéricos. O leitor decide quais ingredientes utilizar e consumir.
