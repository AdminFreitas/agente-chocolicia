"""
testa_site.py — Testa a integração com o site Chocolícia de forma isolada,
sem envolver o agente. Envia uma receita de teste como rascunho (draft).

Uso:
    $env:SITE_BASE_URL = "https://www.chocolicia.com"   # ou URL do preview
    $env:SITE_TOKEN_DRAFT = "seu_token_aqui"
    python testa_site.py

    # Para ver o payload sem enviar:
    python testa_site.py --dry-run

Interpretação da resposta:
    201  → Site funciona. Só falta o agente produzir esse JSON.
    401/403 → Token errado ou escopo. Verificar configuração na Vercel.
    400/422 → Campo em formato errado. A mensagem mostra qual; ajuste o payload.
    404  → Rota não existe. O site precisa do Bloco 1 (CODEX-01).
    Erro de conexão → SITE_BASE_URL errada.
"""
import os
import sys
import json

# Verifica dependência
try:
    import httpx
except ImportError:
    print("ERRO: httpx não instalado. Execute: pip install httpx")
    sys.exit(1)

DRY_RUN = "--dry-run" in sys.argv

base = os.environ.get("SITE_BASE_URL", "").rstrip("/")
token = os.environ.get("SITE_TOKEN_DRAFT", "")

if not base and not DRY_RUN:
    print("ERRO: variável SITE_BASE_URL não definida.")
    print("  $env:SITE_BASE_URL = 'https://www.chocolicia.com'")
    sys.exit(1)

if not token and not DRY_RUN:
    print("ERRO: variável SITE_TOKEN_DRAFT não definida.")
    print("  $env:SITE_TOKEN_DRAFT = 'seu_token_aqui'")
    sys.exit(1)

if DRY_RUN and not base:
    base = "https://www.chocolicia.com"  # placeholder para dry-run

# Payload de teste — segue o contrato legado documentado em 01-ARQUITETURA.md §3.2
# Ajuste os nomes dos campos conforme o schema Zod real do site se houver divergência
payload = {
    "title": "Brigadeiro de Teste — Integração Agente↔Site",
    "excerpt": (
        "Receita de teste enviada automaticamente pelo agente para validar "
        "a integração com o site. Pode apagar com segurança."
    ),
    "category": "Brigadeiros e docinhos",
    "coverImageUrl": "https://images.pexels.com/photos/3026808/pexels-photo-3026808.jpeg",
    "prepTimeMin": 10,
    "cookTimeMin": 15,
    "servings": 8,
    "difficulty": "Fácil",
    "ingredients": [
        {
            "name": "Base",
            "items": [
                {"name": "leite condensado", "quantity": "395", "unit": "g"},
                {"name": "chocolate em pó", "quantity": "3", "unit": "colheres de sopa"},
                {"name": "manteiga", "quantity": "1", "unit": "colher de sopa"},
            ],
        }
    ],
    "steps": [
        {"instruction": "Misture o leite condensado, o chocolate em pó e a manteiga em uma panela."},
        {"instruction": "Leve ao fogo médio, mexendo sempre, até desgrudar do fundo."},
        {"instruction": "Deixe esfriar e enrole em bolinhas."},
        {"instruction": "Passe no granulado de chocolate e sirva."},
    ],
    "status": "draft",
    # Aviso obrigatório de conteúdo gerado por IA
    "aiDisclaimer": "Conteúdo gerado por inteligência artificial. Revise antes de publicar.",
}

url = f"{base}/api/recipes"

print(f"URL: {url}")
print(f"Status alvo: draft")
print(f"Modo: {'DRY-RUN (sem envio)' if DRY_RUN else 'ENVIO REAL'}")
print("-" * 50)

if DRY_RUN:
    print("PAYLOAD (dry-run):")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\n[Dry-run concluído — nenhuma requisição enviada]")
    sys.exit(0)

try:
    r = httpx.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    print(f"STATUS HTTP: {r.status_code}")
    print(f"HEADERS DE RESPOSTA relevantes:")
    for h in ("content-type", "x-request-id", "cf-ray"):
        if h in r.headers:
            print(f"  {h}: {r.headers[h]}")

    print(f"\nCORPO DA RESPOSTA:")
    try:
        body = r.json()
        print(json.dumps(body, ensure_ascii=False, indent=2))
    except Exception:
        print(r.text[:1000])

    # Interpretação
    print("\n" + "=" * 50)
    if r.status_code == 201:
        print("✓ SUCESSO: Receita criada como rascunho no site.")
        try:
            recipe_id = r.json().get("id") or r.json().get("data", {}).get("id")
            if recipe_id:
                print(f"  ID da receita: {recipe_id}")
        except Exception:
            pass
        print("  → Próximo passo: fazer o agente produzir esse JSON.")
    elif r.status_code in (401, 403):
        print("✗ AUTENTICAÇÃO: Token inválido ou sem permissão.")
        print("  → Verificar SITE_TOKEN_DRAFT e escopos na Vercel.")
    elif r.status_code in (400, 422):
        print("✗ PAYLOAD INVÁLIDO: Algum campo está errado ou faltando.")
        print("  → Veja a mensagem de erro acima e ajuste o payload.")
    elif r.status_code == 404:
        print("✗ ROTA NÃO ENCONTRADA: /api/recipes não existe no site.")
        print("  → O site precisa do Bloco 1 do CODEX-01.")
    elif r.status_code >= 500:
        print("✗ ERRO DO SERVIDOR: Problema interno no site.")
        print("  → Verificar logs da Vercel.")
    else:
        print(f"? RESPOSTA INESPERADA: {r.status_code}")

except httpx.ConnectError as e:
    print(f"ERRO DE CONEXÃO: Não foi possível conectar a {base}")
    print(f"  Detalhe: {e}")
    print("  → Verificar se SITE_BASE_URL está correta.")
except httpx.TimeoutException:
    print(f"TIMEOUT: O site não respondeu em 30s.")
    print("  → Verificar se o site está online.")
except Exception as e:
    print(f"ERRO INESPERADO: {e}")
    raise
