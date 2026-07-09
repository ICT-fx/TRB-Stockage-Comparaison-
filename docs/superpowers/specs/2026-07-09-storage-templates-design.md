# Spécification — Templates de colonnes pour l'espace de stockage

**Date :** 2026-07-09
**Statut :** validé (brainstorming), prêt pour plan d'implémentation
**Auteur :** Fantin + Claude

---

## 1. Contexte

L'outil compare un inventaire théorique (Proconcept) et un inventaire réel
(fichier « espace de stockage », historiquement RK Logistik). Aujourd'hui, la
mise en page des colonnes du fichier de stockage est **codée en dur** dans le
backend (`parse_rk_lot`). Chaque nouveau partenaire logistique avec un ordre de
colonnes différent obligerait à recompiler l'`.exe`.

L'application est distribuée en exécutable Windows autonome (PyInstaller
*onefile*) — voir `windows/launcher.py`, `windows/trb_stock.spec`,
`.github/workflows/build-windows.yml`.

## 2. Objectif

Permettre à l'utilisateur de **créer, nommer, modifier et supprimer des
templates de colonnes** pour le fichier d'espace de stockage, **directement dans
l'application**, sans recompiler, et que ces templates soient **mémorisés d'un
lancement à l'autre**.

Un template décrit, pour chacun des 5 champs métier, **dans quelle colonne** du
fichier il se trouve :

- **SKU** (requis)
- **N° de lot** (requis)
- **Date d'expiration** (optionnel)
- **Description du produit** (optionnel)
- **Quantité** (requis)

Les colonnes en trop dans le fichier sont **ignorées**.

## 3. Périmètre (scope)

**Inclus :**
- Templates **uniquement pour le fichier d'espace de stockage** (le « réel »).
  Le fichier Proconcept (« théorique ») garde son format fixe actuel.
- Création **guidée par un fichier exemple** : l'app lit les colonnes du fichier
  déposé et l'utilisateur associe chaque champ à une colonne via des menus.
- Gestion complète : créer / renommer / modifier / supprimer.
- Persistance côté application (voir §4).

**Hors périmètre (non-goals) :**
- Templates pour le fichier Proconcept.
- Mise à jour automatique de l'`.exe` lui-même (auto-update du binaire) — projet
  séparé.
- Modification de la logique de comparaison (toujours par SKU + N° de lot).

## 4. Modèle de données & stockage

### 4.1 Schéma d'un template

Indices de colonnes en **base 0**. `header_row` en **base 1** (numéro de ligne
Excel contenant les en-têtes ; les données commencent à la ligne suivante).

```json
{
  "id": "a1b2c3d4",
  "name": "Stock Partenaire X",
  "header_row": 2,
  "columns": {
    "sku": 0,
    "lot": 1,
    "qty": 4,
    "date": 2,
    "description": 3
  }
}
```

- `sku`, `lot`, `qty` : **requis** (entier ≥ 0).
- `date`, `description` : **optionnels** (`null` si le fichier ne les contient
  pas).
- `name` : chaîne non vide.

### 4.2 Emplacement de stockage

Fichier `templates.json` dans un **dossier de données persistant** :

- **Windows :** `%APPDATA%\TRB-Comparaison-Stock\templates.json`
- **Autres (dev macOS/Linux) :** `~/.trb-comparaison-stock/templates.json`

Le dossier est créé automatiquement au premier enregistrement. **Ne jamais**
utiliser `sys._MEIPASS` (dossier temporaire de l'`.exe`, supprimé à la
fermeture).

Format du fichier :

```json
{ "templates": [ { …template… }, … ] }
```

### 4.3 Template intégré par défaut

« **Basic template stock** » reproduit le format RK actuel :

```json
{
  "id": "basic-stock",
  "name": "Basic template stock",
  "builtin": true,
  "header_row": 2,
  "columns": { "sku": 0, "lot": 1, "date": 2, "description": 3, "qty": 4 }
}
```

Il est **codé en dur dans le backend** (pas dans le JSON), donc **toujours
présent et non supprimable/non modifiable**. Le comportement actuel est ainsi
préservé à l'identique.

`GET /templates` renvoie l'intégré **fusionné** avec les templates utilisateur
du JSON.

## 5. Backend

### 5.1 Découpage en modules

- **`backend/templates.py`** *(nouveau)* :
  - modèle / validation de template ;
  - template intégré `basic-stock` ;
  - `data_dir()`, `templates_path()` ;
  - `load_templates()` / `save_templates()` (écriture atomique) ;
  - `get_template(id)` (intégré + JSON) ;
  - `detect_columns(raw_bytes, header_row=None)` : auto-détection de la ligne
    d'en-tête + description des colonnes.
- **`backend/main.py`** : parsers/comparaison/Excel existants + parser
  générique + nouvelles routes.

`backend/templates.py` étant importé par `main.py`, PyInstaller le suit
automatiquement ; on l'ajoute néanmoins aux `hiddenimports` du `.spec` par
sécurité.

### 5.2 Parser générique

`parse_storage_with_template(raw_bytes, template) -> (list[dict], DataFrame)` :

- `df = pd.read_excel(BytesIO(raw_bytes), header=template.header_row - 1)`
- Si le fichier a moins de colonnes que l'indice max requis → `ValueError`
  clair (« Le fichier n'a que N colonnes, le template en attend au moins M »).
- Pour chaque ligne : `code = df.iloc[:, columns.sku]`, `lot = columns.lot`,
  `qty = columns.qty`, `date`/`description` si mappés (sinon `""`).
- **Réutilise** `_is_numeric_code`, `_clean_code`, `_clean_lot`,
  `_parse_rk_date` pour un comportement identique à l'existant.
- Mêmes règles de filtrage que `parse_rk_lot` (ligne ignorée si code non
  numérique ou lot vide).
- Renvoie la même structure `{code, lot, date, qty, description}` → la
  comparaison `compare_by_lot` **ne change pas**.

Le template `basic-stock` passé à ce parser **reproduit exactement**
`parse_rk_lot` (garanti par un test de non-régression). `parse_rk_lot` peut donc
devenir un simple appel au parser générique avec le template intégré.

### 5.3 Routes API

| Route | Rôle |
|---|---|
| `GET /templates` | Liste : intégré (`builtin: true`) + templates utilisateur. |
| `POST /templates/preview` | Reçoit un fichier exemple (+ `header_row` optionnel). Auto-détecte la ligne d'en-tête (gère la 1ʳᵉ ligne vide RK). Renvoie `{ header_row, columns: [ {index, name, samples:[…]} ] }`. |
| `POST /templates` | Crée `{name, header_row, columns}`. Valide, génère `id`, enregistre. Renvoie le template créé. |
| `PUT /templates/{id}` | Modifie/renomme un template utilisateur. Intégré protégé → 400. |
| `DELETE /templates/{id}` | Supprime un template utilisateur. Intégré protégé → 400. |

`POST /compare` et `POST /compare/download` reçoivent en plus
`storage_template_id: str = Form("basic-stock")`. Le côté stockage utilise
`parse_storage_with_template` avec le template résolu ; le côté Proconcept est
inchangé (`parse_proconcept_lot`). Id introuvable → 400 clair.

Les anciens champs de formulaire inutilisés `layout_theorique` / `layout_reel`
sont retirés : `storage_template_id` les remplace côté stockage, et le côté
Proconcept n'a pas de sélecteur de format.

### 5.4 Détection de colonnes (`detect_columns`)

- Lecture `header=None`.
- **Auto-détection de l'en-tête** : première ligne **non entièrement vide** →
  `header_row` (base 1). Gère le cas RK (ligne 0 vide, en-tête ligne 2).
- Re-lecture avec ce `header_row` ; pour chaque colonne : `index`, `name`
  (texte d'en-tête, ou `Colonne N` si vide), `samples` = 1 à 3 premières valeurs
  non nulles.
- `header_row` surchargeable par l'appelant (bouton ▲▼ côté UI).

### 5.5 Validation & robustesse

- `name` non vide ; `sku`/`lot`/`qty` présents et entiers ≥ 0 ; refus si deux
  **champs requis** pointent la même colonne.
- **Écriture atomique** : écrire dans `templates.json.tmp` puis `os.replace`.
- `templates.json` illisible/corrompu → journalisé, traité comme
  `{ "templates": [] }` (l'intégré fonctionne toujours, pas de crash).
- `%APPDATA%` non accessible en écriture → erreur claire remontée à l'UI ;
  l'intégré reste utilisable en lecture.

## 6. Frontend

### 6.1 Sélecteur de template (fichier stockage)

Le `<select id="layout-reel">` est **rempli dynamiquement** au chargement via
`GET /templates` : intégré + templates utilisateur. À côté :

- **✎ Modifier** et **🗑 Supprimer** (agissent sur le template sélectionné ;
  désactivés si l'intégré est sélectionné) ;
- bouton **＋ Nouveau template**.

### 6.2 Modale « Nouveau template »

1. **Étape 1** — déposer/choisir un **fichier exemple** → `POST /templates/preview`.
2. **Étape 2** — affichage :
   - **En-tête détecté sur la ligne : [N] ▲▼** (ajustable ; re-preview au
     changement) ;
   - 5 lignes de mapping, un menu déroulant par champ, listant les colonnes
     détectées (`nom (ex: valeur)`). Date et Description ont l'option
     **« — aucune — »** ;
   - **pré-remplissage automatique** par correspondance de nom d'en-tête,
     corrigeable ;
   - champ **Nom du template**.
3. **Enregistrer** → `POST /templates` → rafraîchit le menu, **sélectionne
   automatiquement** le nouveau template, ferme la modale.

**Modifier** rouvre la modale pré-remplie sur le mapping enregistré. Le
renommage et l'ajustement des indices/`header_row` sont toujours possibles ; en
l'absence de nouveau fichier exemple, les colonnes sont affichées de façon
générique (« Colonne N ») puisque seuls les **indices** sont mémorisés, pas les
noms. Pour retrouver noms + aperçus, l'utilisateur **redépose un fichier
exemple**. **Supprimer** demande confirmation.

### 6.3 Mémorisation du dernier choix

L'id du dernier template sélectionné est stocké dans `localStorage` pour
re-sélection par défaut à l'ouverture. Si cet id n'existe plus (template
supprimé) → retour sur l'intégré.

### 6.4 Envoi à la comparaison

`storage_template_id` = valeur du `<select>` transmis à `/compare` et
`/compare/download`.

### 6.5 Style

Vanilla JS (aucune dépendance), thème sombre TRB existant, modale en
`glass-card`, cohérent avec `app.js`/`style.css`.

## 7. Cas limites & erreurs

- Fichier exemple illisible/vide → erreur claire dans la modale.
- Template attend une colonne absente du fichier → erreur explicite (n° de
  colonnes).
- Aucune ligne valide après application du template → avertissement.
- Deux champs requis sur la même colonne → refusé à l'enregistrement.
- `templates.json` corrompu → traité comme vide.
- `%APPDATA%` non accessible → message d'erreur, intégré utilisable.
- Template mémorisé mais supprimé → retour automatique sur l'intégré.
- Date/Description non mappées → colonnes vides dans le rapport.

## 8. Tests

- **Non-régression** : parser générique + `basic-stock` == `parse_rk_lot`
  actuel (mêmes résultats sur un fichier RK de référence).
- **Unitaires backend** (pytest) : colonnes réordonnées + colonnes en trop ;
  date/description non mappées ; colonne hors limites → erreur ; store
  save/load round-trip ; JSON corrompu toléré ; intégré protégé
  (modif/suppr) ; auto-détection en-tête (1ʳᵉ ligne vide).
- **Persistance** : template enregistré relu par un **nouveau processus**
  (simule le redémarrage de l'`.exe`).
- **Bout-en-bout** : `/compare` avec template personnalisé (colonnes
  réordonnées) → résultats corrects + rapport `.xlsx`.
- **Frozen/PyInstaller** : `backend/templates.py` embarqué ; l'`.exe` lit/écrit
  dans `%APPDATA%` (vérifié en local macOS + build Windows CI).
- **Vérification manuelle UI** : fichier exemple → mapping → enregistrement →
  comparaison → persistance après redémarrage.

## 9. Impact packaging

- Ajouter `backend/templates.py` aux `hiddenimports` du `.spec`.
- Aucune donnée template embarquée dans le bundle ; tout vit dans `%APPDATA%`.
- Le workflow CI et le flux de distribution de l'`.exe` restent inchangés.
