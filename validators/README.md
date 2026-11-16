# Validadores

Interface atual: `validar_conteudo(conteudo: dict, contexto: dict | None) -> ResultadoValidacao`.
`ResultadoValidacao.falhas` contém `FalhaValidacao(id, gravidade, detalhe, campo)`;
`aprovado` só é verdadeiro quando não há falhas bloqueantes. O módulo não faz
rede nem chama LLM. Curadorias vazias bloqueiam somente os riscos que dependem
delas.

Status atual por ID de `docs/08-VALIDACAO.md`:

| Família | IDs | Status |
|---|---|---|
| SCH | SCH-01, SCH-05, SCH-07 | parcial |
| TAX | TAX-01, TAX-05 | parcial |
| NUM | NUM-07, NUM-08 | parcial |
| CUL | CUL-06, CUL-08 | parcial |
| ALG | ALG-01, ALG-05 | parcial |
| SEG | SEG-02 | parcial |
| HON | HON-01 | parcial |
| SIM | SIM-01 | parcial |
| IMG | IMG-08 | parcial |
| SEO | SEO-01 | parcial |
| API | — | não implementado |

Os demais IDs permanecem não implementados e aguardam a frente responsável
pelos validadores. Não usar este pacote como autorização para publicar.
