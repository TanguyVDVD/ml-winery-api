# ml_api : détection d'anomalies des Peltier

Petit serveur qui dit si une mesure d'un Peltier est **inhabituelle**. Le Pi l'appelle une fois par minute ; le modèle donne un avis, écrit dans les logs du Pi. **Il ne commande jamais les relais** : la sécurité reste assurée par les règles de `api/peltier/cellar.py`.

```text
Pi : mqtt-consumer ──HTTPS + jeton──> Caddy ──> ml-api /predict ──> { is_anomaly, anomaly_score }
```

## Le modèle

**Isolation Forest** (scikit-learn), un modèle **non supervisé** : on ne lui montre aucune panne, il apprend ce qui est habituel dans les données.

- **Entraînement** : il construit 100 arbres qui découpent les mesures au hasard (une colonne, une valeur de coupure), jusqu'à isoler chaque point.
- **Prédiction** : une mesure habituelle est entourée d'autres, il faut beaucoup de coupes pour l'isoler. Une mesure anormale est loin de tout, elle est isolée en peu de coupes. Peu de coupes → `anomaly_score` négatif → `is_anomaly: true`.

Colonnes utilisées (`app/features.py`) : `peltier_temp` (ventirad), `ambient_temp` (cave), `fan_rpm` (ventilateur chaud). Seules les mesures **Peltier en marche** et **complètes** servent à l'entraînement.

⚠️ Le modèle croit que tout ce qu'il a vu est normal. Des pannes présentes dans les données d'entraînement (tachymètre à 0, bruit à 1 500 tr/min) ne seront pas signalées.

## Fichiers

| Fichier | Rôle |
|---|---|
| `app/main.py` | Route `POST /predict`, charge `models/isolation_forest.joblib` |
| `app/schemas.py` | Données acceptées, avec des bornes (valeur absurde → 422) |
| `app/features.py` | La liste des colonnes, partagée par l'entraînement et le serveur |
| `app/security.py` | Vérifie le jeton `Authorization: Bearer ...` |
| `train.py` | Entraîne le modèle à partir d'un export CSV |
| `tests/test_predict.py` | Tests du serveur et du filtrage du CSV |
| `Dockerfile`, `docker-compose.yaml`, `Caddyfile` | Déploiement : ml-api derrière Caddy (HTTPS) |
| `data/`, `models/` | CSV et modèle, **hors Git** et hors de l'image (volumes Docker) |

## Configuration (`.env`)

Copier `.env.example` en `.env` :

| Variable | Valeur |
|---|---|
| `API_TOKEN` | Longue valeur aléatoire : `python -c "import secrets; print(secrets.token_urlsafe(32))"`. **La même** que `ML_API_TOKEN` dans le `.env` du Pi. |
| `SITE_ADDRESS` | Nom de domaine du serveur (ex. `ml.example.org`), qui pointe vers son IP publique. |

`.env` n'est jamais commité.

## 1. Exporter les mesures (sur le Pi)

Depuis le dossier du projet :

```bash
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "COPY (
    SELECT peltier_id, peltier_temp, ambient_temp, fan_rpm, is_on, created_at
    FROM peltier ORDER BY created_at
) TO STDOUT WITH CSV HEADER"' > peltier.csv
```

Puis copier `peltier.csv` dans `ml_api/data/` sur le serveur (`scp`).

## 2. Déployer et entraîner (sur le serveur)

Prérequis : Docker, le nom de domaine pointé vers le serveur, ports **80** et **443** ouverts et libres (Caddy en a besoin pour obtenir le certificat HTTPS).

```bash
cd ml_api
mkdir -p models data          # avant tout : sinon Docker les crée en root et train.py ne peut pas écrire
cp .env.example .env          # remplir API_TOKEN et SITE_ADDRESS
# copier peltier.csv dans data/
docker compose build
docker compose run --rm ml-api python train.py data/peltier.csv "2026-11-03 17:39:14+00"
docker compose up -d
```

La date est **obligatoire** : les mesures plus anciennes sont ignorées. Mets le moment à partir duquel le matériel fonctionne correctement.

`train.py` affiche le nombre de lignes utilisées et la part qu'il juge lui-même anormale. Au-delà de 5 à 10 %, les données sont probablement sales. Il avertit sous 1 000 lignes et refuse sous 100.

L'entraînement tourne dans la même image que le serveur : la version de scikit-learn (fixée dans `requirements.txt`) est forcément la même des deux côtés. Un modèle créé avec une autre version peut ne pas se charger ou donner des résultats faux.

## 3. Réentraîner

Nouvel export dans `data/`, puis :

```bash
docker compose run --rm ml-api python train.py data/peltier.csv "<date>"
docker compose restart ml-api
```

Quand : après un changement matériel, quand la saison change, ou si le Pi signale souvent des anomalies alors que tout va bien.

## 4. Brancher le Pi

Dans le `.env` du Pi :

```env
ML_API_URL=https://ml.example.org/predict
ML_API_TOKEN=<même valeur que API_TOKEN ici>
```

Puis `docker compose up -d mqtt-consumer`. Sans ces variables, le contrôle est simplement désactivé. Le client (`api/app/ml_client.py`) refuse une adresse en `http://`, attend 5 s au plus, et ne gêne jamais la régulation si le serveur est absent.

## API

`POST /predict`, en-tête `Authorization: Bearer <API_TOKEN>` :

```bash
curl -X POST https://ml.example.org/predict -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"peltier_id":"peltier_1","is_on":true,"peltier_temp":45,"ambient_temp":15.5,"fan_rpm":0}'
```

| Cas | Réponse |
|---|---|
| Mesure complète, Peltier en marche | `{"peltier_id": "...", "is_anomaly": true/false, "anomaly_score": 0.08}` (négatif = inhabituel) |
| Peltier arrêté, ou `peltier_temp` / `fan_rpm` absent | `is_anomaly: null` : pas d'avis |
| Pas de jeton / mauvais jeton | `403` / `401` |
| Valeur hors bornes | `422` |

La documentation interactive (`/docs`) est désactivée : le serveur est public.

## Développement (sans Docker)

```bash
cd ml_api
python -m venv .venv && .venv/Scripts/activate      # Linux : source .venv/bin/activate
pip install -r requirements.txt httpx
python train.py data/peltier.csv "2026-11-03 17:39:14+00"
API_TOKEN=dev uvicorn app.main:app --reload         # PowerShell : $env:API_TOKEN="dev"; uvicorn ...
python -m tests.test_predict                         # ou pytest
```

## État actuel

Premier modèle entraîné le 2026-11-04 sur **235 lignes** seulement, avec le bruit des tachymètres : il juge 21 % de ses propres données anormales, et ne signale pas un ventilateur à 0 tr/min à température normale. À réentraîner dès qu'il y aura 1 à 2 semaines de mesures propres. Détails : `docs/ml-anomaly-detection.md`.
