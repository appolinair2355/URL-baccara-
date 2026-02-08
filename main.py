import os
import asyncio
import re
import logging
import sys
import json
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.channels import EditBannedRequest, GetParticipantsRequest
from telethon.tl.types import ChatBannedRights, ChannelParticipantsSearch
from telethon import functions, types
from telethon.errors import UserNotParticipantError, ChatIdInvalidError
from aiohttp import web
from PIL import Image
from io import BytesIO
import requests
import base64

# ============================================================
# CONFIGURATION
# ============================================================

API_ID = int(os.getenv('API_ID', '29177661'))
API_HASH = os.getenv('API_HASH', 'a8639172fa8d35dbfd8ea46286d349ab')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8442253971:AAEisYucgZ49Ej2b-mK9_6DhNrqh9WOc_XU')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1190237801'))

PORT = int(os.getenv('PORT', '10000'))
RENDER_DEPLOYMENT = os.getenv('RENDER_DEPLOYMENT', 'true').lower() == 'true'
TELEGRAM_SESSION = os.getenv('TELEGRAM_SESSION', '')

DATA_DIR = os.getenv('DATA_DIR', './data')

try:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        print(f"✅ Dossier créé : {DATA_DIR}")
except PermissionError:
    print(f"⚠️ Permission refusée pour {DATA_DIR}, utilisation de ./data")
    DATA_DIR = './data'
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception as e:
    print(f"⚠️ Erreur : {e}, utilisation de ./data")
    DATA_DIR = './data'
    os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users_data.json')
CHANNELS_CONFIG_FILE = os.path.join(DATA_DIR, 'channels_config.json')
TRIAL_CONFIG_FILE = os.path.join(DATA_DIR, 'trial_config.json')
OCR_DATA_FILE = os.path.join(DATA_DIR, 'ocr_data.json')
VALIDATED_PAYMENTS_FILE = os.path.join(DATA_DIR, 'validated_payments.json')
EXPIRED_NOTIFIED_FILE = os.path.join(DATA_DIR, 'expired_notified.json')

OCR_API_KEY = os.getenv('OCR_API_KEY', 'K86527928888957')
PAYMENT_LINK = os.getenv('PAYMENT_LINK', 'https://my.moneyfusion.net/6977f7502181d4ebf722398d')
BASE_MONTANT = int(os.getenv('BASE_MONTANT', '205'))
BASE_MINUTES = int(os.getenv('BASE_MINUTES', '1440'))

DEFAULT_SOURCE_CHANNEL_ID = int(os.getenv('DEFAULT_SOURCE_CHANNEL_ID', '-1002682552255'))
DEFAULT_PREDICTION_CHANNEL_ID = int(os.getenv('DEFAULT_PREDICTION_CHANNEL_ID', '-1003329818758'))
DEFAULT_VIP_CHANNEL_ID = int(os.getenv('DEFAULT_VIP_CHANNEL_ID', '-1003329818758'))
DEFAULT_VIP_CHANNEL_LINK = os.getenv('DEFAULT_VIP_CHANNEL_LINK', 'https://t.me/+s3y7GejUVHU0YjE0')

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

if not API_ID or API_ID == 0:
    logger.error("❌ API_ID manquant")
    exit(1)
if not API_HASH:
    logger.error("❌ API_HASH manquant")
    exit(1)
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN manquant")
    exit(1)

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

trial_config = {'duration_minutes': DEFAULT_TRIAL_DURATION}
users_data = {}
ocr_data = {"paiements": {}, "references": {}, "factures": {}}
validated_payments = {}
expired_notified = {}

user_conversation_state = {}
user_ocr_state = {}
watch_state = {}
pending_removals = {}

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
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur sauvegarde {file_path}: {e}")

def load_all_configs():
    global channels_config, trial_config, users_data, ocr_data, validated_payments, expired_notified
    channels_config.update(load_json(CHANNELS_CONFIG_FILE, channels_config))
    trial_config.update(load_json(TRIAL_CONFIG_FILE, trial_config))
    users_data.update(load_json(USERS_FILE, {}))
    ocr_data.update(load_json(OCR_DATA_FILE, ocr_data))
    validated_payments.update(load_json(VALIDATED_PAYMENTS_FILE, {}))
    expired_notified.update(load_json(EXPIRED_NOTIFIED_FILE, {}))
    logger.info("✅ Configurations chargées")

def save_all_configs():
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    save_json(TRIAL_CONFIG_FILE, trial_config)
    save_json(USERS_FILE, users_data)
    save_json(OCR_DATA_FILE, ocr_data)
    save_json(VALIDATED_PAYMENTS_FILE, validated_payments)
    save_json(EXPIRED_NOTIFIED_FILE, expired_notified)

def get_vip_channel_id():
    return channels_config.get('vip_channel_id', DEFAULT_VIP_CHANNEL_ID)

def get_vip_channel_link():
    return channels_config.get('vip_channel_link', DEFAULT_VIP_CHANNEL_LINK)

def get_prediction_channel_id():
    return channels_config.get('prediction_channel_id', DEFAULT_PREDICTION_CHANNEL_ID)

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

def get_remaining_time(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return "∞ (Admin)"
    if is_user_subscribed(user_id):
        user = get_user(user_id)
        return format_time_remaining(user.get('subscription_end', ''))
    elif is_trial_active(user_id):
        user = get_user(user_id)
        trial_end = datetime.fromisoformat(user.get('trial_joined_at')) + timedelta(minutes=trial_config['duration_minutes'])
        remaining = int((trial_end - datetime.now()).total_seconds())
        return format_seconds(remaining)
    return "⛔ Expiré"

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

def format_seconds(seconds: int) -> str:
    if seconds <= 0:
        return "⛔ Expiré"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and hours == 0:
        parts.append(f"{secs}s")
    return " ".join(parts) if parts else "⏳ Quelques secondes"

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
# FONCTIONS DE RETRAIT DU CANAL (NOUVELLES FONCTIONS)
# ============================================================

async def get_channel_entity(channel_id: int):
    """
    Récupère l'entity d'un canal avec gestion d'erreur améliorée.
    Essaie d'abord get_input_entity, sinon get_entity.
    """
    try:
        entity = await client.get_input_entity(channel_id)
        return entity
    except Exception as e:
        logger.warning(f"get_input_entity a échoué pour {channel_id}: {e}")
        try:
            entity = await client.get_entity(channel_id)
            return entity
        except Exception as e2:
            logger.error(f"get_entity a aussi échoué pour {channel_id}: {e2}")
            raise e2

async def remove_user_from_channel(channel_id: int, user_id: int):
    """
    Retire un utilisateur du canal en utilisant kick_participant (méthode fiable)
    """
    try:
        entity = await get_channel_entity(channel_id)
        
        # Utiliser kick_participant (fonctionne pour les channels et megagroups)
        await client.kick_participant(entity, user_id)
        
        # Débannir immédiatement pour permettre de revenir plus tard (si réabonnement)
        await client(EditBannedRequest(
            channel=entity,
            participant=user_id,
            banned_rights=ChatBannedRights(until_date=None, view_messages=False)
        ))
        
        logger.info(f"✅ Utilisateur {user_id} retiré du canal {channel_id}")
        return True
        
    except UserNotParticipantError:
        logger.warning(f"⚠️ L'utilisateur {user_id} n'est pas membre du canal {channel_id}")
        return False
        
    except ChatIdInvalidError:
        logger.error(f"❌ ID de canal invalide: {channel_id}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du retrait de {user_id}: {e}")
        return False

async def ban_user_from_channel(channel_id: int, user_id: int):
    """
    Bannit définitivement un utilisateur du canal
    """
    try:
        entity = await get_channel_entity(channel_id)
        
        await client(EditBannedRequest(
            channel=entity,
            participant=user_id,
            banned_rights=ChatBannedRights(
                until_date=None,
                view_messages=True,
                send_messages=True,
                send_media=True,
                send_stickers=True,
                send_gifs=True,
                send_games=True,
                send_inline=True,
                embed_links=True
            )
        ))
        
        logger.info(f"🔨 Utilisateur {user_id} banni du canal {channel_id}")
        return True
        
    except UserNotParticipantError:
        logger.warning(f"⚠️ Utilisateur {user_id} non membre du canal {channel_id}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Erreur bannissement {user_id}: {e}")
        return False

# ============================================================
# FONCTIONS OCR
# ============================================================

async def ocr_space_api(image_bytes):
    url = "https://api.ocr.space/parse/image"
    payload = {'apikey': OCR_API_KEY, 'language': 'fre', 'isOverlayRequired': False}
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
# GESTION VIP - CORRIGÉE AVEC RETRAIT AUTO ET NOTIFICATION
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
        
        uid_str = str(user_id)
        if uid_str in expired_notified:
            del expired_notified[uid_str]
            save_json(EXPIRED_NOTIFIED_FILE, expired_notified)
        
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
        
        asyncio.create_task(auto_kick_and_notify(user_id, duration_minutes * 60))
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur ajout VIP {user_id}: {e}")
        return False

async def extend_or_add_vip(user_id: int, additional_minutes: int, payment_info: dict = None):
    try:
        user = get_user(user_id)
        now = datetime.now()
        
        uid_str = str(user_id)
        if uid_str in expired_notified:
            del expired_notified[uid_str]
            save_json(EXPIRED_NOTIFIED_FILE, expired_notified)
        
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
        asyncio.create_task(auto_kick_and_notify(user_id, remaining_seconds))
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur extend_or_add_vip {user_id}: {e}")
        await client.send_message(user_id, "❌ Erreur lors de l'activation. Contactez @Kouamappoloak")
        return False

async def auto_kick_and_notify(user_id: int, delay_seconds: int):
    """
    Attend l'expiration, retire des canaux, notifie user et admin
    """
    if user_id == ADMIN_ID:
        return
    
    logger.info(f"⏰ Programmation expulsion pour {user_id} dans {delay_seconds}s")
    
    await asyncio.sleep(delay_seconds)
    
    try:
        if is_user_subscribed(user_id) or is_trial_active(user_id):
            logger.info(f"✅ Utilisateur {user_id} a renouvelé, annulation expulsion")
            return
        
        user = get_user(user_id)
        uid_str = str(user_id)
        vip_id = get_vip_channel_id()
        pred_id = get_prediction_channel_id()
        
        already_notified = expired_notified.get(uid_str, False)
        
        # 1. RETIRER DU CANAL VIP
        vip_success = False
        try:
            vip_success = await remove_user_from_channel(vip_id, user_id)
            logger.info(f"{'✅' if vip_success else '❌'} Retrait VIP {user_id}")
        except Exception as e:
            logger.error(f"Erreur retrait VIP {user_id}: {e}")
        
        # 2. RETIRER DU CANAL PRÉDICTION (si différent)
        pred_success = False
        if pred_id != vip_id:
            try:
                pred_success = await remove_user_from_channel(pred_id, user_id)
                logger.info(f"{'✅' if pred_success else '❌'} Retrait Prédiction {user_id}")
            except Exception as e:
                logger.error(f"Erreur retrait Prédiction {user_id}: {e}")
        
        # 3. METTRE À JOUR LA BASE
        update_user(user_id, {
            'vip_expires_at': None,
            'subscription_end': None,
            'is_in_channel': False,
            'trial_used': True
        })
        
        # 4. NOTIFIER L'UTILISATEUR (seulement si pas déjà notifié)
        if not already_notified:
            try:
                await client.send_message(user_id, f"""
😢 **VOTRE ACCÈS EST TERMINÉ** 😢

⏰ *Votre abonnement VIP a expiré.*
{'✅ Vous avez été retiré automatiquement du canal.' if vip_success else '⚠️ Contactez l\'admin pour être retiré du canal.'}

💔 *Nous espérons que vous avez apprécié l'expérience !*

💎 **Vous voulez continuer l'aventure ?**

💳 **Renouvelez votre abonnement :**
👉 Tapez `/payer`

🌟 *Ne manquez pas les prochaines opportunités !*

📞 **Besoin d'aide ?** @Kouamappoloak
""")
            except Exception as e:
                logger.error(f"Erreur notification user {user_id}: {e}")
            
            expired_notified[uid_str] = {
                'date': datetime.now().isoformat(),
                'type': 'expired'
            }
            save_json(EXPIRED_NOTIFIED_FILE, expired_notified)
        
        # 5. NOTIFIER L'ADMIN
        notif_status = "🔔 Nouvelle expiration" if not already_notified else "📝 Déjà notifié précédemment"
        
        await client.send_message(ADMIN_ID, f"""
🚫 **UTILISATEUR EXPIRÉ {'ET RETIRÉ' if vip_success else '(RETRAIT ÉCHEC)'}**

{notif_status}

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
🌍 {user.get('pays', 'N/A')}

**Actions :**
{'✅' if vip_success else '❌'} Retrait canal VIP
{'✅' if pred_success else '❌'} Retrait canal Prédiction
✅ Base de données mise à jour
{'✅' if not already_notified else '⏭️'} Notification utilisateur

{'✅ Tout est automatique !' if vip_success else '⚠️ **Action manuelle requise :** Vérifiez le canal et retirez l\'utilisateur si nécessaire'}
""")
        
        logger.info(f"✅ Expiration traitée pour {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement expiration {user_id}: {e}")

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
➕ `/adduser` - Ajouter manuellement un utilisateur
🔍 `/scan` - Scanner canal VIP (tous les IDs)
🧹 `/scanretire` - Scanner et retirer non-inscrits
⏱️ `/monitor` - Surveillance active
👁️ `/watch` - Mode espion temps réel
⏫ `/extend ID durée` - Accorder du temps
🚫 `/retirer ID` - Expulser immédiatement
🗑️ `/remove ID` - Retirer du système (commande alternative)

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
`/adduser` - Ajouter un utilisateur manuellement
`/scan` - Scanner tous les membres du canal VIP
`/scanretire` - Scanner et retirer les non-inscrits
`/monitor` - Utilisateurs actifs uniquement
`/watch` - Surveillance automatique (30s)
`/stopwatch` - Arrêter surveillance
`/extend 123456 2h` - Ajouter 2 heures

**Contrôle absolu :**
`/retirer 123456` - Expulsion immédiate des canaux
`/remove 123456` - Retirer du système uniquement

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
4️⃣ Revenez et cliquez **J'AI DÉJÀ PAYÉ**
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
    """Affiche TOUS les utilisateurs avec ID, nom, pays, statut, temps"""
    if event.sender_id != ADMIN_ID:
        return
    
    global users_data
    users_data = load_json(USERS_FILE, {})
    
    if not users_data:
        await event.respond("📭 *Aucun utilisateur enregistré dans la base*")
        return
    
    all_users = []
    for uid_str, info in users_data.items():
        try:
            uid = int(uid_str)
            if uid == ADMIN_ID:
                continue
            
            if is_user_subscribed(uid):
                status = "🟢 ABONNÉ"
                time_remaining = format_time_remaining(info.get('subscription_end', ''))
            elif is_trial_active(uid):
                status = "🟡 ESSAI"
                trial_end = datetime.fromisoformat(info.get('trial_joined_at')) + timedelta(minutes=trial_config['duration_minutes'])
                remaining = int((trial_end - datetime.now()).total_seconds())
                time_remaining = format_seconds(remaining)
            else:
                status = "🔴 INACTIF"
                time_remaining = "⛔ Expiré"
            
            prenom = info.get('prenom') or 'N/A'
            nom = info.get('nom') or 'N/A'
            pays = info.get('pays') or 'N/A'
            full_name = f"{prenom} {nom}".strip()
            
            all_users.append({
                'uid': uid,
                'name': full_name,
                'pays': pays,
                'status': status,
                'time': time_remaining,
                'total': info.get('total_time_added', 0),
                'registered': info.get('registered', False)
            })
        except Exception as e:
            logger.error(f"Erreur traitement user {uid_str}: {e}")
            continue
    
    if not all_users:
        await event.respond("📭 *Aucun utilisateur trouvé dans la base*")
        return
    
    all_users.sort(key=lambda x: (0 if 'ABONNÉ' in x['status'] else 1 if 'ESSAI' in x['status'] else 2, x['name']))
    
    total = len(all_users)
    for i in range(0, total, 5):
        chunk = all_users[i:i+5]
        
        lines = [f"📋 **UTILISATEURS ({i+1}-{min(i+len(chunk), total)}/{total})**\n"]
        
        for u in chunk:
            lines.append(f"""
{'─' * 45}
🆔 **ID :** `{u['uid']}`
👤 **Nom :** {u['name']}
🌍 **Pays :** {u['pays']}
📊 **Statut :** {u['status']}
⏳ **Temps restant :** {u['time']}
📈 **Total cumulé :** {u['total']:,} min
{'─' * 45}""")
        
        await event.respond("\n".join(lines))
        await asyncio.sleep(0.3)

@client.on(events.NewMessage(pattern=r'^/adduser(\s+.+)?$'))
async def cmd_adduser(event):
    """Ajoute manuellement un utilisateur à la base"""
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 5:
        await event.respond("""
➕ **AJOUTER UN UTILISATEUR**

**Usage :** `/adduser ID NOM PRENOM PAYS [DUREE]`

**Exemples :**
• `/adduser 123456789 KOUAME SOSSOU "COTE D'IVOIRE"` → Ajoute sans abonnement
• `/adduser 123456789 KOUAME SOSSOU "COTE D'IVOIRE" 1440` → Ajoute avec 24h

**Paramètres :**
• `ID` : ID Telegram de l'utilisateur (chiffres)
• `NOM` : Nom de famille
• `PRENOM` : Prénom
• `PAYS` : Pays (mettre entre guillemets si espace)
• `DUREE` : Optionnel, minutes d'abonnement (ex: 1440 = 24h)

💡 *L'utilisateur sera enregistré mais devra payer pour activer son accès (sauf si durée précisée)*
""")
        return
    
    try:
        target_id = int(parts[1])
        nom = parts[2]
        prenom = parts[3]
        pays = parts[4]
        duree = int(parts[5]) if len(parts) > 5 else 0
        
        uid_str = str(target_id)
        
        if uid_str in users_data and users_data[uid_str].get('registered'):
            await event.respond(f"""
⚠️ **UTILISATEUR EXISTANT**

🆔 `{target_id}` est déjà dans la base.

💡 Utilisez `/extend {target_id} 60` pour ajouter du temps.
""")
            return
        
        now = datetime.now()
        user_data = {
            'registered': True,
            'nom': nom,
            'prenom': prenom,
            'pays': pays,
            'trial_used': duree > 0,
            'total_time_added': duree,
            'added_manually': True,
            'added_date': now.isoformat()
        }
        
        if duree > 0:
            expires_at = now + timedelta(minutes=duree)
            user_data['subscription_end'] = expires_at.isoformat()
            user_data['vip_expires_at'] = expires_at.isoformat()
            user_data['is_in_channel'] = True
        
        update_user(target_id, user_data)
        
        if duree > 0:
            time_str = format_time_remaining(user_data['subscription_end'])
            await event.respond(f"""
✅ **UTILISATEUR AJOUTÉ ET ACTIVÉ**

🆔 **ID :** `{target_id}`
👤 **Nom :** {prenom} {nom}
🌍 **Pays :** {pays}
⏱️ **Durée :** {duree} minutes ({time_str})
📅 **Expire le :** {expires_at.strftime('%d/%m/%Y à %H:%M')}

🔗 **Lien VIP envoyé automatiquement à l'utilisateur**
""")
            await add_user_to_vip(target_id, duree, is_trial=False)
        else:
            await event.respond(f"""
✅ **UTILISATEUR AJOUTÉ**

🆔 **ID :** `{target_id}`
👤 **Nom :** {prenom} {nom}
🌍 **Pays :** {pays}
📊 **Statut :** Enregistré (sans abonnement)

💡 L'utilisateur doit utiliser `/payer` pour activer son accès.
""")
        
    except ValueError as e:
        await event.respond(f"❌ **Erreur de format :** `{e}`\n\nVérifiez que l'ID est un nombre.")
    except Exception as e:
        await event.respond(f"❌ **Erreur :** `{e}`")

@client.on(events.NewMessage(pattern='/scan'))
async def cmd_scan(event):
    """Scanne le canal VIP et affiche TOUS les membres"""
    if event.sender_id != ADMIN_ID:
        return
    
    await event.respond("🔍 **SCAN EN COURS...**\n\n⏳ Récupération des membres du canal VIP...")
    
    try:
        vip_id = get_vip_channel_id()
        
        if not vip_id or vip_id == 0:
            await event.respond("❌ **ID du canal VIP non configuré**\n\nUtilisez: `/setvipid -100XXXXXXXXXX`")
            return
        
        logger.info(f"Scan du canal: {vip_id}")
        
        entity = await get_channel_entity(vip_id)
        
        participants = []
        async for user in client.iter_participants(entity):
            if user.id == ADMIN_ID:
                continue
            participants.append({
                'id': user.id,
                'username': user.username or 'N/A',
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'full_name': f"{user.first_name or ''} {user.last_name or ''}".strip() or 'Anonyme'
            })
        
        if not participants:
            await event.respond("📭 *Aucun membre trouvé dans le canal VIP*")
            return
        
        inscrits = []
        non_inscrits = []
        expires_soon = []
        
        for p in participants:
            uid_str = str(p['id'])
            if uid_str in users_data:
                user_info = users_data[uid_str]
                if is_user_subscribed(p['id']):
                    time_left = format_time_remaining(user_info.get('subscription_end', ''))
                    inscrits.append({**p, 'time': time_left, 'status': '✅ Actif'})
                elif is_trial_active(p['id']):
                    time_left = format_time_remaining(user_info.get('trial_joined_at', ''))
                    inscrits.append({**p, 'time': time_left, 'status': '🎁 Essai'})
                else:
                    expires_soon.append({**p, 'status': '⛔ Expiré'})
            else:
                non_inscrits.append(p)
        
        summary = f"""
📊 **RÉSULTAT DU SCAN**

👥 **Total membres dans le canal :** {len(participants)}

✅ **Inscrits actifs :** {len([x for x in inscrits if '✅' in x['status']])}
🎁 **En essai :** {len([x for x in inscrits if '🎁' in x['status']])}
⛔ **Inscrits mais expirés :** {len(expires_soon)}
🔴 **Non inscrits (intrus) :** {len(non_inscrits)}

💡 Utilisez `/scanretire` pour gérer les non-inscrits et expirés
"""
        await event.respond(summary)
        
        if expires_soon:
            lines = ["\n⛔ **INSCRITS MAIS EXPIRÉS (À RETIRER) :**\n"]
            for p in expires_soon[:10]:
                lines.append(f"🆔 `{p['id']}` | 👤 {p['full_name'][:20]} | `/retirer {p['id']}`")
            if len(expires_soon) > 10:
                lines.append(f"\n... et {len(expires_soon) - 10} autres expirés")
            await event.respond("\n".join(lines))
        
        if non_inscrits:
            lines = ["\n🔴 **MEMBRES NON INSCRITS (INTRUS) :**\n"]
            for p in non_inscrits[:10]:
                lines.append(f"🆔 `{p['id']}` | 👤 {p['full_name'][:20]} | @{p['username']} | `/retirer {p['id']}`")
            if len(non_inscrits) > 10:
                lines.append(f"\n... et {len(non_inscrits) - 10} autres intrus")
            await event.respond("\n".join(lines))
            
    except Exception as e:
        logger.error(f"Erreur scan: {e}")
        await event.respond(f"""
❌ **Erreur lors du scan :** `{e}`

🔧 **Solutions possibles :**
1. Vérifiez que le bot est bien administrateur du canal
2. Assurez-vous que le bot a rejoint le canal (pas juste admin)
3. Vérifiez l'ID avec `/showids`
4. Essayez de redémarrer le bot

💡 **ID actuel :** `{get_vip_channel_id()}`
""")

@client.on(events.NewMessage(pattern='/scanretire'))
async def cmd_scanretire(event):
    """Scanne et retire automatiquement les non-inscrits et expirés"""
    if event.sender_id != ADMIN_ID:
        return
    
    status_msg = await event.respond("🧹 **MODE NETTOYAGE INTELLIGENT**\n\n🔍 Analyse du canal VIP en cours...")
    
    try:
        vip_id = get_vip_channel_id()
        
        if not vip_id or vip_id == 0:
            await event.respond("❌ **ID du canal VIP non configuré**")
            return
        
        entity = await get_channel_entity(vip_id)
        
        membres_canal = []
        async for user in client.iter_participants(entity):
            if user.id == ADMIN_ID:
                continue
            membres_canal.append({
                'id': user.id,
                'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or 'Anonyme',
                'username': user.username or 'N/A'
            })
        
        if not membres_canal:
            await event.respond("📭 *Aucun membre dans le canal VIP*")
            return
        
        a_retirer = []
        a_conserver = []
        
        for membre in membres_canal:
            uid = membre['id']
            uid_str = str(uid)
            
            if uid_str not in users_data:
                membre['raison'] = 'Non inscrit'
                a_retirer.append(membre)
            else:
                if is_user_subscribed(uid) or is_trial_active(uid):
                    membre['raison'] = 'Actif'
                    a_conserver.append(membre)
                else:
                    membre['raison'] = 'Expiré'
                    a_retirer.append(membre)
        
        await status_msg.edit(f"""
🧹 **ANALYSE TERMINÉE**

👥 **Total dans le canal :** {len(membres_canal)}
✅ **À conserver :** {len(a_conserver)}
🚫 **À retirer :** {len(a_retirer)}

{'⚠️ **Aucun membre à retirer**' if not a_retirer else '🔄 **Début du nettoyage automatique...**'}
""")
        
        if not a_retirer:
            return
        
        retires = []
        echecs = []
        
        for membre in a_retirer:
            try:
                success = await remove_user_from_channel(vip_id, membre['id'])
                
                if success:
                    update_user(membre['id'], {
                        'vip_expires_at': None,
                        'subscription_end': None,
                        'is_in_channel': False
                    })
                    
                    if membre['raison'] == 'Expiré':
                        try:
                            await client.send_message(membre['id'], """
⛔ **VOTRE ACCÈS A EXPIRÉ** ⛔

*Vous avez été retiré du canal VIP car votre abonnement est terminé.*

💳 **Pour renouveler :**
👉 Tapez `/payer`

📞 **Besoin d'aide ?** @Kouamappoloak
""")
                        except:
                            pass
                    
                    retires.append(membre)
                else:
                    echecs.append(membre)
                    
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Erreur retrait {membre['id']}: {e}")
                echecs.append(membre)
        
        rapport = f"""
✅ **NETTOYAGE TERMINÉ**

🗑️ **Retirés :** {len(retires)}
❌ **Échecs :** {len(echecs)}

**Détails des retraits :**
"""
        for m in retires[:15]:
            rapport += f"\n• `{m['id']}` | {m['name'][:20]} | *{m['raison']}*"
        
        if len(retires) > 15:
            rapport += f"\n... et {len(retires) - 15} autres"
        
        if echecs:
            rapport += "\n\n**Échecs :**"
            for m in echecs[:5]:
                rapport += f"\n• `{m['id']}` | {m['name'][:20]}"
        
        await event.respond(rapport)
        
    except Exception as e:
        logger.error(f"Erreur scanretire: {e}")
        await event.respond(f"""
❌ **Erreur :** `{e}`

🔧 **Vérifiez :**
• Le bot est admin du canal
• L'ID est correct : `/showids`
• Le bot a accès au canal
""")

@client.on(events.NewMessage(pattern='/monitor'))
async def cmd_monitor(event):
    if event.sender_id != ADMIN_ID:
        return
    
    active = []
    for uid_str, info in users_data.items():
        try:
            uid = int(uid_str)
            if uid == ADMIN_ID:
                continue
            if is_user_subscribed(uid) or is_trial_active(uid):
                name = f"{info.get('prenom', '')} {info.get('nom', '')}".strip() or "Anonyme"
                active.append(f"🟢 `{uid}` | {name[:18]:<18} | {get_remaining_time(uid)}")
        except:
            continue
    
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
                try:
                    uid = int(uid_str)
                    if uid == ADMIN_ID:
                        continue
                    if is_user_subscribed(uid) or is_trial_active(uid):
                        count += 1
                        name = f"{info.get('prenom', '')} {info.get('nom', '')}".strip() or "Anon"
                        lines.append(f"🟢 `{uid}` | {name[:12]:<12} | {get_remaining_time(uid)}")
                except:
                    continue
            
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
        
        uid_str = str(target_id)
        if uid_str in expired_notified:
            del expired_notified[uid_str]
            save_json(EXPIRED_NOTIFIED_FILE, expired_notified)
        
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
        asyncio.create_task(auto_kick_and_notify(target_id, remaining_seconds))
        
    except ValueError:
        await event.respond("❌ *ID invalide*")
    except Exception as e:
        await event.respond(f"❌ *Erreur :* `{e}`")

@client.on(events.NewMessage(pattern=r'^/retirer(\s+\d+)?$'))
async def cmd_retirer(event):
    """Retire immédiatement un utilisateur des canaux"""
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 2:
        await event.respond("""
🚫 **EXPULSION IMMÉDIATE**

**Usage :** `/retirer ID_UTILISATEUR`

⚠️ *L'utilisateur sera immédiatement :*
• ❌ Expulsé du canal VIP
• 🚫 Retiré du canal prédiction (si différent)
• 📵 Accès révoqué dans la base

💡 Trouvez l'ID avec `/users` ou `/scan`
""")
        return
    
    try:
        target_id = int(parts[1])
        target_str = str(target_id)
        
        user = get_user(target_id)
        vip_id = get_vip_channel_id()
        pred_id = get_prediction_channel_id()
        
        results = []
        
        # 1. Retirer du canal VIP
        try:
            success = await remove_user_from_channel(vip_id, target_id)
            results.append(f"{'✅' if success else '❌'} Canal VIP")
        except Exception as e:
            results.append(f"❌ Canal VIP: {e}")
        
        # 2. Retirer du canal prédiction (si différent)
        if pred_id != vip_id:
            try:
                success = await remove_user_from_channel(pred_id, target_id)
                results.append(f"{'✅' if success else '❌'} Canal Prédiction")
            except Exception as e:
                results.append(f"❌ Canal Prédiction: {e}")
        
        # 3. Mettre à jour la base
        update_user(target_id, {
            'vip_expires_at': None,
            'subscription_end': None,
            'is_in_channel': False,
            'trial_used': True
        })
        
        # 4. Supprimer des paiements validés
        if target_str in validated_payments:
            del validated_payments[target_str]
            save_json(VALIDATED_PAYMENTS_FILE, validated_payments)
        
        # 5. Notifier l'utilisateur
        try:
            await client.send_message(target_id, """
⛔ **ACCÈS RÉVOQUÉ** ⛔

*Votre abonnement a été résilié par l'administrateur.*

📞 **Pour plus d'informations :**
@Kouamappoloak
""")
        except:
            pass
        
        await event.respond(f"""
✅ **EXPULSION RÉUSSIE**

🆔 `{target_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}

**Actions effectuées :**
{chr(10).join(results)}
🗑️ Base de données mise à jour
📨 Notification envoyée
""")
        
    except ValueError:
        await event.respond("❌ *ID invalide*")
    except Exception as e:
        await event.respond(f"❌ *Erreur :* `{e}`")

@client.on(events.NewMessage(pattern=r'^/remove(\s+\d+)?$'))
async def cmd_remove_user(event):
    """Retire un utilisateur du système (sans expulser des canaux)"""
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 2:
        await event.respond("""
🗑️ **RETIRER DU SYSTÈME**

**Usage :** `/remove ID_UTILISATEUR`

⚠️ *Cette commande supprime uniquement les données de l'utilisateur de la base, sans l'expulser des canaux.*

💡 Pour expulser des canaux, utilisez `/retirer ID`
""")
        return
    
    try:
        target_user_id = int(parts[1])
        target_str = str(target_user_id)
        
        user = get_user(target_user_id)
        
        # Retirer des données utilisateurs
        if target_str in users_data:
            del users_data[target_str]
            save_json(USERS_FILE, users_data)
        
        # Optionnel: Retirer des canaux aussi si vous voulez
        # await remove_user_from_channel(get_vip_channel_id(), target_user_id)
        
        await event.respond(f"""
✅ **UTILISATEUR RETIRÉ DU SYSTÈME**

🆔 `{target_user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}

🗑️ Données supprimées de la base.

💡 *L'utilisateur n'a pas été expulsé des canaux. Utilisez `/retirer {target_user_id}` pour l'expulser.*
""")
        logger.info(f"Admin a retiré l'utilisateur {target_user_id} du système")
        
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")

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
        try:
            user = get_user(int(uid))
            lines.append(f"""
🆔 `{uid}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
💰 {info.get('montant', 0):.0f} FCFA | ⏱️ {info.get('minutes', 0)} min
📅 {info.get('date', 'N/A')[:10]}
""")
        except:
            lines.append(f"🆔 `{uid}` - Erreur chargement")
    
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
    
    photo_bytes = BytesIO()
    await event.client.download_media(event.message.photo, photo_bytes)
    photo_bytes.seek(0)
    
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
    
    minutes = calculer_minutes(montant)
    duree = formater_duree(minutes)
    
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
    
    validated_payments[str(user_id)] = paiement_info
    save_all_configs()
    
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
    
    asyncio.create_task(delete_message_after_delay(user_id, msg.id, 30))
    
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
