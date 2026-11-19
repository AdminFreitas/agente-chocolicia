# Camada de adaptadores runtime — Chocolícia

Este pacote acrescenta adaptadores sem substituir `pipeline/gerar_receitas.py`,
`pipeline/gerar_conteudo_educativo.py`, `rodar_agente.py` nem os validadores
corrigidos do checkout local.

## O que entrega
- Pesquisa real Brave Search API, com filtro final por domínios autorizados.
- Cliente LLM compatível com API Chat Completions; modelo e família explícitos por tarefa.
- Seleção de categorias do enum atual de receitas, sem presumir disponibilidade da API de taxonomia.
- Persistência PostgreSQL para execuções, custos, imagens utilizadas e publicações.
- Fábrica do `ClienteSite` existente, respeitando fase, contrato e dry-run.
- Configuração por ambiente e testes unitários básicos.

## Instalação
As dependências abaixo já constam do `requirements.txt` da branch consultada:
`httpx`, `sqlalchemy`, `psycopg2-binary`. Instale também `pytest` para testes.

Copie `runtime_adapters/` para a raiz do projeto e mescle `.env.example.runtime`
com seu `.env.example`. Não copie segredos.

## Ativação segura
1. Comece com `AGENT_ENABLED=false`.
2. Configure banco de desenvolvimento, chave Brave e chave LLM.
3. Preencha modelo **e família** para criação, reparo, revisão e SEO. A família
   é uma declaração de configuração e não é inferida pelo adaptador.
4. Configure `SITE_BASE_URL` para preview e o token atual `RECIPES_AGENT_TOKEN`.
5. Mantenha `SITE_CONTRACT=legacy`, `AGENT_PHASE=0` e `DRY_RUN=true` até concluir a integração.
6. O cliente legado só envia `draft`; publicação está bloqueada, sem token publish.

## Integração com os pipelines
`runtime_adapters.cli_contract.build_services()` entrega:
- `buscadores`
- `gerar`
- `cliente_site`
- `catalogo`
- `historico`
- `runtime`

Mapeie esses serviços para os campos dos dataclasses de dependências
existentes no checkout local. A assinatura dos pipelines foi deliberadamente
preservada porque a cópia remota da branch consultada contém versões anteriores
de `rodar_agente.py` e `pipeline/gerar_receitas.py`, diferentes das alterações
locais informadas. Não substitua esses arquivos com esta versão.

## Limites explícitos
- O adaptador de busca implementa Brave. O leitor HTTP de páginas não é ativado:
  antes é necessário validar termos de uso, robots.txt e fontes autorizadas.
- Os endpoints de taxonomia e lookup não estão disponíveis no contrato observado.
  O agente não envia subcategoria sem poder verificar que está ativa/habilitada;
  duplicidade é reservada no banco do agente e conflitos de slug do site falham.
- `POST /api/articles` e a pesquisa composta de dicas seguem bloqueados; não há
  envio de dicas até esses componentes estarem disponíveis e testados.
- O esquema PostgreSQL é criado por `PostgresStore.migrate()`. Ajuste-o à
  política de retenção e às tabelas já existentes antes de produção.
- Não foram inventados nomes/famílias de modelos. O pipeline deve continuar
  falhando fechado se revisão independente não estiver garantida.
- Não completa a cobertura dos IDs SCH/TAX/NUM/CUL/ALG/SEG/HON/SIM/IMG/SEO/API.
  IDs ausentes continuam bloqueantes; não se deve declarar cobertura sem regra
  implementada e testada.
- A conexão da CLI ao pipeline permanece como último encaixe dependente dos
  dataclasses reais do checkout local. Este pacote não afirma execução ponta a
  ponta já validada.
- Nenhum deploy, publicação ou acesso à produção é executado por estes arquivos.
