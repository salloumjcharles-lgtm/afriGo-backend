markdown
# AfriGo Backend - API VTC Côte d'Ivoire

## Installation

1. Créer un environnement virtuel :
bash
python -m venv venv
source venv/bin/activate # Linux/Mac
venv\Scripts\activate # Windows

2. Installer les dépendances :
bash
pip install -r requirements.txt

3. Configurer les variables d'environnement :
bash
cp .env.example .env
# Modifier .env avec vos valeurs

4. Lancer le serveur :
bash
uvicorn server:app --reload --port 8001

## API Endpoints

- POST /api/auth/register - Inscription
- POST /api/auth/login - Connexion
- POST /api/rides/request - Demander une course
- PUT /api/rides/{id}/accept - Accepter une course
