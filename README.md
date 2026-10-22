# License Server — Déploiement Railway / Render + PostgreSQL

## Fichiers inclus
- `server.py`      — Serveur Flask avec PostgreSQL
- `dashboard.html` — Interface admin
- `requirements.txt`
- `Procfile`
- `runtime.txt`

---

## ÉTAPES RAILWAY (recommandé)

### 1. Crée un compte GitHub et push ces fichiers
```bash
git init
git add .
git commit -m "init license server"
# Crée un repo sur github.com puis :
git remote add origin https://github.com/TON_USER/license-server.git
git push -u origin main
```

### 2. Déploie sur Railway
1. Va sur https://railway.app → New Project
2. Deploy from GitHub repo → sélectionne ton repo
3. Le déploiement démarre automatiquement

### 3. Ajoute PostgreSQL
1. Dans ton projet Railway → **+ New** → **Database** → **PostgreSQL**
2. Railway crée automatiquement la variable `DATABASE_URL` dans ton service

### 4. Configure les variables d'environnement
Dans ton service web → **Variables** → ajoute :
```
ADMIN_PASSWORD  =  ton_mot_de_passe_secret
SECRET_KEY      =  une_chaine_aleatoire_longue_ex_abc123xyz789
```
(DATABASE_URL est déjà injectée automatiquement par Railway)

### 5. Récupère ton URL
Dans **Settings** → **Domains** → quelque chose comme :
`https://license-server-production-xxxx.up.railway.app`

---

## ÉTAPES RENDER (alternative)

### 1. Va sur https://render.com → New Web Service
2. Connecte ton GitHub → sélectionne le repo
3. **Build Command** : `pip install -r requirements.txt`
4. **Start Command** : `gunicorn server:app --bind 0.0.0.0:$PORT`

### 2. Ajoute PostgreSQL
1. Render Dashboard → **New** → **PostgreSQL** (plan Free)
2. Copie l'**Internal Database URL**
3. Dans ton Web Service → **Environment** → ajoute :
```
DATABASE_URL    =  (colle l'URL copiée)
ADMIN_PASSWORD  =  ton_mot_de_passe_secret
SECRET_KEY      =  une_chaine_aleatoire_longue
```

---

## APRÈS LE DÉPLOIEMENT

Modifie cette ligne dans `mining_bot_v3.4.py` :
```python
LICENSE_SERVER = "https://TON-URL.up.railway.app"
```

Accède au dashboard admin : `https://TON-URL.up.railway.app/`

---

## FONCTIONNEMENT

1. Un ami lance le bot → son HWID est envoyé au serveur
2. Statut **pending** → tu vois sa demande dans le dashboard
3. Tu cliques **APPROUVER** → il peut utiliser le bot
4. Tu peux **suspendre** ou **bannir** à tout moment
5. Les données sont **permanentes** dans PostgreSQL (pas de perte au redéploiement)
