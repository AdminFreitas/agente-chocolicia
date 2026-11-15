"""Fakes de LLM para os testes da Etapa 2. Nunca fazem chamada de rede."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.editor import RespostaLLM


@dataclass
class GeradorFalso:
    """Devolve, em ordem, uma resposta por chamada (fila)."""

    respostas: list[str]
    modelo: str = "modelo-fake-1"
    chamadas: list[tuple[str, list[dict[str, str]]]] = field(default_factory=list)

    def gerar_texto(self, tarefa: str, mensagens: list[dict[str, str]]) -> RespostaLLM:
        self.chamadas.append((tarefa, mensagens))
        if not self.respostas:
            raise AssertionError("GeradorFalso ficou sem respostas na fila")
        conteudo = self.respostas.pop(0)
        return RespostaLLM(conteudo=conteudo, modelo=self.modelo)
