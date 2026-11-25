# Decisões canônicas do projeto Chocolícia

> Este documento prevalece sobre instruções conflitantes nos documentos antigos. A documentação herdada do DigitalTech e as especificações anteriores que contrariem estas decisões devem ser corrigidas ou removidas durante a consolidação da Etapa 3.

## Objetivo e responsabilidade

O repositório `agente-chocolicia` contém o agente responsável por planejar, pesquisar, criar, validar e publicar automaticamente receitas e conteúdos culinários da Chocolícia.

**Quem gera o conteúdo é o agente.** O backend do site recebe, armazena e apresenta o conteúdo; não substitui o agente nem executa uma segunda geração paralela. O agente envia o conteúdo ao site pela API. Não grava diretamente no banco Neon do site.

A publicação automática faz parte do funcionamento esperado. Não existe etapa obrigatória de revisão humana, aprovação manual, janela de veto ou teste prático de receita antes da publicação. A validação automática do próprio agente continua responsável por conferir estrutura, coerência culinária, campos obrigatórios e contrato da API.

## Escopo editorial

O agente produz:
- receitas;
- dicas culinárias;
- técnicas de preparo;
- matérias e conteúdos educativos relacionados à culinária e confeitaria.

Não produz notícias, artigos de tecnologia, conteúdo DigitalTech, feeds RSS de tecnologia ou pautas de programação, cibersegurança, cloud e assuntos semelhantes.

## Ingredientes, alergias e saúde

A receita deve informar corretamente os ingredientes, quantidades, unidades e modo de preparo.

A Chocolícia não identifica alergias individuais dos leitores, não mantém catálogo de alérgenos para bloquear receitas, não classifica receitas como seguras para pessoas específicas e não recomenda marcas ou substituições por motivos médicos.

A escolha dos ingredientes e a decisão de preparar ou consumir a receita cabem ao leitor. Se uma receita pede leite, camarão, ovos ou qualquer outro ingrediente, esse ingrediente deve constar normalmente na lista. Não se deve bloquear a receita porque alguém pode ser alérgico a um ingrediente.

Não inserir avisos médicos genéricos, advertências clínicas, aconselhamento nutricional ou instruções para diagnosticar condições de saúde. O projeto é um site de receitas, não um serviço médico ou nutricional.

O agente não deve fazer alegações terapêuticas ou promessas de cura, tratamento ou benefício médico. Isso não impede conteúdo culinário comum nem a publicação de receitas com ingredientes usuais.

## Qualidade culinária

A validação automática deve se concentrar em:
- coerência entre ingredientes, quantidades e etapas;
- clareza e sequência do modo de preparo;
- plausibilidade culinária de tempos, temperaturas e rendimento;
- integridade do JSON e aderência ao contrato do site;
- originalidade do texto e qualidade editorial;
- SEO, imagem e metadados exigidos pelo contrato.

Uma falha de qualidade culinária ou de estrutura pode impedir o envio até que o agente corrija o conteúdo. A mera presença de um ingrediente que possa causar alergia não é falha.

## Arquitetura de execução

1. Um ponto de entrada do agente coordena receitas e conteúdos educativos.
2. Os módulos de pauta, pesquisa culinária, geração, validação, SEO e imagem são reutilizáveis e compartilhados quando apropriado.
3. Um serviço de IA central controla a ordem de provedores e registra o provedor e modelo efetivamente utilizados.
4. O agente publica pelo cliente/API oficial da Chocolícia.
5. O site valida o contrato, persiste os dados e os apresenta. Não gera o conteúdo em paralelo.
6. O histórico operacional do agente pode ficar em banco próprio; o banco do site só é acessado por sua API.

O Ollama está temporariamente fora do escopo operacional. Não é requisito para consolidar a arquitetura nem para continuar as correções. Não executar novas tentativas de configuração do Ollama nesta etapa.

## Limites operacionais desta etapa

As alterações devem permanecer na branch `fix/gemini-client-lifecycle`. Não tocar em `main`, não fazer merge, não executar testes, workflows, geração ou publicação real, migrações ou deploy. Essas ações dependem de autorização posterior do responsável pelo projeto.


## Execução e publicação

O agente Python é responsável por gerar, validar e publicar automaticamente receitas e dicas pela API Chocolícia. Os workflows apenas acionam o agente; o backend do site não gera conteúdo. Não há revisão humana obrigatória. Ollama está fora do escopo operacional atual; o serviço compartilhado utiliza os provedores em nuvem configurados em `FALLBACK_ORDER`.
