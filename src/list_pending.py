#!/usr/bin/env python3
"""
list_pending.py

Parcourt tous les articles publiés de Shop-e-Dom et affiche dans les logs
la liste de ceux qui ne sont PAS encore construits avec Elementor — prêts à
copier-coller dans config/articles.json.

Ne modifie rien sur le site (lecture seule). Utilise les mêmes secrets que
update_article.py (WP_SHOP_URL, WP_SHOP_USER, WP_SHOP_APP_PASSWORD).
"""

import os
import sys

import requests

from update_article import is_already_elementor, wp_session

PER_PAGE = 50


def iter_published_posts(base_url: str, session: requests.Session):
    page = 1
    while True:
        url = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts"
        r = session.get(
            url,
            params={
                "status": "publish",
                "context": "edit",
                "per_page": PER_PAGE,
                "page": page,
                "_fields": "id,title,content,meta",
            },
            timeout=30,
        )
        if r.status_code == 400 and page > 1:
            # WP renvoie 400 "rest_post_invalid_page_number" une fois qu'on dépasse le nombre de pages
            break
        r.raise_for_status()
        posts = r.json()
        if not posts:
            break
        for post in posts:
            yield post

        total_pages = int(r.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            break
        page += 1


def main():
    base_url = os.environ["WP_SHOP_URL"]
    session = wp_session()

    pending = []
    done = []

    for post in iter_published_posts(base_url, session):
        title = post.get("title", {}).get("rendered", "(sans titre)")
        entry = f"{post['id']} — {title}"
        if is_already_elementor(post):
            done.append(entry)
        else:
            pending.append(entry)

    print(f"Total articles publiés analysés : {len(pending) + len(done)}")
    print(f"Déjà en Elementor : {len(done)}")
    print(f"Pas encore en Elementor : {len(pending)}")
    print()
    print("=== IDs pas encore en Elementor (à copier dans config/articles.json) ===")
    ids_only = [e.split(" — ")[0] for e in pending]
    print("[" + ", ".join(ids_only) + "]")
    print()
    print("=== Détail (ID — Titre) ===")
    for entry in pending:
        print(entry)

    if not pending:
        print("Aucun article restant à convertir.")


if __name__ == "__main__":
    main()
