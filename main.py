#!/usr/bin/env python3
"""
Main entry point - Bot Telegram + Serveur Web
Ce fichier ouvre le port et gère toute l'application
"""

import asyncio
import random
import signal
import sys
from contextlib import suppress

from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext

# Import configuration
import config
from strategies import StrategyManager
from utils import get_latest_results, update_history

# ==================== VARIABLES GLOBALES ====================
bot_running = False
prediction_history = []
history = {}
games_to_skip = 0
skipped_games = []
prediction_task = None
strategy_manager = StrategyManager()

# ==================== SERVEUR WEB (OUVRE LE PORT) ====================

async def health_check(request):
    """Endpoint de vérification de santé pour Render"""
    return web.json_response({
        "status": "alive",
        "bot_running": bot_running,
        "port": config.PORT,
        "predictions_count": len(prediction_history)
    })

async def root_handler(request):
    """Page d'accueil"""
    html = f"""
    <html>
        <head><title>Prediction Bot</title></head>
        <body>
            <h1>🤖 Prediction Bot is Running!</h1>
            <p>Status: {'✅ Active' if bot_running else '⏸️ Paused'}</p>
            <p>Port: {config.PORT}</p>
            <p>Channel: {config.CHANNEL_ID}</p>
            <p>Active Predictions: {len(prediction_history)}</p>
        </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def start_web_server():
    """Démarre le serveur web sur le port configuré"""
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    
    print(f"🌐 [WEB] Serveur démarré sur http://{config.HOST}:{config.PORT}")
    print(f"🌐 [WEB] Health check: http://{config.HOST}:{config.PORT}/health")
    
    return runner

# ==================== LOGIQUE DU BOT ====================

async def check_predictions(context: CallbackContext):
    """Boucle principale de vérification des prédictions"""
    global bot_running, history, games_to_skip, skipped_games
    
    try:
        while bot_running:
            await asyncio.sleep(config.CHECK_INTERVAL)
            print("[🔍] Vérification des résultats...")
            
            # Récupérer les résultats API
            results = get_latest_results()
            if not results:
                print("[⚠️] Aucun résultat API")
                continue
            
            # Mettre à jour l'historique
            history = update_history(results, history)
            
            # Gérer les jeux à sauter
            if skipped_games:
                all_finished = all(
                    game_number in history and history[game_number]["is_finished"]
                    for game_number in skipped_games
                )
                if not all_finished:
                    print(f"[⏭️] Jeux à sauter: {skipped_games}")
                    continue
                skipped_games = []
                print("[✅] Fin du saut, reprise normale")
            
            # Générer nouvelle prédiction si nécessaire
            if not prediction_history and not skipped_games:
                await generate_and_send_prediction(context, results)
            
            # Vérifier les prédictions en cours
            await verify_predictions(context, results)
            
    except asyncio.CancelledError:
        print("[🛑] Tâche de prédiction annulée")
        raise

async def generate_and_send_prediction(context: CallbackContext, results: list):
    """Génère et envoie une nouvelle prédiction"""
    prediction = strategy_manager.generate_prediction(history)
    if not prediction:
        return
    
    prediction_text = config.get_translation("prediction").format(
        symbol=prediction["symbol"],
        game_number=prediction["game_number"]
    )
    
    for chat_id in config.get_chat_ids():
        try:
            print(f"[📤] Envoi prédiction: {prediction['symbol']} -> {chat_id}")
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=prediction_text,
                parse_mode="HTML"
            )
            prediction_history.append({
                "message_id": sent.message_id,
                "chat_id": chat_id,
                "data": prediction
            })
            await asyncio.sleep(config.MESSAGE_DELAY)
        except Exception as e:
            print(f"[❌] Erreur envoi: {e}")

async def verify_predictions(context: CallbackContext, results: list):
    """Vérifie si les prédictions sont gagnantes ou perdantes"""
    global games_to_skip, skipped_games
    
    for prediction in prediction_history[:]:
        if prediction["data"]["status"] is not None:
            continue
        
        pred_number = prediction["data"]["number"]
        initial_game = prediction["data"]["game_number"]
        
        # Jeux pertinents (initial + rattrapages)
        relevant = [g for g in results if initial_game <= g["game_number"] <= initial_game + config.MAX_RETRIES]
        
        # Vérifier victoire
        for result in relevant:
            player_cards = result["player_cards"]
            if any(card["S"] == pred_number for card in player_cards):
                prediction["data"]["status"] = "✅"
                prediction["data"]["result_game"] = result["game_number"]
                print(f"[🎉] Prédiction gagnante au jeu #{result['game_number']}")
                break
        
        # Si pas de victoire et tous jeux terminés = échec
        if prediction["data"]["status"] is None:
            if all(g["is_finished"] for g in relevant):
                prediction["data"]["status"] = "❌"
                print(f"[💥] Prédiction perdue")
        
        # Mettre à jour le message si résolu
        if prediction["data"]["status"] is not None:
            await update_prediction_message(context, prediction)

async def update_prediction_message(context: CallbackContext, prediction: dict):
    """Met à jour le message Telegram avec le résultat"""
    global games_to_skip, skipped_games
    
    status = prediction["data"]["status"]
    result_game = prediction["data"]["result_game"]
    initial_game = prediction["data"]["game_number"]
    index = ""
    
    if status == "✅":
        if result_game == initial_game:
            index = "0️⃣"
            games_to_skip = random.randint(config.SKIP_AFTER_WIN_MIN, config.SKIP_AFTER_WIN_MAX)
        elif result_game == initial_game + 1:
            index = "1️⃣"
            games_to_skip = random.randint(config.SKIP_AFTER_WIN_MIN, config.SKIP_AFTER_WIN_MAX)
        elif result_game == initial_game + 2:
            index = "2️⃣"
            games_to_skip = random.randint(config.SKIP_AFTER_WIN_MIN, config.SKIP_AFTER_WIN_MAX)
        
        skipped_games = [result_game + i for i in range(1, games_to_skip + 1)]
        print(f"[⏭️] Prochains jeux à sauter: {skipped_games}")
    
    message = config.get_translation("prediction").format(
        symbol=prediction["data"]["symbol"],
        game_number=prediction["data"]["game_number"]
    ) + f"{status}{index}"
    
    try:
        await context.bot.edit_message_text(
            chat_id=prediction["chat_id"],
            message_id=prediction["message_id"],
            text=message,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[❌] Erreur mise à jour: {e}")
    
    prediction_history.remove(prediction)

# ==================== COMMANDES TELEGRAM ====================

async def start_bot(update: Update, context: CallbackContext):
    """Commande /startbot"""
    global bot_running, prediction_task
    
    user_id = update.effective_user.id
    if user_id not in config.get_admin_ids():
        await update.message.reply_text(config.get_translation("no_permission"))
        return
    
    if bot_running:
        await update.message.reply_text(config.get_translation("bot_already_started"))
        return
    
    bot_running = True
    prediction_task = asyncio.create_task(check_predictions(context))
    await update.message.reply_text(config.get_translation("bot_started"))
    print(f"[🚀] Bot démarré par l'admin {user_id}")

async def stop_bot(update: Update, context: CallbackContext):
    """Commande /stopbot"""
    global bot_running, prediction_task
    
    user_id = update.effective_user.id
    if user_id not in config.get_admin_ids():
        await update.message.reply_text(config.get_translation("no_permission"))
        return
    
    if not bot_running:
        await update.message.reply_text(config.get_translation("bot_already_stopped"))
        return
    
    bot_running = False
    if prediction_task:
        prediction_task.cancel()
        with suppress(asyncio.CancelledError):
            await prediction_task
    
    await update.message.reply_text(config.get_translation("bot_stopped"))
    print(f"[🛑] Bot arrêté par l'admin {user_id}")

# ==================== GESTION DU SIGNAL ====================

def handle_shutdown(signum, frame):
    """Gestion propre de l'arrêt"""
    global bot_running
    print(f"\n[🛑] Signal {signum} reçu, arrêt en cours...")
    bot_running = False
    sys.exit(0)

# ==================== POINT D'ENTRÉE PRINCIPAL ====================

async def main():
    """Fonction principale - Démarre le serveur ET le bot"""
    print("=" * 50)
    print("🤖 PREDICTION BOT - Démarrage")
    print("=" * 50)
    print(f"📡 Port: {config.PORT}")
    print(f"💬 Canal: {config.CHANNEL_ID}")
    print(f"👥 Admins: {config.get_admin_ids()}")
    print(f"🌍 Langue: {config.DEFAULT_LANGUAGE}")
    print("=" * 50)
    
    # 1. Démarrer le serveur web (OUVRE LE PORT)
    web_runner = await start_web_server()
    
    # 2. Configurer le bot Telegram
    application = ApplicationBuilder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler("startbot", start_bot))
    application.add_handler(CommandHandler("stopbot", stop_bot))
    
    # 3. Démarrer le bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("[✅] Bot Telegram prêt!")
    print("[💡] Envoyez /startbot dans Telegram pour démarrer les prédictions")
    
    # 4. Garder l'application vivante
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        print("\n[🛑] Arrêt demandé...")
    finally:
        print("[🧹] Nettoyage...")
        await application.stop()
        await web_runner.cleanup()
        print("[👋] Au revoir!")

if __name__ == "__main__":
    # Gestion des signaux
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Lancer l'application
    asyncio.run(main())
