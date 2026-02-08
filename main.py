import os
import asyncio
import re
import logging
import sys
import json
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights
from aiohttp import web
from PIL import Image
from io import BytesIO
import requests
import base64

# ============================================================
# CONFIGURATION - Variables d'environnement pour Render
# ============================================================

# API Telegram
API_ID = int(os.getenv('API_ID', '29177661'))
API_HASH = os.getenv('API_HASH', 'a8639172fa8d35dbfd8ea46286d349ab')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1190237801'))

# Configuration Render - CORRIGÉ : utiliser ./data au lieu de /data
PORT = int(os.getenv('PORT', '10000'))
RENDER_DEPLOYMENT = os.getenv('RENDER_DEPLOYMENT', 'true').lower() == 'true'
TELEGRAM_SESSION = os.getenv('TELEGRAM_SESSION', '')

# Dossier de données - CORRIGÉ : chemin relatif obligatoire sur Render
DATA_DIR = os.getenv('DATA_DIR', './data')

# Créer le dossier de données avec gestion d'erreur
try:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"✅ Dossier créé : {DATA_DIR}")
except PermissionError as e:
    print(f"⚠️ Permission refusée pour {DATA_DIR}, utilisation de ./data")
    DATA_DIR = './data'
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception as e:
    print(f"⚠️ Erreur création dossier : {e}, utilisation de ./data")
    DATA_DIR = './data'
    os.makedirs(DATA_DIR, exist_ok=True)

# Fichiers de données
USERS_FILE = os.path.join(DATA_DIR, 'users_data.json')
CHANNELS_CONFIG_FILE = os.path.join(DATA_DIR, 'channels_config.json')
TRIAL_CONFIG_FILE = os.path.join(DATA_DIR, 'trial_config.json')
OCR_DATA_FILE = os.path.join(DATA_DIR, 'ocr_data.json')
VALIDATED_PAYMENTS_FILE = os.path.join(DATA_DIR, 'validated_payments.json')

# Configuration OCR & Paiement
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K86527928888957')
PAYMENT_LINK = os.getenv('PAYMENT_LINK', 'https://my.moneyfusion.net/6977f7502181d4ebf722398d')
BASE_MONTANT = int(os.getenv('BASE_MONTANT', '205'))
BASE_MINUTES = int(os.getenv('BASE_MINUTES', '1440'))

# Configuration Canaux par défaut
DEFAULT_SOURCE_CHANNEL_ID = int(os.getenv('DEFAULT_SOURCE_CHANNEL_ID', '-1002682552255'))
DEFAULT_PREDICTION_CHANNEL_ID = int(os.getenv('DEFAULT_PREDICTION_CHANNEL_ID', '-1003329818758'))
DEFAULT_VIP_CHANNEL_ID = int(os.getenv('DEFAULT_VIP_CHANNEL_ID', '-1003329818758'))
DEFAULT_VIP_CHANNEL_LINK = os.getenv('DEFAULT_VIP_CHANNEL_LINK', 'https://t.me/+s3y7GejUVHU0YjE0')

# Essai gratuit
DEFAULT_TRIAL_DURATION = int(os.getenv('TRIAL_DURATION_MINUTES', '15'))

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Vérification configuration
if not API_ID or API_ID == 0:
    logger.error("❌ API_ID manquant")
    exit(1)
if not API_HASH:
    logger.error("❌ API_HASH manquant")
    exit(1)
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN manquant")
    exit(1)

# Initialisation client Telethon
client = TelegramClient(StringSession(TELEGRAM_SESSION), API_ID, API_HASH)

# ============================================================
# VARIABLES GLOBALES
# ============================================================

channels_config = {
    'source_channel_id': DEFAULT_SOURCE_CHANNEL_ID,
    'prediction_channel_id': DEFAULT_PREDICTION_CHANNEL_ID,
    'vip_channel_id': DEFAULT_VIP_CHANNEL_ID,
    'vip_channel_link': DEFAULT_VIP_CHANNEL_LINK
}

trial_config = {
    'duration_minutes': DEFAULT_TRIAL_DURATION
}

users_data = {}
ocr_data = {"paiements": {}, "references": {}, "factures": {}}
validated_payments = {}

# États
user_conversation_state = {}
user_ocr_state = {}
watch_state = {}

# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def load_json(file_path, default=None):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Erreur chargement {file_path}: {e}")
    return default or {}

def save_json(file_path, data):
    try:
        # S'assurer que le dossier existe
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur sauvegarde {file_path}: {e}")

def load_all_configs():
    global channels_config, trial_config, users_data, ocr_data, validated_payments
    channels_config.update(load_json(CHANNELS_CONFIG_FILE, channels_config))
    trial_config.update(load_json(TRIAL_CONFIG_FILE, trial_config))
    users_data.update(load_json(USERS_FILE, {}))
    ocr_data.update(load_json(OCR_DATA_FILE, ocr_data))
    validated_payments.update(load_json(VALIDATED_PAYMENTS_FILE, {}))
    logger.info("✅ Configurations chargées")

def save_all_configs():
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    save_json(TRIAL_CONFIG_FILE, trial_config)
    save_json(USERS_FILE, users_data)
    save_json(OCR_DATA_FILE, ocr_data)
    save_json(VALIDATED_PAYMENTS_FILE, validated_payments)

# ============================================================
# GESTION CANAUX
# ============================================================

def get_vip_channel_id():
    return channels_config.get('vip_channel_id', DEFAULT_VIP_CHANNEL_ID)

def get_vip_channel_link():
    return channels_config.get('vip_channel_link', DEFAULT_VIP_CHANNEL_LINK)

def get_prediction_channel_id():
    return channels_config.get('prediction_channel_id', DEFAULT_PREDICTION_CHANNEL_ID)

# ============================================================
# GESTION UTILISATEURS
# ============================================================

def get_user(user_id: int) -> dict:
    user_id_str = str(user_id)
    if user_id_str not in users_data:
        users_data[user_id_str] = {
            'registered': False, 'nom': None, 'prenom': None, 'pays': None,
            'trial_started': None, 'trial_used': False, 'trial_joined_at': None,
            'subscription_end': None, 'vip_expires_at': None, 'is_in_channel': False,
            'total_time_added': 0
        }
        save_json(USERS_FILE, users_data)
    return users_data[user_id_str]

def update_user(user_id: int, data: dict):
    users_data[str(user_id)].update(data)
    save_json(USERS_FILE, users_data)

def is_user_subscribed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    user = get_user(user_id)
    if not user.get('subscription_end'):
        return False
    try:
        return datetime.now() < datetime.fromisoformat(user['subscription_end'])
    except:
        return False

def is_trial_active(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    user = get_user(user_id)
    if user.get('trial_used') or not user.get('trial_joined_at'):
        return False
    try:
        trial_end = datetime.fromisoformat(user['trial_joined_at']) + timedelta(minutes=trial_config['duration_minutes'])
        return datetime.now() < trial_end
    except:
        return False

def format_time_remaining(expiry_iso: str) -> str:
    try:
        expiry = datetime.fromisoformat(expiry_iso)
        remaining = expiry - datetime.now()
        if remaining.total_seconds() <= 0:
            return "⛔ Expiré"
        total_seconds = int(remaining.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}j")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        return " ".join(parts) if parts else "⏳ Quelques secondes"
    except:
        return "❓ Inconnu"

def parse_duration(input_str: str) -> int:
    input_str = input_str.strip().lower()
    if input_str.isdigit():
        return int(input_str)
    if input_str.endswith('h'):
        try:
            return int(float(input_str[:-1]) * 60)
        except:
            return 0
    if input_str.endswith('m'):
        try:
            return int(input_str[:-1])
        except:
            return 0
    return 0

# ============================================================
# FONCTIONS OCR
# ============================================================

async def ocr_space_api(image_bytes):
    url = "https://api.ocr.space/parse/image"
    payload = {
        'apikey': OCR_API_KEY,
        'language': 'fre',
        'isOverlayRequired': False
    }
    files = {'image': ('image.jpg', image_bytes)}
    try:
        response = requests.post(url, data=payload, files=files, timeout=30)
        result = response.json()
        if result.get("ParsedResults"):
            return result["ParsedResults"][0].get("ParsedText", "")
    except Exception as e:
        logger.error(f"Erreur OCR API: {e}")
    return ""

def extraire_montant(texte):
    patterns = [
        r'Montant\s*[:：]?\s*([0-9\s]+)[.,]?\d*\s*FCFA',
        r'(\d[\d\s]*)\s*FCFA',
        r'Montant.*?(\d[\d\s]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, texte, re.IGNORECASE)
        if match:
            montant_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                return float(montant_str)
            except:
                continue
    return None

def extraire_reference(texte):
    match = re.search(r'Référence\s*de\s*paiement\s*[:：]?\s*([a-f0-9-]+)', texte, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()
    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', texte, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()
    return None

def extraire_numero_facture(texte):
    match = re.search(r'N[°º]?\s*Facture\s*[:：]?\s*([A-Z0-9-]+)', texte, re.IGNORECASE)
    if match:
        return match.group(1).strip().upper()
    match = re.search(r'(FACT-[0-9]+)', texte, re.IGNORECASE)
    if match:
        return match.group(1).strip().upper()
    return None

def calculer_minutes(montant):
    return int((montant / BASE_MONTANT) * BASE_MINUTES)

def formater_duree(minutes):
    jours = minutes // (24 * 60)
    heures = (minutes % (24 * 60)) // 60
    mins = minutes % 60
    parties = []
    if jours > 0:
        parties.append(f"{jours} jour{'s' if jours > 1 else ''}")
    if heures > 0:
        parties.append(f"{heures}h")
    if mins > 0:
        parties.append(f"{mins}min")
    return " ".join(parties) if parties else "0 min"

def verifier_doublon(reference, facture):
    doublons = []
    if reference and reference in ocr_data.get("references", {}):
        ancien_user = ocr_data["references"][reference]
        doublons.append(f"📌 Référence déjà utilisée (User: {ancien_user})")
    if facture and facture in ocr_data.get("factures", {}):
        ancien_user = ocr_data["factures"][facture]
        doublons.append(f"📌 Facture déjà utilisée (User: {ancien_user})")
    return doublons

# ============================================================
# GESTION VIP
# ============================================================

async def delete_message_after_delay(chat_id: int, message_id: int, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    try:
        await client.delete_messages(chat_id, [message_id])
    except:
        pass

async def add_user_to_vip(user_id: int, duration_minutes: int, is_trial: bool = False):
    if user_id == ADMIN_ID:
        return True
    
    try:
        now = datetime.now()
        expires_at = now + timedelta(minutes=duration_minutes)
        
        update_data = {
            'vip_joined_at': now.isoformat(),
            'vip_expires_at': expires_at.isoformat(),
            'subscription_end': expires_at.isoformat(),
            'is_in_channel': True,
            'total_time_added': get_user(user_id).get('total_time_added', 0) + duration_minutes
        }
        
        if is_trial:
            update_data['trial_joined_at'] = now.isoformat()
        else:
            update_data['trial_used'] = True
        
        update_user(user_id, update_data)
        
        vip_link = get_vip_channel_link()
        
        if is_trial:
            msg = f"""
🎊 **BIENVENUE DANS L'AVENTURE !** 🎊

✨ *Votre essai gratuit est activé !* ✨

⏳ **Durée :** 15 minutes
📅 **Expire le :** {expires_at.strftime('%d/%m/%Y à %H:%M')}

🔗 **VOTRE PASS VIP :**
{vip_link}

⚡ **CE LIEN DISPARAÎT DANS 10 SECONDES !** ⚡
🚀 **CLIQUEZ IMMÉDIATEMENT !**

🎰 *Prêt à découvrir le système exclusif ?*
"""
        else:
            time_str = format_time_remaining(expires_at.isoformat())
            msg = f"""
🎉 **FÉLICITATIONS !** 🎉

🌟 *Votre accès VIP est maintenant ACTIF !* 🌟

⏱️ **Temps attribué :** {time_str}
📅 **Validité :** Jusqu'au {expires_at.strftime('%d/%m/%Y à %H:%M')}

🔗 **VOTRE LIEN VIP EXCLUSIF :**
{vip_link}

⚠️ **⚡ ULTRA URGENT : CE LIEN S'AUTO-DÉTRUIT DANS 10 SECONDES ! ⚡**

🎯 *Rejoignez immédiatement ou perdez votre accès à jamais !*

💎 *Bienvenue dans l'élite...*
"""
        
        link_msg = await client.send_message(user_id, msg)
        asyncio.create_task(delete_message_after_delay(user_id, link_msg.id, 10))
        
        user = get_user(user_id)
        await client.send_message(ADMIN_ID, f"""
📋 **{'ESSAI' if is_trial else 'NOUVEL ABONNEMENT'}**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
🌍 {user.get('pays', 'N/A')}
⏱️ {duration_minutes} minutes
📅 Expire : {expires_at.strftime('%d/%m/%Y %H:%M')}
""")
        
        asyncio.create_task(auto_kick_user(user_id, duration_minutes * 60))
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur ajout VIP {user_id}: {e}")
        return False

async def extend_or_add_vip(user_id: int, additional_minutes: int, payment_info: dict = None):
    try:
        user = get_user(user_id)
        now = datetime.now()
        
        if is_user_subscribed(user_id) or is_trial_active(user_id):
            current_end = datetime.fromisoformat(user.get('subscription_end') or user.get('vip_expires_at'))
            start_from = max(now, current_end)
            is_extension = True
        else:
            start_from = now
            is_extension = False
        
        new_end = start_from + timedelta(minutes=additional_minutes)
        
        update_user(user_id, {
            'subscription_end': new_end.isoformat(),
            'vip_expires_at': new_end.isoformat(),
            'total_time_added': user.get('total_time_added', 0) + additional_minutes,
            'is_in_channel': True,
            'trial_used': True
        })
        
        time_str = format_time_remaining(new_end.isoformat())
        vip_link = get_vip_channel_link()
        
        if is_extension:
            msg = f"""
⏫ **EXTENSION RÉUSSIE !** ⏫

✨ *Votre temps VIP vient d'être prolongé !* ✨

📈 **+{additional_minutes:,} minutes** ajoutées !
📅 **Nouvelle expiration :** {new_end.strftime('%d/%m/%Y à %H:%M')}
⏳ **Temps total :** {time_str}

🔗 **LIEN VIP (valide 10s) :**
{vip_link}

⚡ **CLIQUEZ VITE AVANT DISPARITION !**

🚀 *Continuez l'aventure sans interruption...*
"""
        else:
            msg = f"""
🎊 **BIENVENUE AU CLUB VIP !** 🎊

🔥 *Votre paiement a été validé avec succès !* 🔥

💰 **Montant :** {payment_info.get('montant', 'N/A')} FCFA
⏱️ **Temps attribué :** {additional_minutes:,} minutes ({time_str})
📅 **Expire le :** {new_end.strftime('%d/%m/%Y à %H:%M')}

🔗 **VOTRE PASS VIP EXCLUSIF :**
{vip_link}

⚠️ **🚨 CE LIEN S'AUTO-DÉTRUIT DANS 10 SECONDES ! 🚨**

💎 *Vous faites maintenant partie de l'élite !*
"""
        
        link_msg = await client.send_message(user_id, msg)
        asyncio.create_task(delete_message_after_delay(user_id, link_msg.id, 10))
        
        admin_msg = f"""
📋 **PAIEMENT OCR VALIDÉ**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
🌍 {user.get('pays', 'N/A')}
💰 Montant : {payment_info.get('montant', 'N/A')} FCFA
🧾 Facture : `{payment_info.get('facture', 'N/A')}`
🔑 Référence : `{payment_info.get('reference', 'N/A')}`
⏱️ Minutes : {additional_minutes:,}
📅 Expire : {new_end.strftime('%d/%m/%Y %H:%M')}

💡 `/retirer {user_id}` pour expulser
"""
        await client.send_message(ADMIN_ID, admin_msg)
        
        remaining_seconds = int((new_end - now).total_seconds())
        asyncio.create_task(auto_kick_user(user_id, remaining_seconds))
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur extend_or_add_vip {user_id}: {e}")
        await client.send_message(user_id, "❌ Erreur lors de l'activation. Contactez @Kouamappoloak")
        return False

async def auto_kick_user(user_id: int, delay_seconds: int):
    if user_id == ADMIN_ID:
        return
    
    await asyncio.sleep(delay_seconds)
    
    try:
        if is_user_subscribed(user_id):
            logger.info(f"Utilisateur {user_id} a renouvelé, annulation expulsion")
            return
        
        user = get_user(user_id)
        entity = await client.get_input_entity(get_vip_channel_id())
        
        await client.kick_participant(entity, user_id)
        await client(EditBannedRequest(
            channel=entity, participant=user_id,
            banned_rights=ChatBannedRights(until_date=None, view_messages=False)
        ))
        
        update_user(user_id, {
            'vip_expires_at': None, 'subscription_end': None,
            'is_in_channel': False, 'trial_used': True
        })
        
        await client.send_message(user_id, f"""
😢 **VOTRE AVENTURE S'ARRÊTE ICI...** 😢

⏰ *Votre accès VIP est malheureusement terminé.*

💔 *Nous espérons vous revoir très bientôt !*

💳 **Pour réactiver votre accès :**
👉 Tapez /payer

🌟 *Rejoignez-nous à nouveau et retrouvez l'excitation !*

📞 **Besoin d'aide ?** @Kouamappoloak
""")
        
        await client.send_message(ADMIN_ID, f"""
🚫 **UTILISATEUR RETIRÉ**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
⏰ Expiration naturelle
""")
        
        logger.info(f"🚫 Utilisateur {user_id} expulsé")
        
    except Exception as e:
        logger.error(f"Erreur expulsion {user_id}: {e}")

# ============================================================
# COMMANDES UTILISATEURS
# ============================================================

@client.on(events.NewMessage(pattern='/start'))
async def cmd_start(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        await event.respond("""
👑 **BIENVENUE, MAÎTRE !** 👑

🌟 *Vous contrôlez le royaume VIP !* 🌟

📋 **VOS POUVOIRS :**

👥 `/users` - Voir tous les sujets
⏱️ `/monitor` - Surveillance active
👁️ `/watch` - Mode espion temps réel
⏫ `/extend ID durée` - Accorder du temps
🚫 `/retirer ID` - Expulser immédiatement

⚙️ **CONFIGURATION :**
🔗 `/setviplink URL` - Changer lien VIP
🆔 `/setvipid ID` - Changer ID canal VIP
🎯 `/setpredictionid ID` - Changer ID prédiction
📊 `/showids` - Voir configuration actuelle

📈 **STATISTIQUES :**
📊 `/stats` - Stats paiements OCR
📋 `/validated` - Liste paiements validés
🗑️ `/clearocr` - Reset données OCR

💡 `/help` - Aide détaillée

🎰 *Le pouvoir est entre vos mains...*
""")
        return
    
    user = get_user(user_id)
    
    if user.get('registered'):
        status_emoji = "✅" if is_user_subscribed(user_id) else "🎁" if is_trial_active(user_id) else "❌"
        status_text = "ABONNÉ VIP" if is_user_subscribed(user_id) else "ESSAI ACTIF" if is_trial_active(user_id) else "INACTIF"
        
        await event.respond(f"""
👋 **HEUREUX DE VOUS REVOIR !** 👋

{status_emoji} *Statut :* **{status_text}**
⏳ *Temps restant :* `{get_remaining_time(user_id)}`

💎 *Que souhaitez-vous faire ?*

💳 `/payer` - Renouveler mon abonnement
📊 `/status` - Voir mes détails
❓ `/help` - Obtenir de l'aide

🚀 *Prêt pour de nouvelles victoires ?*
""")
        return
    
    user_conversation_state[user_id] = 'awaiting_nom'
    await event.respond("""
🎉 **BIENVENUE DANS L'AVENTURE !** 🎉

🌟 *Vous êtes sur le point de découvrir quelque chose d'EXTRAORDINAIRE !* 🌟

🎁 **EN CADEAU DE BIENVENUE :**
⏱️ **15 MINUTES D'ESSAI GRATUIT !**

💎 *Accès immédiat au canal VIP !*
🔥 *Découvrez le système exclusif !*
⭐ *Zero risque, 100% découverte !*

📝 **Commençons par votre inscription :**

**Étape 1/3** 🚀
*Quel est votre nom de famille ?*
""")

@client.on(events.NewMessage(pattern='/help'))
async def cmd_help(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        await event.respond("""
📖 **GUIDE DU MAÎTRE** 📖

**Gestion des sujets :**
`/users` - Liste complète avec statuts
`/monitor` - Utilisateurs actifs uniquement
`/watch` - Surveillance automatique (30s)
`/stopwatch` - Arrêter surveillance
`/extend 123456 2h` - Ajouter 2 heures

**Contrôle absolu :**
`/retirer 123456` - Expulsion immédiate

**Configuration système :**
`/setviplink https://t.me/...` - Nouveau lien VIP
`/setvipid -100...` - Nouveau canal VIP
`/setpredictionid -100...` - Canal prédiction
`/showids` - Voir tout

**Données :**
`/stats` - Statistiques OCR
`/validated` - Historique validations
`/clearocr` - Reset complet

🆘 **Support :** @Kouamappoloak
""")
        return
    
    await event.respond("""
📖 **VOTRE GUIDE COMPLET** 📖

**🚀 Démarrage rapide :**
`/start` - Créer mon compte / Voir statut
`/payer` - Obtenir un abonnement VIP
`/status` - Vérifier mon temps restant

**💳 Paiement :**
1️⃣ Tapez `/payer`
2️⃣ Cliquez sur **PAYER MAINTENANT**
3️⃣ Payez sur le site sécurisé
4️⃣ Revenez ici et cliquez **J'AI DÉJÀ PAYÉ**
5️⃣ Envoyez votre capture d'écran
6️⃣ ✅ Recevez votre lien VIP instantanément !

**💰 Tarif :**
• 205 FCFA = 24 heures
• Calcul automatique selon montant
• Plus vous payez, plus vous avez de temps !

**⚡ Important :**
• Le lien VIP disparaît après 10 secondes !
• Rejoignez IMMÉDIATEMENT
• Accès automatique après validation OCR

**🆘 Besoin d'aide ?**
Contactez : @Kouamappoloak

🎰 *Bonne chance dans vos prédictions !*
""")

@client.on(events.NewMessage(pattern='/payer'))
async def cmd_payer(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    if user_id == ADMIN_ID:
        await event.respond("👑 *Vous êtes éternel, Maître...*")
        return
    
    user = get_user(user_id)
    if not user.get('registered'):
        await event.respond("""
❌ **INSCRIPTION REQUISE** ❌

📝 *Vous devez d'abord créer votre compte :*

👉 Tapez `/start` pour vous inscrire

🎁 *15 minutes gratuites vous attendent !*
""")
        return
    
    buttons = [
        [Button.url("💳 PAYER MAINTENANT", PAYMENT_LINK)],
        [Button.inline("📸 J'AI DÉJÀ PAYÉ", b"envoyer_capture")]
    ]
    
    await event.respond(f"""
💎 **ACCÈS VIP EXCLUSIF** 💎

🌟 *Rejoignez l'élite dès maintenant !* 🌟

💰 **TARIF AVANTAGEUX :**
🔥 **{BASE_MONTANT} FCFA = {BASE_MINUTES // 60} HEURES** 🔥
📈 *Calcul proportionnel automatique*

**✨ Ce que vous obtenez :**
✅ Accès immédiat au canal VIP
✅ Validations ultra-rapides par IA
✅ Support prioritaire 24/7
✅ Renouvellement facile

**🚀 COMMENT PROCÉDER :**

1️⃣ **Cliquez sur** 💳 **PAYER MAINTENANT**
2️⃣ **Effectuez votre paiement** sur le site sécurisé
3️⃣ **Revenez ici** et cliquez 📸 **J'AI DÉJÀ PAYÉ**
4️⃣ **Envoyez votre capture** d'écran
5️⃣ **Recevez instantanément** votre lien VIP !

⚡ *L'assistant OCR valide en 5 secondes !*

🎯 **PRÊT À REJOINDRE L'AVENTURE ?**

*Choisissez une option ci-dessous :*
""", buttons=buttons)

@client.on(events.CallbackQuery(data=b"envoyer_capture"))
async def callback_envoyer_capture(event):
    user_id = event.sender_id
    
    user = get_user(user_id)
    if not user.get('registered'):
        await event.answer("❌ Inscrivez-vous d'abord avec /start", alert=True)
        return
    
    user_ocr_state[user_id] = "awaiting_capture"
    
    await event.answer("✅ Parfait ! Envoyez votre capture")
    await event.edit("""
📸 **ENVOYEZ VOTRE CAPTURE**

🔍 *Notre assistant IA va analyser :*
• ✅ Le montant payé
• ✅ La référence de transaction  
• ✅ Le numéro de facture

⚡ **Validation en 5 secondes !**

📤 *Envoyez votre capture d'écran maintenant...*
""")

@client.on(events.NewMessage(pattern='/status'))
async def cmd_status(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user.get('registered'):
        await event.respond("""
❌ **COMPTE NON TROUVÉ** ❌

📝 *Créez votre compte d'abord :*
👉 `/start`

🎁 *Essai gratuit de 15 minutes !*
""")
        return
    
    status_emoji = "👑" if user_id == ADMIN_ID else "✅" if is_user_subscribed(user_id) else "🎁" if is_trial_active(user_id) else "❌"
    status_text = "ADMINISTRATEUR" if user_id == ADMIN_ID else "ABONNÉ VIP" if is_user_subscribed(user_id) else "ESSAI ACTIF" if is_trial_active(user_id) else "INACTIF"
    
    await event.respond(f"""
📊 **VOTRE TABLEAU DE BORD** 📊

{status_emoji} **Statut :** *{status_text}*
👤 **Nom :** {user.get('prenom', '')} {user.get('nom', '')}
🌍 **Pays :** {user.get('pays', 'Non spécifié')}
⏳ **Temps restant :** `{get_remaining_time(user_id)}`

📈 **Total cumulé :** {user.get('total_time_added', 0):,} minutes

💡 *Besoin de plus de temps ?*
👉 `/payer` pour renouveler

🚀 *Continuez l'aventure !*
""")

# ============================================================
# COMMANDES ADMIN
# ============================================================

@client.on(events.NewMessage(pattern='/users'))
async def cmd_users(event):
    if event.sender_id != ADMIN_ID:
        return
    
    if not users_data:
        await event.respond("📭 *Aucun utilisateur enregistré*")
        return
    
    lines = []
    for uid_str, info in users_data.items():
        uid = int(uid_str)
        if uid == ADMIN_ID:
            continue
            
        status = "🟢" if is_user_subscribed(uid) else "🟡" if is_trial_active(uid) else "🔴"
        name = f"{info.get('prenom', '')} {info.get('nom', '')}".strip() or "Anonyme"
        
        lines.append(f"{status} `{uid}` | {name[:20]:<20} | {get_remaining_time(uid)}")
    
    if not lines:
        await event.respond("📭 *Aucun utilisateur*")
        return
    
    for i in range(0, len(lines), 50):
        chunk = lines[i:i+50]
        header = f"""
📋 **RÉPERTOIRE DES MEMBRES**
*Total : {len(lines)} utilisateurs*

"""
        await event.respond(header + "\n".join(chunk))
        await asyncio.sleep(0.3)

@client.on(events.NewMessage(pattern='/monitor'))
async def cmd_monitor(event):
    if event.sender_id != ADMIN_ID:
        return
    
    active = []
    for uid_str, info in users_data.items():
        uid = int(uid_str)
        if uid == ADMIN_ID:
            continue
        if is_user_subscribed(uid) or is_trial_active(uid):
            name = f"{info.get('prenom', '')} {info.get('nom', '')}".strip() or "Anonyme"
            active.append(f"🟢 `{uid}` | {name[:18]:<18} | {get_remaining_time(uid)}")
    
    if not active:
        await event.respond("""
🔴 **AUCUN UTILISATEUR ACTIF**

💤 *Tous les accès sont expirés...*
""")
        return
    
    await event.respond(f"""
⏱️ **SURVEILLANCE ACTIVE**

*Utilisateurs connectés : {len(active)}*

{chr(10).join(active[:30])}
""")

@client.on(events.NewMessage(pattern='/watch'))
async def cmd_watch(event):
    if event.sender_id != ADMIN_ID:
        return
    
    msg = await event.respond("👁️ **MODE ESPION ACTIVÉ**")
    watch_state[event.sender_id] = {'msg_id': msg.id, 'active': True}
    asyncio.create_task(watch_loop(event.sender_id))

async def watch_loop(admin_id):
    while watch_state.get(admin_id, {}).get('active', False):
        await asyncio.sleep(30)
        try:
            lines = ["👁️ **SURVEILLANCE EN DIRECT**\n"]
            
            count = 0
            for uid_str, info in users_data.items():
                uid = int(uid_str)
                if uid == ADMIN_ID:
                    continue
                if is_user_subscribed(uid) or is_trial_active(uid):
                    count += 1
                    name = f"{info.get('prenom', '')} {info.get('nom', '')}".strip() or "Anon"
                    lines.append(f"🟢 `{uid}` | {name[:12]:<12} | {get_remaining_time(uid)}")
            
            if count == 0:
                lines.append("🔴 Aucun actif")
            
            lines.append(f"\n🔄 {datetime.now().strftime('%H:%M:%S')} | `/stopwatch`")
            
            await client.edit_message(admin_id, watch_state[admin_id]['msg_id'], "\n".join(lines[:35]))
        except:
            break

@client.on(events.NewMessage(pattern='/stopwatch'))
async def cmd_stopwatch(event):
    if event.sender_id != ADMIN_ID:
        return
    watch_state[event.sender_id] = {'active': False}
    await event.respond("✅ *Surveillance arrêtée*")

@client.on(events.NewMessage(pattern=r'^/extend(\s+\d+)?(\s+.+)?$'))
async def cmd_extend(event):
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 3:
        await event.respond("""
⏫ **EXTENSION DE TEMPS**

**Usage :** `/extend ID_UTILISATEUR DURÉE`

**Exemples :**
• `/extend 123456 60` → +60 minutes
• `/extend 123456 2h` → +2 heures  
• `/extend 123456 24h` → +24 heures

⚡ *Effet immédiat !*
""")
        return
    
    try:
        target_id = int(parts[1])
        duration_str = parts[2]
        
        if str(target_id) not in users_data:
            await event.respond(f"""
❌ **UTILISATEUR INTROUVABLE**

🆔 `{target_id}` n'existe pas dans la base.

💡 Vérifiez avec `/users`
""")
            return
        
        additional_minutes = parse_duration(duration_str)
        
        if additional_minutes < 1:
            await event.respond("❌ *Durée invalide (min 1 minute)*")
            return
        
        user = get_user(target_id)
        
        if is_user_subscribed(target_id) or is_trial_active(target_id):
            current_end = datetime.fromisoformat(user.get('subscription_end') or user.get('vip_expires_at'))
            new_end = current_end + timedelta(minutes=additional_minutes)
        else:
            new_end = datetime.now() + timedelta(minutes=additional_minutes)
        
        update_user(target_id, {
            'subscription_end': new_end.isoformat(),
            'vip_expires_at': new_end.isoformat(),
            'total_time_added': user.get('total_time_added', 0) + additional_minutes,
            'is_in_channel': True
        })
        
        time_str = format_time_remaining(new_end.isoformat())
        
        await client.send_message(target_id, f"""
⏫ **TEMPS AJOUTÉ !** ⏫

✨ *{additional_minutes} minutes* viennent d'être ajoutées !

📅 **Nouvelle expiration :** {new_end.strftime('%d/%m/%Y à %H:%M')}
⏳ **Temps total :** {time_str}

🚀 *Profitez bien de votre extension !*
""")
        
        await event.respond(f"""
✅ **EXTENSION RÉUSSIE**

🆔 `{target_id}`
⏱️ **+{additional_minutes} minutes**
📅 **Expire :** {new_end.strftime('%d/%m/%Y %H:%M')}
""")
        
        remaining_seconds = int((new_end - datetime.now()).total_seconds())
        asyncio.create_task(auto_kick_user(target_id, remaining_seconds))
        
    except ValueError:
        await event.respond("❌ *ID invalide*")
    except Exception as e:
        await event.respond(f"❌ *Erreur :* `{e}`")

@client.on(events.NewMessage(pattern=r'^/retirer(\s+\d+)?$'))
async def cmd_retirer(event):
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 2:
        await event.respond("""
🚫 **EXPULSION IMMÉDIATE**

**Usage :** `/retirer ID_UTILISATEUR`

⚠️ *L'utilisateur sera immédiatement :*
• ❌ Expulsé du canal VIP
• 🚫 Banni temporairement
• 📵 Accès révoqué

💡 Trouvez l'ID avec `/users`
""")
        return
    
    try:
        target_id = int(parts[1])
        target_str = str(target_id)
        
        if target_str not in users_data:
            await event.respond(f"""
❌ **UTILISATEUR INTROUVABLE**

🆔 `{target_id}` n'existe pas.

💡 Vérifiez avec `/users`
""")
            return
        
        user = get_user(target_id)
        
        try:
            entity = await client.get_input_entity(get_vip_channel_id())
            await client.kick_participant(entity, target_id)
            await client(EditBannedRequest(
                channel=entity, participant=target_id,
                banned_rights=ChatBannedRights(until_date=None, view_messages=False)
            ))
        except Exception as e:
            logger.error(f"Erreur kick {target_id}: {e}")
        
        update_user(target_id, {
            'vip_expires_at': None,
            'subscription_end': None,
            'is_in_channel': False,
            'trial_used': True
        })
        
        if target_str in validated_payments:
            del validated_payments[target_str]
            save_json(VALIDATED_PAYMENTS_FILE, validated_payments)
        
        await client.send_message(target_id, """
⛔ **ACCÈS RÉVOQUÉ** ⛔

*Votre abonnement a été résilié par l'administrateur.*

📞 **Pour plus d'informations :**
@Kouamappoloak
""")
        
        await event.respond(f"""
✅ **EXPULSION RÉUSSIE**

🆔 `{target_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}

🚫 *L'utilisateur a été retiré avec succès.*
""")
        
    except ValueError:
        await event.respond("❌ *ID invalide*")
    except Exception as e:
        await event.respond(f"❌ *Erreur :* `{e}`")

@client.on(events.NewMessage(pattern=r'^/setviplink(\s+.+)?$'))
async def cmd_setviplink(event):
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 2:
        await event.respond(f"""
🔗 **MODIFICATION LIEN VIP**

**Actuel :** `{get_vip_channel_link()}`

**Usage :** `/setviplink https://t.me/+nouveauLien`

⚡ *Effet immédiat sur les nouveaux paiements*
""")
        return
    
    new_link = parts[1]
    channels_config['vip_channel_link'] = new_link
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    
    await event.respond(f"""
✅ **LIEN VIP MIS À JOUR**

🔗 **Nouveau lien :**
`{new_link}`

🎯 *Les prochains utilisateurs recevront ce lien*
""")

@client.on(events.NewMessage(pattern=r'^/setvipid(\s+.+)?$'))
async def cmd_setvipid(event):
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 2:
        await event.respond(f"""
🆔 **MODIFICATION ID CANAL VIP**

**Actuel :** `{get_vip_channel_id()}`

**Usage :** `/setvipid -1001234567890`

⚠️ *Nécessaire pour les expulsions automatiques*
""")
        return
    
    try:
        new_id = int(parts[1])
        channels_config['vip_channel_id'] = new_id
        save_json(CHANNELS_CONFIG_FILE, channels_config)
        
        await event.respond(f"""
✅ **ID VIP MIS À JOUR**

🆔 **Nouvel ID :** `{new_id}`

🎯 *Configuration enregistrée*
""")
    except ValueError:
        await event.respond("❌ *ID invalide (doit être un nombre)*")

@client.on(events.NewMessage(pattern=r'^/setpredictionid(\s+.+)?$'))
async def cmd_setpredictionid(event):
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 2:
        await event.respond(f"""
🎯 **MODIFICATION ID CANAL PRÉDICTION**

**Actuel :** `{get_prediction_channel_id()}`

**Usage :** `/setpredictionid -1009876543210`
""")
        return
    
    try:
        new_id = int(parts[1])
        channels_config['prediction_channel_id'] = new_id
        save_json(CHANNELS_CONFIG_FILE, channels_config)
        
        await event.respond(f"""
✅ **ID PRÉDICTION MIS À JOUR**

🎯 **Nouvel ID :** `{new_id}`
""")
    except ValueError:
        await event.respond("❌ *ID invalide*")

@client.on(events.NewMessage(pattern='/showids'))
async def cmd_showids(event):
    if event.sender_id != ADMIN_ID:
        return
    
    await event.respond(f"""
📊 **CONFIGURATION ACTUELLE**

🔗 **Lien VIP :**
`{get_vip_channel_link()}`

🆔 **ID Canal VIP :**
`{get_vip_channel_id()}`

🎯 **ID Canal Prédiction :**
`{get_prediction_channel_id()}`

💡 *Utilisez /setviplink, /setvipid, /setpredictionid pour modifier*
""")

@client.on(events.NewMessage(pattern='/stats'))
async def cmd_stats(event):
    if event.sender_id != ADMIN_ID:
        return
    
    total_paiements = sum(len(v) for v in ocr_data.get("paiements", {}).values())
    total_refs = len(ocr_data.get("references", {}))
    total_validated = len(validated_payments)
    
    await event.respond(f"""
📊 **STATISTIQUES OCR**

💰 **Paiements traités :** {total_paiements}
🔍 **Références uniques :** {total_refs}
✅ **Validations auto :** {total_validated}

💱 **Base tarifaire :**
{BASE_MONTANT} FCFA = {BASE_MINUTES} minutes (24h)
""")

@client.on(events.NewMessage(pattern='/validated'))
async def cmd_validated(event):
    if event.sender_id != ADMIN_ID:
        return
    
    if not validated_payments:
        await event.respond("📭 *Aucun paiement validé*")
        return
    
    lines = []
    for uid, info in list(validated_payments.items())[:20]:
        user = get_user(int(uid))
        lines.append(f"""
🆔 `{uid}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
💰 {info.get('montant', 0):.0f} FCFA | ⏱️ {info.get('minutes', 0)} min
📅 {info.get('date', 'N/A')[:10]}
""")
    
    await event.respond(f"""
✅ **PAIEMENTS AUTO-VALIDÉS**
*Total : {len(validated_payments)}*

{chr(10).join(lines)}
""")

@client.on(events.NewMessage(pattern='/clearocr'))
async def cmd_clearocr(event):
    if event.sender_id != ADMIN_ID:
        return
    
    global ocr_data, validated_payments
    ocr_data = {"paiements": {}, "references": {}, "factures": {}}
    validated_payments = {}
    save_json(OCR_DATA_FILE, ocr_data)
    save_json(VALIDATED_PAYMENTS_FILE, validated_payments)
    
    await event.respond("🗑️ **DONNÉES OCR EFFACÉES**")

# ============================================================
# GESTION MESSAGES
# ============================================================

@client.on(events.NewMessage)
async def handle_messages(event):
    if event.is_group or event.is_channel:
        return
    
    if event.message.message.startswith('/'):
        return
    
    user_id = event.sender_id
    
    # OCR en attente
    if event.message.photo and user_id in user_ocr_state:
        if user_ocr_state[user_id] == "awaiting_capture":
            await process_ocr_payment(event)
            del user_ocr_state[user_id]
            return
    
    # Inscription
    if user_id in user_conversation_state:
        state = user_conversation_state[user_id]
        text = event.message.message.strip()
        
        if state == 'awaiting_nom':
            update_user(user_id, {'nom': text})
            user_conversation_state[user_id] = 'awaiting_prenom'
            await event.respond("""
✨ **Parfait !** ✨

**Étape 2/3** 🚀
*Et votre prénom ?*
""")
            return
        
        elif state == 'awaiting_prenom':
            update_user(user_id, {'prenom': text})
            user_conversation_state[user_id] = 'awaiting_pays'
            await event.respond("""
🌟 **Excellent !** 🌟

**Étape 3/3** 🚀
*De quel pays êtes-vous ?*
""")
            return
        
        elif state == 'awaiting_pays':
            update_user(user_id, {
                'pays': text, 'registered': True,
                'trial_started': datetime.now().isoformat()
            })
            del user_conversation_state[user_id]
            
            await event.respond("""
🎊 **INSCRIPTION RÉUSSIE !** 🎊

✅ *Votre compte est créé !*
🎁 *15 minutes gratuites activées !*

⚡ *Votre lien VIP arrive...*
""")
            await add_user_to_vip(user_id, trial_config['duration_minutes'], is_trial=True)
            return
    
    # Photo hors contexte
    if event.message.photo:
        await event.respond("""
📸 **OUPS !** 

💡 *Pour payer, utilisez d'abord :*
👉 `/payer`

🎯 *Ensuite cliquez sur "J'AI DÉJÀ PAYÉ"*
""")

async def process_ocr_payment(event):
    """Traite la capture d'écran OCR"""
    user_id = event.sender_id
    username = event.sender.username or f"User_{user_id}"
    
    # Télécharger l'image
    photo_bytes = BytesIO()
    await event.client.download_media(event.message.photo, photo_bytes)
    photo_bytes.seek(0)
    
    # Analyse OCR
    await event.respond("🔍 *Analyse en cours...*")
    texte = await ocr_space_api(photo_bytes)
    
    if not texte.strip():
        await event.respond("""
❌ **LECTURE IMPOSSIBLE**

📝 *Nous ne pouvons pas lire votre capture.*

💡 **Conseils :**
• Envoyez une image plus claire
• Assurez-vous que tout le reçu est visible
• Évitez les reflets

🔄 *Réessayez avec /payer*
""")
        return
    
    # Extraction des données
    montant = extraire_montant(texte)
    reference = extraire_reference(texte)
    facture = extraire_numero_facture(texte)
    
    if not montant:
        await event.respond("""
❌ **MONTANT NON TROUVÉ**

💰 *Nous ne détectons pas le montant FCFA.*

📝 *Vérifiez que :*
• Le montant est bien visible
• "FCFA" apparaît sur le reçu
• L'image n'est pas floue

🔄 *Réessayez avec /payer*
""")
        return
    
    # Vérification anti-doublon
    doublons = verifier_doublon(reference, facture)
    
    if doublons:
        await event.respond(f"""
🛑 **ALERTE SÉCURITÉ** 🛑

🔴 **REÇU DÉJÀ UTILISÉ !** 🔴

❌ *Ce paiement a déjà été enregistré.*

📋 **Détection :**
{chr(10).join(f"• {d}" for d in doublons)}

💰 Montant détecté : {montant:.0f} FCFA

⛔ **Paiement REFUSÉ**

🔄 *Effectuez un NOUVEAU paiement valide :*
👉 `/payer`
""")
        return
    
    # ✅ Paiement conforme - Calcul et validation
    minutes = calculer_minutes(montant)
    duree = formater_duree(minutes)
    
    # Sauvegarder dans OCR data
    if str(user_id) not in ocr_data["paiements"]:
        ocr_data["paiements"][str(user_id)] = []
    
    paiement_info = {
        "date": datetime.now().isoformat(),
        "montant": montant,
        "minutes_attribuees": minutes,
        "reference": reference or "Non détectée",
        "facture": facture or "Non détectée",
        "username": username
    }
    
    ocr_data["paiements"][str(user_id)].append(paiement_info)
    
    if reference:
        ocr_data["references"][reference] = str(user_id)
    if facture:
        ocr_data["factures"][facture] = str(user_id)
    
    # Sauvegarder dans validations
    validated_payments[str(user_id)] = paiement_info
    save_all_configs()
    
    # Message de confirmation avec émotion
    vip_link = get_vip_channel_link()
    
    msg = await event.respond(f"""
╔════════════════════════════════════╗
║     ✅ PAIEMENT CONFORME ✅       ║
╚════════════════════════════════════╝

🤖 **L'assistant de Sossou Kouamé confirme votre paiement conforme en attendant la confirmation visa administrateur**

💰 **Montant détecté :** {montant:.0f} FCFA
⏱️ **Temps calculé :** {minutes:,} minutes ({duree})
🧾 **Facture :** `{facture or 'N/A'}`
🔑 **Référence :** `{reference or 'N/A'}`

⚡ **VALIDATION INSTANTANÉE !**

🔗 **VOTRE LIEN VIP :**
{vip_link}

🚨 **CLIQUEZ IMMÉDIATEMENT !** 🚨

💎 *Bienvenue dans l'expérience VIP...*
""")
    
    # Supprimer le message après 30 secondes
    asyncio.create_task(delete_message_after_delay(user_id, msg.id, 30))
    
    # Activer le VIP
    payment_data = {
        'montant': montant,
        'facture': facture or 'N/A',
        'reference': reference or 'N/A'
    }
    
    await extend_or_add_vip(user_id, minutes, payment_data)

# ============================================================
# SERVEUR WEB
# ============================================================

async def web_index(request):
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>🎰 Bot VIP Sossou Kouamé</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            padding: 50px;
            min-height: 100vh;
            margin: 0;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 3em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .subtitle {{
            font-size: 1.2em;
            opacity: 0.9;
            margin-bottom: 40px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 40px 0;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            padding: 30px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.2);
            transition: transform 0.3s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        .stat-number {{
            font-size: 3em;
            font-weight: bold;
            color: #ffd700;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        .stat-label {{
            font-size: 1.1em;
            margin-top: 10px;
            opacity: 0.9;
        }}
        .info-bar {{
            background: rgba(0,0,0,0.2);
            padding: 20px;
            border-radius: 15px;
            margin-top: 30px;
            font-size: 1.1em;
        }}
        .pulse {{
            animation: pulse 2s infinite;
            display: inline-block;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        .status-indicator {{
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #00ff88;
            border-radius: 50%;
            margin-right: 10px;
            animation: blink 1s infinite;
        }}
        @keyframes blink {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎰 <span class="pulse">Bot VIP</span></h1>
        <div class="subtitle">Système exclusif de Sossou Kouamé</div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{len([u for u in users_data if int(u) != ADMIN_ID])}</div>
                <div class="stat-label">👥 Membres</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{sum(len(v) for v in ocr_data.get('paiements', {}).values())}</div>
                <div class="stat-label">💰 Paiements</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(validated_payments)}</div>
                <div class="stat-label">✅ Validations</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(ocr_data.get('references', {}))}</div>
                <div class="stat-label">🔍 Anti-Doublons</div>
            </div>
        </div>
        
        <div class="info-bar">
            <span class="status-indicator"></span>
            <strong>🟢 SYSTÈME OPÉRATIONNEL</strong><br><br>
            💳 Tarif : {BASE_MONTANT} FCFA = {BASE_MINUTES} min (24h)<br>
            🤖 Validation OCR automatique<br>
            ⚡ Lien VIP 30 secondes<br><br>
            <small>🔄 Mis à jour : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</small>
        </div>
    </div>
</body>
</html>
"""
    return web.Response(text=html, content_type='text/html')

async def start_web():
    app = web.Application()
    app.router.add_get('/', web_index)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()

# ============================================================
# DÉMARRAGE
# ============================================================

async def main():
    load_all_configs()
    await start_web()
    await client.start(bot_token=BOT_TOKEN)
    
    logger.info("=" * 60)
    logger.info("🚀 BOT VIP SOSSOU KOUAMÉ DÉMARRÉ")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    logger.info(f"⭐ VIP: {get_vip_channel_id()}")
    logger.info(f"💳 Tarif: {BASE_MONTANT} FCFA = {BASE_MINUTES} min")
    logger.info(f"📁 Data dir: {DATA_DIR}")
    logger.info(f"🌐 Port: {PORT}")
    logger.info("=" * 60)
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
