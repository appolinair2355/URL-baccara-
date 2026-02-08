import os
from dotenv import load_dotenv

# Chargement des variables d'environnement (pour développement local)
load_dotenv()

# ============================================================
# CONFIGURATION TELEGRAM API
# ============================================================

# API Telegram (https://my.telegram.org)
API_ID = int(os.getenv('API_ID', '29177661'))
API_HASH = os.getenv('API_HASH', 'a8639172fa8d35dbfd8ea46286d349ab')

# Bot Token (de @BotFather)
BOT_TOKEN = os.getenv('BOT_TOKEN', '8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU')

# ID Admin (votre ID Telegram)
ADMIN_ID = int(os.getenv('ADMIN_ID', '1190237801'))

# ============================================================
# CONFIGURATION RENDER.COM
# ============================================================

# Port (Render utilise 10000 par défaut)
PORT = int(os.getenv('PORT', '10000'))

# Mode déploiement Render
RENDER_DEPLOYMENT = os.getenv('RENDER_DEPLOYMENT', 'true').lower() == 'true'

# Session string pour Render (persistance connexion)
TELEGRAM_SESSION = os.getenv('TELEGRAM_SESSION', '')

# ============================================================
# CONFIGURATION WEBHOOK (optionnel pour Render)
# ============================================================

# URL de l'application Render (pour webhook)
# Exemple: https://votre-bot.onrender.com
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

# Mode webhook ou polling
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'

# ============================================================
# CONFIGURATION BASE DE DONNÉES (optionnel pour Render)
# ============================================================

# URL PostgreSQL (Render PostgreSQL)
DATABASE_URL = os.getenv('DATABASE_URL', '')

# Mode persistence: 'json' (fichier) ou 'postgres' (base de données)
PERSISTENCE_MODE = os.getenv('PERSISTENCE_MODE', 'json')

# ============================================================
# CONFIGURATION OCR & PAIEMENT
# ============================================================

# Clé API OCR.space
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K86527928888957')

# Lien de paiement MoneyFusion
PAYMENT_LINK = os.getenv('PAYMENT_LINK', 'https://my.moneyfusion.net/6977f7502181d4ebf722398d')

# Tarification
BASE_MONTANT = int(os.getenv('BASE_MONTANT', '205'))  # FCFA
BASE_MINUTES = int(os.getenv('BASE_MINUTES', '1440'))  # 24h

# ============================================================
# CONFIGURATION CANAUX (valeurs par défaut, modifiables via commandes)
# ============================================================

# Canal source (où le bot lit les numéros)
DEFAULT_SOURCE_CHANNEL_ID = int(os.getenv('DEFAULT_SOURCE_CHANNEL_ID', '-1002682552255'))

# Canal de prédiction (où le bot envoie les prédictions)
DEFAULT_PREDICTION_CHANNEL_ID = int(os.getenv('DEFAULT_PREDICTION_CHANNEL_ID', '-1003329818758'))

# Canal VIP (canal privé des abonnés)
DEFAULT_VIP_CHANNEL_ID = int(os.getenv('DEFAULT_VIP_CHANNEL_ID', '-1003329818758'))

# Lien d'invitation VIP
DEFAULT_VIP_CHANNEL_LINK = os.getenv('DEFAULT_VIP_CHANNEL_LINK', 'https://t.me/+Ju0A1LU7Zno5ZTM0')

# ============================================================
# CONFIGURATION ESSAI GRATUIT
# ============================================================

# Durée essai gratuit en minutes
TRIAL_DURATION_MINUTES = int(os.getenv('TRIAL_DURATION_MINUTES', '15'))

# ============================================================
# CONFIGURATION LOGGING
# ============================================================

# Niveau de log
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Format des logs
LOG_FORMAT = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ============================================================
# FICHIERS DE DONNÉES (chemins relatifs pour Render)
# ============================================================

# Dossier de données (Render a un filesystem éphémère sauf si disque persistant)
DATA_DIR = os.getenv('DATA_DIR', '/data' if RENDER_DEPLOYMENT else '.')

# Fichiers JSON
USERS_FILE = os.path.join(DATA_DIR, 'users_data.json')
CHANNELS_CONFIG_FILE = os.path.join(DATA_DIR, 'channels_config.json')
TRIAL_CONFIG_FILE = os.path.join(DATA_DIR, 'trial_config.json')
OCR_DATA_FILE = os.path.join(DATA_DIR, 'ocr_data.json')
VALIDATED_PAYMENTS_FILE = os.path.join(DATA_DIR, 'validated_payments.json')

# ============================================================
# VÉRIFICATIONS ET VALIDATIONS
# ============================================================

def validate_config():
    """Vérifie que la configuration est complète"""
    errors = []
    
    if not API_ID or API_ID == 0:
        errors.append("API_ID manquant")
    
    if not API_HASH:
        errors.append("API_HASH manquant")
    
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN manquant")
    
    if not ADMIN_ID:
        errors.append("ADMIN_ID manquant")
    
    if errors:
        raise ValueError(f"Configuration invalide: {', '.join(errors)}")
    
    return True

# Validation au chargement
try:
    validate_config()
    print("✅ Configuration validée avec succès")
except ValueError as e:
    print(f"❌ {e}")
    raise

# ============================================================
# AFFICHAGE CONFIG (pour debug)
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print("CONFIGURATION BOT VIP")
    print("=" * 50)
    print(f"API_ID: {API_ID}")
    print(f"ADMIN_ID: {ADMIN_ID}")
    print(f"PORT: {PORT}")
    print(f"RENDER_DEPLOYMENT: {RENDER_DEPLOYMENT}")
    print(f"PERSISTENCE_MODE: {PERSISTENCE_MODE}")
    print(f"DATA_DIR: {DATA_DIR}")
    print("=" * 50)
