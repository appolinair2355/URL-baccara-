"""
Fichier de configuration centralisé
Toutes les variables sont définies ici, mais peuvent être surchargées par les variables d'environnement
"""

import os

# ==================== CONFIGURATION TELEGRAM ====================
# Bot Token (depuis @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU")

# ID du canal/group où envoyer les prédictions
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003846785063")

# Liste des IDs des administrateurs (séparés par virgule si plusieurs via env)
DEFAULT_ADMIN_IDS = "1190237801"
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", DEFAULT_ADMIN_IDS).split(",")]

# ==================== CONFIGURATION RENDER/SERVEUR ====================
# Port d'écoute (Render définit cette variable automatiquement)
PORT = int(os.getenv("PORT", "10000"))

# Host pour le serveur web
HOST = os.getenv("HOST", "0.0.0.0")

# ==================== CONFIGURATION JEU ====================
# Langue par défaut (fr ou tr)
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "fr")

# Délai entre les vérifications (secondes)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))

# Délai entre les envois de messages (évite le flood)
MESSAGE_DELAY = float(os.getenv("MESSAGE_DELAY", "0.5"))

# ==================== CONFIGURATION STRATÉGIE ====================
# Nombre de jeux à sauter après validation (min et max)
SKIP_AFTER_WIN_MIN = int(os.getenv("SKIP_AFTER_WIN_MIN", "3"))
SKIP_AFTER_WIN_MAX = int(os.getenv("SKIP_AFTER_WIN_MAX", "4"))

# Nombre de rattrapages autorisés
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

# ==================== CONFIGURATION API 1XBET ====================
# URL de l'API
API_URL = os.getenv("API_URL", "https://1xbet-new.com/LiveFeed/GetChampZip?champ=2050671")

# Timeout pour les requêtes API (secondes)
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))

# ==================== TRADUCTIONS ====================
LANGUAGES = {"fr": "Français", "tr": "Türkçe"}

TRANSLATIONS = {
    "fr": {
        "prediction": "<b>Prédiction</b> 🚩: {symbol}(Joueur)\nJeu 🏠: #N{game_number}\nRattrapage🛡: 2",
        "bot_started": "✅ Le bot a démarré et est en ligne!",
        "bot_already_started": "❌ Le bot est déjà démarré.",
        "bot_stopped": "🛑 Le bot a été arrêté.",
        "bot_already_stopped": "❌ Le bot est déjà arrêté.",
        "no_permission": "⛔ Vous n'avez pas les permissions nécessaires.",
        "prediction_validated": "✅ Prédiction validée au jeu #{game_number}",
        "prediction_failed": "❌ Prédiction échouée",
    },
    "tr": {
        "prediction": "<b>Tahmin</b> 🚩: {symbol}(Oyuncu)\nOda 🏠: #N{game_number}\nMartingale 🛡: 2",
        "bot_started": "✅ Bot başladı ve çevrimiçi!",
        "bot_already_started": "❌ Bot zaten çalışıyor.",
        "bot_stopped": "🛑 Bot durduruldu.",
        "bot_already_stopped": "❌ Bot zaten durdurulmuş.",
        "no_permission": "⛔ Gerekli izinlere sahip değilsiniz.",
        "prediction_validated": "✅ Tahmin #{game_number} oyununda doğrulandı",
        "prediction_failed": "❌ Tahmin başarısız oldu",
    }
}

# ==================== FONCTIONS UTILITAIRES ====================
def get_translation(key: str, lang: str = None) -> str:
    """Récupère une traduction"""
    if lang is None:
        lang = DEFAULT_LANGUAGE
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)

def get_chat_ids() -> list:
    """Retourne la liste des IDs de chat"""
    return [CHANNEL_ID]

def get_admin_ids() -> list:
    """Retourne la liste des IDs admin"""
    return ADMIN_IDS

