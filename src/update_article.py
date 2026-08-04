#!/usr/bin/env python3
"""
update_article.py

Convertit automatiquement des articles WordPress "classiques" en Elementor
sur Shop-e-Dom, en respectant la charte graphique du site (règles issues
du skill `update-shop-e-dom`) :

  - 1 conteneur (elType="container") = 1 bloc sémantique (intro, ou H2/H3 + son texte)
  - H2 top-level : {"title": "..."}
  - H3            : {"title": "...", "header_size": "h3",
                      "__globals__": {"typography_typography": "globals/typography?id=accent"}}
  - Texte         : {"editor": "<p>...</p>", "__globals__": {"text_color": "globals/colors?id=primary"}}
  - Le tout premier paragraphe (bloc d'intro) reçoit un style "lead" (Titillium Web, 24px, etc.)
  - meta._elementor_edit_mode = "builder", meta._elementor_template_type = "wp-post"
  - Toujours wp_update_post (jamais de création) : on remplace l'article en place.

Ce script est 100% déterministe (parsing HTML avec BeautifulSoup) : il ne fait PAS
appel à l'API Claude, car le découpage par titres H2/H3 ne nécessite aucun
jugement — uniquement du parsing. Cela évite tout coût d'API et toute
variabilité pour cette tâche précise.

Variables d'environnement requises (à définir en secrets GitHub) :
  WP_SHOP_URL           ex: https://www.shop-e-dom.com
  WP_SHOP_USER          identifiant WordPress (utilisateur avec droits d'édition)
  WP_SHOP_APP_PASSWORD  mot de passe d'application WordPress (Réglages > Profil > Mots de passe d'application)

Configuration des articles à traiter : config/articles.json
  { "article_ids": [123, 456, ...] }
"""

import json
import os
import random
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString

HEX_CHARS = "0123456789abcdef"


def gen_id(existing: set) -> str:
    """Génère un ID Elementor unique de 7 caractères hexadécimaux."""
    while True:
        new_id = "".join(random.choices(HEX_CHARS, k=7))
        if new_id not in existing:
            existing.add(new_id)
            return new_id


# ---------------------------------------------------------------------------
# 1. Découpage sémantique du HTML en blocs (intro, puis un par H2/H3)
# ---------------------------------------------------------------------------

def split_into_blocks(raw_html: str):
    """
    Découpe le contenu brut en blocs :
      - le premier bloc (heading=None) = intro
      - chaque bloc suivant démarre à un H2 ou H3 rencontré
    Retourne une liste de dicts : {"heading": {"text":.., "level":2|3} | None, "html": "<p>...</p>..."}
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    blocks = []
    current = {"heading": None, "nodes": []}

    for node in list(soup.contents):
        if isinstance(node, NavigableString) and not node.strip():
            continue
        if getattr(node, "name", None) in ("h2", "h3"):
            if current["heading"] is not None or current["nodes"]:
                blocks.append(current)
            current = {
                "heading": {"text": node.get_text(strip=True), "level": int(node.name[1])},
                "nodes": [],
            }
        else:
            current["nodes"].append(node)

    if current["heading"] is not None or current["nodes"]:
        blocks.append(current)

    result = []
    for b in blocks:
        html = "".join(str(n) for n in b["nodes"]).strip()
        if not html and b["heading"] is None:
            continue
        result.append({"heading": b["heading"], "html": html})
    return result


# ---------------------------------------------------------------------------
# 2. Construction du JSON _elementor_data à partir des blocs
# ---------------------------------------------------------------------------

LEAD_TYPOGRAPHY = {
    "typography_typography": "custom",
    "typography_font_family": "Titillium Web",
    "typography_font_size": {"unit": "px", "size": 24, "sizes": []},
    "typography_font_size_tablet": {"unit": "px", "size": 20, "sizes": []},
    "typography_font_size_mobile": {"unit": "px", "size": 16, "sizes": []},
    "typography_font_weight": "400",
    "typography_line_height": {"unit": "px", "size": 30, "sizes": []},
    "typography_line_height_tablet": {"unit": "em", "size": 1.2, "sizes": []},
    "typography_line_height_mobile": {"unit": "em", "size": 1.2, "sizes": []},
}


def make_text_widget(html: str, ids: set, lead: bool = False) -> dict:
    settings = {"editor": html, "__globals__": {"text_color": "globals/colors?id=primary"}}
    if lead:
        settings.update(LEAD_TYPOGRAPHY)
    return {
        "id": gen_id(ids),
        "elType": "widget",
        "widgetType": "text-editor",
        "settings": settings,
        "elements": [],
    }


def make_heading_widget(heading: dict, ids: set) -> dict:
    if heading["level"] == 2:
        settings = {"title": heading["text"]}
    else:
        settings = {
            "title": heading["text"],
            "header_size": "h3",
            "__globals__": {"typography_typography": "globals/typography?id=accent"},
        }
    return {
        "id": gen_id(ids),
        "elType": "widget",
        "widgetType": "heading",
        "settings": settings,
        "elements": [],
    }


def make_container(children: list, ids: set) -> dict:
    return {
        "id": gen_id(ids),
        "elType": "container",
        "settings": {"flex_direction": "column"},
        "elements": children,
    }


def build_elementor_data(blocks: list) -> list:
    ids = set()
    containers = []
    first_paragraph_done = False

    for block in blocks:
        children = []
        if block["heading"] is not None:
            children.append(make_heading_widget(block["heading"], ids))
        if block["html"]:
            is_lead = not first_paragraph_done and block["heading"] is None
            children.append(make_text_widget(block["html"], ids, lead=is_lead))
            first_paragraph_done = True
        if children:
            containers.append(make_container(children, ids))

    return containers


# ---------------------------------------------------------------------------
# 3. Appels WordPress REST API
# ---------------------------------------------------------------------------

def wp_session():
    user = os.environ["WP_SHOP_USER"]
    app_password = os.environ["WP_SHOP_APP_PASSWORD"]
    s = requests.Session()
    s.auth = (user, app_password)
    return s


def fetch_raw_content(base_url: str, post_id: int, session: requests.Session) -> str:
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
    r = session.get(url, params={"context": "edit"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["content"]["raw"]


def update_post_elementor(base_url: str, post_id: int, elementor_data: list, session: requests.Session):
    payload_json = json.dumps(elementor_data, ensure_ascii=False)

    # Garde-fou : vérifie qu'il n'y a pas d'échappement `\/` parasite et que le JSON est valide
    if "\\/" in payload_json:
        raise ValueError("Échappement '\\/' détecté dans le JSON généré — corriger avant envoi.")
    json.loads(payload_json)  # lève une exception si invalide

    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
    body = {
        "meta": {
            "_elementor_data": payload_json,
            "_elementor_edit_mode": "builder",
            "_elementor_template_type": "wp-post",
        }
    }
    r = session.post(url, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# 4. Main
# ---------------------------------------------------------------------------

def main():
    base_url = os.environ["WP_SHOP_URL"]
    session = wp_session()

    config_path = Path(__file__).resolve().parent.parent / "config" / "articles.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    article_ids = config.get("article_ids", [])

    if not article_ids:
        print("Aucun ID d'article configuré dans config/articles.json — rien à faire.")
        return

    exit_code = 0
    for post_id in article_ids:
        try:
            print(f"--- Article {post_id} ---")
            raw_html = fetch_raw_content(base_url, post_id, session)
            blocks = split_into_blocks(raw_html)
            elementor_data = build_elementor_data(blocks)
            update_post_elementor(base_url, post_id, elementor_data, session)
            print(f"Article {post_id} converti en Elementor ({len(elementor_data)} conteneurs).")
        except Exception as exc:  # noqa: BLE001 - on veut logguer et continuer les autres articles
            print(f"ERREUR sur l'article {post_id} : {exc}", file=sys.stderr)
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
