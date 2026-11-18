import unittest

from integration.content import build_payload, slugify


class ContentAdapterTests(unittest.TestCase):
    def test_slug_is_ascii_lowercase_and_hyphenated(self):
        self.assertEqual(slugify("Bolo de Chocolate!"), "bolo-de-chocolate")

    def test_recipe_maps_to_documented_api_contract(self):
        generated = {
            "title": "Bolo simples de chocolate",
            "excerpt": "Bolo macio de chocolate com preparo direto e ingredientes comuns.",
            "prepTimeMin": 15,
            "cookTimeMin": 35,
            "servings": 8,
            "difficulty": "Fácil",
            "ingredients": [{"name": "Massa", "items": [
                {"name": "farinha de trigo", "quantity": "2", "unit": "xícara"}
            ]}],
            "steps": [{"instruction": f"Etapa {i}: misture os ingredientes até obter uma massa uniforme."} for i in range(4)],
            "coverImageAlt": "Bolo de chocolate em um prato claro",
        }
        cover = {
            "mode": "stock", "provider": "pexels", "sourceImageUrl": "https://images.example/a.jpg",
            "sourcePageUrl": "https://pexels.example/a", "author": "Autora", "license": "Licença",
            "attributionText": "Foto: Autora",
        }
        payload, schema, slug = build_payload(
            "receita", generated, topic="Bolo de chocolate", cover=cover,
            model="mistral", run_id="run-1", subcategoria="bolos-simples",
        )
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["subcategorySlug"], "bolos-simples")
        self.assertEqual(payload["slug"], slug)
        self.assertEqual(schema["@type"], "Recipe")
        self.assertNotIn("schema_org", payload)
        self.assertNotIn("meta_description", payload)


if __name__ == "__main__":
    unittest.main()
