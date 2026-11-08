"""
artigo_repository.py — Acesso ao banco de dados para artigos

Grava e consulta artigos direto na tabela `artigos` do Neon (o mesmo banco
que o site DigitalTech lê).

Alterações nesta versão (rodada de integração com o painel):
  - COLUNAS_ATUALIZAVEIS ganhou categoria_id, conteudo_md, conteudo_html e
    tempo_leitura -- antes, uma edição de conteúdo ou categoria feita pelo
    painel era aceita pela API mas descartada silenciosamente aqui dentro,
    porque essas colunas não estavam na allowlist.
  - atualizar() agora recalcula conteudo_html e tempo_leitura sempre que
    conteudo_md é enviado, do mesmo jeito que criar() já fazia.
"""

import os
import markdown
from sqlalchemy.orm import Session
from sqlalchemy import text

AUTOR_ID_AGENTE = int(os.getenv("AGENTE_AUTOR_ID", "2"))

# Colunas que atualizar() aceita alterar. Uma allowlist explícita evita que
# um payload malicioso injete nomes de coluna arbitrários na query (SQL
# Injection [Injeção de SQL] por nome de coluna, não só por valor).
COLUNAS_ATUALIZAVEIS = {
    "titulo", "slug", "resumo", "status", "categoria_id",
    "conteudo_md", "conteudo_html", "tempo_leitura",
    "imagem_url", "imagem_autor", "imagem_link",
    "imagem_fonte", "imagem_query", "imagem_alt",
    "meta_title", "meta_description",
}


def _calcular_tempo_leitura(texto_markdown: str) -> int:
    palavras = len(texto_markdown.split())
    return max(1, round(palavras / 200))


class ArtigoRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_categoria_id(self, nome_categoria: str) -> int | None:
        """Resolve o nome/slug de uma categoria para seu ID na tabela `categorias`.

        ATENCAO: assume colunas `nome` e `slug` em `categorias` -- confirme
        com \\d categorias no banco real e ajuste se os nomes forem outros.
        """
        slug = nome_categoria.lower().strip().replace(" ", "-")
        resultado = self.db.execute(
            text("SELECT id FROM categorias WHERE nome ILIKE :nome OR slug = :slug LIMIT 1"),
            {"nome": nome_categoria, "slug": slug},
        ).fetchone()
        return resultado[0] if resultado else None

    def buscar_categoria_nome(self, categoria_id: int) -> str | None:
        """Busca o nome de uma categoria pelo ID -- usado para montar o
        front matter do Markdown publicado no GitHub e para normalizar
        a saída da API (o painel espera `categoria` como texto)."""
        resultado = self.db.execute(
            text("SELECT nome FROM categorias WHERE id = :id"),
            {"id": categoria_id},
        ).fetchone()
        return resultado[0] if resultado else None

    def criar(
        self,
        slug: str,
        titulo: str,
        categoria_id: int,
        resumo: str,
        conteudo_markdown: str,
        status: str = "rascunho",
        imagem_url: str | None = None,
        imagem_autor: str | None = None,
        imagem_link: str | None = None,
        meta_title: str | None = None,
        meta_description: str | None = None,
        imagem_fonte: str | None = None,
        imagem_query: str | None = None,
        imagem_alt: str | None = None,
    ) -> int:
        """Salva um novo artigo. Retorna o ID gerado."""
        conteudo_html = markdown.markdown(conteudo_markdown)
        tempo_leitura = _calcular_tempo_leitura(conteudo_markdown)

        resultado = self.db.execute(
            text("""
                INSERT INTO artigos (
                    titulo, slug, resumo, conteudo_md, conteudo_html,
                    categoria_id, autor_id, status, tempo_leitura,
                    imagem_url, imagem_autor, imagem_link,
                    imagem_fonte, imagem_query, imagem_alt,
                    meta_title, meta_description,
                    data_publicacao
                ) VALUES (
                    :titulo, :slug, :resumo, :conteudo_md, :conteudo_html,
                    :categoria_id, :autor_id, :status, :tempo_leitura,
                    :imagem_url, :imagem_autor, :imagem_link,
                    :imagem_fonte, :imagem_query, :imagem_alt,
                    :meta_title, :meta_description,
                    NOW()
                )
                RETURNING id
            """),
            {
                "titulo": titulo,
                "slug": slug,
                "resumo": resumo,
                "conteudo_md": conteudo_markdown,
                "conteudo_html": conteudo_html,
                "categoria_id": categoria_id,
                "autor_id": AUTOR_ID_AGENTE,
                "status": status,
                "tempo_leitura": tempo_leitura,
                "imagem_url": imagem_url,
                "imagem_autor": imagem_autor,
                "imagem_link": imagem_link,
                "imagem_fonte": imagem_fonte,
                "imagem_query": imagem_query,
                "imagem_alt": imagem_alt,
                "meta_title": meta_title,
                "meta_description": meta_description,
            },
        )
        self.db.commit()
        return resultado.fetchone()[0]

    def atualizar(self, artigo_id: int, dados: dict) -> None:
        """Atualiza campos de um artigo existente.

        `dados` é um dict {coluna: valor}. Só colunas em
        COLUNAS_ATUALIZAVEIS são aceitas -- qualquer outra chave é ignorada
        silenciosamente por segurança (evita SQL Injection por nome de
        coluna vindo de um payload externo).

        Se `conteudo_md` estiver presente, `conteudo_html` e
        `tempo_leitura` são recalculados automaticamente (mesma lógica de
        criar()), para não deixar o HTML publicado e o tempo de leitura
        dessincronizados do markdown editado no painel.
        """
        dados = dict(dados)
        if dados.get("conteudo_md") is not None:
            dados["conteudo_html"] = markdown.markdown(dados["conteudo_md"])
            dados["tempo_leitura"] = _calcular_tempo_leitura(dados["conteudo_md"])

        campos_validos = {k: v for k, v in dados.items() if k in COLUNAS_ATUALIZAVEIS}
        if not campos_validos:
            return

        set_clause = ", ".join(f"{campo} = :{campo}" for campo in campos_validos)
        campos_validos["id"] = artigo_id

        self.db.execute(
            text(f"UPDATE artigos SET {set_clause}, atualizado_em = NOW() WHERE id = :id"),
            campos_validos,
        )
        self.db.commit()

    def excluir(self, artigo_id: int) -> None:
        """Remove um artigo do banco."""
        self.db.execute(
            text("DELETE FROM artigos WHERE id = :id"),
            {"id": artigo_id},
        )
        self.db.commit()

    def publicar(self, artigo_id: int) -> None:
        """Muda o status de um artigo existente para 'publicado'.

        Mantido como atalho semântico -- equivalente a
        atualizar(artigo_id, {"status": "publicado"}), mas mais legível
        onde só o status importa (ex.: pipeline de geração automática).
        """
        self.db.execute(
            text("UPDATE artigos SET status = 'publicado', atualizado_em = NOW() WHERE id = :id"),
            {"id": artigo_id},
        )
        self.db.commit()

    def buscar_por_id(self, artigo_id: int):
        return self.db.execute(
            text("SELECT * FROM artigos WHERE id = :id"), {"id": artigo_id}
        ).fetchone()

    def buscar_por_slug(self, slug: str):
        return self.db.execute(
            text("SELECT * FROM artigos WHERE slug = :slug"), {"slug": slug}
        ).fetchone()

    def listar_todos(self, limite: int = 50):
        return self.db.execute(
            text("""
                SELECT a.id, a.slug, a.titulo, a.resumo, a.imagem_url,
                       c.nome AS categoria, a.status,
                       a.data_publicacao, a.criado_em AS created_at
                FROM artigos a
                LEFT JOIN categorias c ON c.id = a.categoria_id
                ORDER BY a.criado_em DESC LIMIT :limite
            """),
            {"limite": limite},
        ).fetchall()