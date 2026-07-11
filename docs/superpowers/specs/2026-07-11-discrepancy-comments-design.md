# Spécification — Commentaires par ligne d'écart (justification + traçabilité)

**Date :** 2026-07-11
**Statut :** validé (brainstorming), prêt pour plan d'implémentation

---

## 1. Contexte

L'outil compare l'inventaire théorique (Proconcept) et réel (espace de stockage)
et affiche les écarts par `code + N° de lot`. Aujourd'hui l'utilisateur ne peut
pas annoter un écart pour le justifier, et rien n'est conservé d'un inventaire
mensuel à l'autre — il faut refaire les recherches chaque mois.

## 2. Objectif

Permettre, sur **chaque ligne d'écart**, de saisir un **commentaire** de
justification, qui :
1. apparaît dans le **rapport Excel exporté** ;
2. est **mémorisé par `code + lot`** et **partagé** par toute l'équipe ;
3. **revient automatiquement** le mois suivant si le même lot est encore en
   écart, préfixé « previous comment », pour la traçabilité (« ce qui a bougé
   ou pas ») sans refaire les recherches.

## 3. Périmètre

**Inclus :**
- Onglet « Écarts » affiché **par défaut** (au lieu de « OK »).
- Zone de commentaire éditable par ligne d'écart, enregistrement automatique.
- Persistance partagée (`comments.json` dans le dossier partagé des templates).
- Report « previous comment » daté (cumul).
- Colonne « Commentaire » dans la feuille Écarts du rapport Excel.

**Hors périmètre :**
- Commentaires sur les lignes « OK ».
- Vue/section des écarts « résolus » (lots commentés qui ne sont plus en écart) :
  l'historique reste en mémoire s'ils reviennent, mais on ne les affiche pas.
- Édition de l'historique passé autrement qu'en modifiant le champ texte.

## 4. Modèle de données & persistance

Fichier **`comments.json`** dans **`data_dir()`** (le même dossier partagé que
`templates.json` — voir `backend/templates.py` : `O:\Logistique\ZZ Outils\Outil
Comparaison Stock` sous Windows si le lecteur est présent, repli local sinon).

Structure :
```json
{
  "comments": {
    "<code>|<lot>": { "text": "<texte complet>", "updated": "AAAA-MM-JJ" }
  }
}
```
- Clé : `f"{code}|{lot}"` (mêmes valeurs normalisées que la comparaison).
- `text` : le contenu complet du champ (historique daté cumulé), stocké **tel quel**.
- `updated` : la **date d'inventaire** (`inventory-date`) de la dernière modif.
- Écriture **atomique** (`.tmp` + `os.replace`) ; JSON illisible/corrompu →
  traité comme `{}` (pas de crash).

## 5. Logique de report « previous comment » (côté frontend)

Entrées : commentaire stocké `{text, updated}` (ou absent) renvoyé par `/compare`
pour la ligne, et la date d'inventaire courante `inv` (du sélecteur).

Soit `curMonth` = `MM/AAAA` de `inv`, `storedMonth` = `MM/AAAA` de `updated`.
Valeur de pré-remplissage du champ :

- **Pas de commentaire stocké** → champ vide.
- **Stocké, même mois** (`storedMonth == curMonth`) → champ = `text` **tel quel**
  (on ne re-emballe pas si on rouvre la même comparaison).
- **Stocké, mois différent** (`storedMonth != curMonth`) :
  - si `text` commence par `"previous comment"` →
    `text + "\n[" + curMonth + "] "`  (on ajoute seulement une ligne datée)
  - sinon →
    `"previous comment [" + storedMonth + "]: " + text + "\n[" + curMonth + "] "`

Le marqueur littéral est **`previous comment`** (en anglais, tel que demandé).

**Enregistrement (auto sur perte de focus)** : si la valeur du champ a changé
par rapport à sa valeur de pré-remplissage rendue (stockée en `data-initial`),
envoyer `POST /comments {code, lot, text, inventory_date: inv}`. Si le texte
est vide (après trim) → suppression de la clé côté serveur.

## 6. Backend

### 6.1 Nouveau module `backend/comments.py`
- `from templates import data_dir` (réutilise le dossier partagé).
- `comments_path()` → `os.path.join(data_dir(), "comments.json")`.
- `load_comments() -> dict` (corruption tolérée → `{}`).
- `save_comments(dict) -> None` (écriture atomique).
- `get_comment(code, lot) -> dict | None` → `{text, updated}` ou None.
- `set_comment(code, lot, text, updated) -> None` : upsert ; si `text.strip()`
  est vide → supprime la clé.
- `key(code, lot) -> str` = `f"{code}|{lot}"`.

### 6.2 Routes (dans `backend/main.py`)
- `import comments as comment_store`.
- **`POST /comments`** body JSON `{code, lot, text, inventory_date}` →
  `comment_store.set_comment(...)`. Retourne `{"ok": true}`. Validation :
  `code`, `lot` non vides ; `inventory_date` chaîne (défaut : "" accepté).
- **`/compare`** : après `compare_by_lot`, pour chaque écart, attacher
  `stored_comment = comment_store.get_comment(code, lot)` (ou `null`) sous la
  clé `stored_comment` de l'entrée. (Les lignes « OK » ne sont pas annotées.)
- **`/compare/download`** : construire `comments_map = {key: text}` pour les
  écarts, passé à `build_excel`.

### 6.3 `build_excel`
- Signature : `build_excel(result, df_proconcept, df_rk, comments_map=None)`.
- **Feuille Écarts uniquement** : en-têtes = `headers_base + ["Commentaire"]`.
  Pour chaque écart, ajouter la cellule commentaire = `comments_map.get(f"{code}|{lot}", "")`.
- La colonne Commentaire a `wrap_text=True` (historique daté lisible) et une
  largeur plus large (≈ 50).
- La feuille **OK** reste inchangée (pas de colonne Commentaire).

## 7. Frontend

### 7.1 Onglet par défaut
- `frontend/index.html` : réordonner les onglets pour mettre **« Écarts »**
  en premier et actif (`class="tab active"`), « OK » ensuite. Réordonner les
  panneaux en conséquence (`panel-discrepancies` avant `panel-ok`), panneau
  Écarts actif par défaut.
- `frontend/app.js` `renderResults` : forcer l'onglet actif sur
  `discrepancies` à chaque affichage des résultats.

### 7.2 Colonne commentaire
- `renderDiscrepancyTable` : ajouter une colonne d'en-tête **« Commentaire »**
  et, par ligne, un `<textarea class="comment-box" data-code data-lot
  data-initial rows="2">` pré-rempli via la logique §5 (calculée en JS à partir
  de `i.stored_comment` et de la date d'inventaire courante).
- **Enregistrement** par délégation d'événement `focusout` sur le panneau : si
  `textarea.value !== textarea.dataset.initial` → `POST /comments`, puis mettre
  à jour `data-initial`.
- **Avant export** : au clic « Télécharger », si une `.comment-box` est
  focalisée et modifiée, **attendre** (`await`) son enregistrement
  (`saveComment`) AVANT de lancer le téléchargement — sinon l'export pourrait
  lire un `comments.json` pas encore à jour (course entre le `POST /comments`
  et le `POST /compare/download`). L'enregistrement est une fonction qui
  renvoie une promesse, réutilisée par le `focusout` et par le clic export.

### 7.3 Style
- `.comment-box` : cohérent thème sombre (fond translucide, texte blanc,
  `resize: vertical`, largeur 100 % de la colonne). Colonne Écarts un peu plus
  large pour accueillir la zone.

## 8. Cas limites
- Lot sans commentaire → champ vide, rien d'enregistré tant qu'on n'écrit rien.
- Champ vidé → suppression du commentaire stocké.
- `comments.json` corrompu → traité comme vide (pas de crash).
- Dossier partagé inaccessible en écriture → l'enregistrement échoue proprement
  (erreur remontée) ; la lecture/compare continue de fonctionner.
- Deux personnes commentant le même lot au même instant → dernier écrit gagne
  (acceptable, édition occasionnelle). Pas de verrou.
- Date d'inventaire non renseignée → marqueur sans mois propre : on utilise la
  valeur du sélecteur (défaut = aujourd'hui, déjà pré-rempli par l'UI).

## 9. Tests
- **Unitaires backend** (pytest) : `comments.py` save/load round-trip ;
  corruption tolérée ; `set_comment` upsert + suppression si vide ; `get_comment`.
- **API** : `POST /comments` (upsert + suppression) ; `/compare` renvoie
  `stored_comment` pour un écart commenté ; `/compare/download` produit un
  `.xlsx` valide avec la colonne « Commentaire » remplie.
- **Logique JS `buildCommentPrefill`** : extraite en fonction testable ;
  cas pas-de-stocké / même-mois / 1ᵉʳ-report / report-suivant.
- **Non-régression** : les 45 tests existants passent.
- **Vérif navigateur (Playwright)** : onglet Écarts par défaut ; saisir un
  commentaire ; export Excel contient le commentaire ; 2ᵉ comparaison (mois
  suivant simulé) → « previous comment » pré-rempli.

## 10. Packaging
- Ajouter `"comments"` aux `hiddenimports` de `windows/trb_stock.spec`.
- `comments.json` vit dans le dossier partagé, jamais dans le bundle.
