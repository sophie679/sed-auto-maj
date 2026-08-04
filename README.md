# update-shop-e-dom-automation

Automatisation qui convertit des articles WordPress "classiques" en Elementor
sur **Shop-e-Dom**, exécutée par **GitHub Actions** toutes les 5h (6h, 11h,
16h, 21h, 2h heure de Paris) — indépendamment de ton ordinateur ou de l'app
Claude (GitHub fait tourner le cron sur ses propres serveurs, 24/7).

Reprend fidèlement les règles du skill `update-shop-e-dom` : 1 conteneur
Elementor = 1 bloc sémantique (H2/H3 + son texte), format `container`
uniquement, style "lead" sur le premier paragraphe, couleurs/typographies de
la charte du site.

---

## 1. Créer le repo GitHub

1. Va sur [github.com/new](https://github.com/new), crée un repo (public ou
   privé, peu importe — privé recommandé).
2. En local ou depuis cette machine, pousse le contenu de ce dossier :
   ```bash
   cd update-shop-e-dom-automation
   git init
   git add .
   git commit -m "Init automatisation update-shop-e-dom"
   git branch -M main
   git remote add origin https://github.com/<ton-compte>/<ton-repo>.git
   git push -u origin main
   ```

## 2. Préparer WordPress (étape obligatoire, une seule fois)

Par défaut, l'API REST de WordPress **n'expose pas** les métadonnées
Elementor (`_elementor_data`, etc.) — il faut les déclarer. Ajoute ce snippet
sur le site Shop-e-Dom (via un plugin "Code Snippets", ou dans
`wp-content/mu-plugins/expose-elementor-meta.php`) :

```php
<?php
add_action('init', function () {
    foreach (['_elementor_data', '_elementor_edit_mode', '_elementor_template_type'] as $key) {
        register_post_meta('post', $key, [
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => 'string',
            'auth_callback' => function () {
                return current_user_can('edit_posts');
            },
        ]);
    }
});
```

Ensuite, crée un **mot de passe d'application** WordPress dédié :
Profil → Mots de passe d'application → donne-lui un nom (ex. "github-actions")
→ copie le mot de passe généré (il ne sera plus jamais affiché).

## 3. Créer une clé API Anthropic (si tu veux étendre le script à des tâches
qui demandent du jugement — pas nécessaire pour cette conversion Elementor,
qui est 100% déterministe)

Va sur [console.anthropic.com](https://console.anthropic.com), crée une clé
API. Facturée à l'usage (indépendant de ton abonnement Claude).

## 4. Configurer les secrets GitHub

Dans le repo GitHub → **Settings → Secrets and variables → Actions** → *New
repository secret*, ajoute :

| Nom | Valeur |
|---|---|
| `WP_SHOP_URL` | `https://www.shop-e-dom.com` (sans slash final) |
| `WP_SHOP_USER` | ton identifiant WordPress |
| `WP_SHOP_APP_PASSWORD` | le mot de passe d'application créé à l'étape 2 |

## 5. Renseigner les articles à traiter

Édite `config/articles.json` :

```json
{ "article_ids": [123, 456, 789] }
```

Commit + push. À chaque exécution planifiée, le script traite tous les IDs
de la liste (déjà en Elementor ou non — attention, le script écrase le
`_elementor_data` existant, donc retire un ID de la liste une fois converti
si tu ne veux pas qu'il soit retraité en boucle).

## 6. Tester manuellement

Dans GitHub → onglet **Actions** → workflow "Update Shop-e-Dom articles
(Elementor)" → **Run workflow**. Vérifie les logs, puis va voir le rendu de
l'article sur le site.

## Comment ça marche

- `.github/workflows/schedule.yml` : déclenche le job aux 5 créneaux
  horaires (converties en UTC — voir le commentaire dans le fichier pour la
  nuance heure d'été/hiver).
- `src/update_article.py` :
  1. récupère le contenu brut de chaque article via l'API REST WP
     (`wp-json/wp/v2/posts/{id}?context=edit`),
  2. le découpe en blocs sémantiques (BeautifulSoup, un bloc par H2/H3),
  3. génère le JSON `_elementor_data` (containers + heading/text-editor,
     styles de charte),
  4. republie l'article via `POST wp-json/wp/v2/posts/{id}` avec les
     métadonnées Elementor (mise à jour en place, jamais de création).

## Limites connues

- Le découpage suppose une structure simple (paragraphes, listes, tableaux,
  H2/H3). Des blocs très complexes (colonnes imbriquées, shortcodes) peuvent
  nécessiter un ajustement manuel du script.
- Le style de charte (couleurs, polices) est codé en dur dans le script
  d'après la charte observée sur l'article de référence du skill d'origine —
  si la charte du site change, il faudra mettre à jour
  `LEAD_TYPOGRAPHY` et les `__globals__` dans `src/update_article.py`.
