import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Remonter à la racine du projet (2 niveaux au-dessus de auth.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "configs", "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "configs", "token.json")

def authenticate():
    creds = None
    
    # Vérifier si le fichier credentials.json existe
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Le fichier credentials.json est introuvable à l'emplacement : {CREDENTIALS_PATH}\n"
            f"Veuillez placer vos identifiants OAuth dans F:\\surveillance_system\\configs\\credentials.json"
        )
    
    # Charger le token existant si disponible
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # Rafraîchir ou obtenir de nouveaux identifiants
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Sauvegarder le token
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds
