"""
smoke_test_perplexity.py — Smoke test para a integração com a Perplexity Search API.

Executa uma consulta mínima e verifica o status HTTP e formato da resposta.
Nunca imprime, loga ou persiste a chave de API (PERPLEXITY_API_KEY).
"""

from __future__ import annotations

import argparse
import os
import sys

# Garante que a raiz do projeto esteja no sys.path para execução direta do script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Carrega variáveis locais do .env se existir
load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test para a Perplexity Search API"
    )
    parser.add_argument(
        "--query",
        type=str,
        default="trufa de chocolate",
        help="Consulta para o teste (padrão: 'trufa de chocolate')",
    )
    parser.add_argument(
        "--country",
        type=str,
        default="BR",
        help="Código de país ISO 3166-1 alpha-2 (padrão: 'BR')",
    )
    args = parser.parse_args()

    api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        print("[-] ERRO: A variável de ambiente PERPLEXITY_API_KEY não foi encontrada.")
        print("[-] Para executar o smoke test com a API real:")
        print("    1. Gere uma chave em: https://console.perplexity.ai")
        print("    2. Exporte a variável no seu terminal:")
        print("       PowerShell: $env:PERPLEXITY_API_KEY='sua-chave-aqui'")
        print("       Bash/Linux: export PERPLEXITY_API_KEY='sua-chave-aqui'")
        print("    (Importante: nunca envie ou cole a chave de API no chat).")
        return 1

    print("[*] PERPLEXITY_API_KEY detectada no ambiente (presença confirmada).")
    print(f"[*] Enviando requisição de teste para Perplexity Search API...")
    print(f"    Consulta: '{args.query}' | max_results: 1 | country: '{args.country}'")

    try:
        from services.busca_service import BuscadorPerplexity

        buscador = BuscadorPerplexity(country=args.country)
        resultados = buscador.buscar(
            consulta=args.query,
            max_resultados=1,
        )

        print("[+] Resposta recebida com sucesso! (Status HTTP: 200 OK)")
        print(f"[+] Quantidade de resultados: {len(resultados)}")
        if resultados:
            primeiro = resultados[0]
            print(f"[+] Estrutura do resultado:")
            print(f"    - URL: {primeiro.url}")
            print(f"    - Título: {primeiro.titulo}")
            print(f"    - Domínio: {primeiro.dominio}")
            print(f"    - Snippet: {primeiro.snippet[:120]}..." if len(primeiro.snippet) > 120 else f"    - Snippet: {primeiro.snippet}")
            print(f"    - Data: {primeiro.date}")
            print(f"    - Última atualização: {primeiro.last_updated}")
        return 0

    except Exception as exc:
        nome_erro = exc.__class__.__name__
        msg = str(exc)
        print(f"[-] Falha na requisição: {nome_erro}")
        print(f"[-] Detalhe: {msg}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
