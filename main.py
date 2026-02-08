#!/usr/bin/env python3
"""
Main entry point - Bot Telegram + Serveur Web (Webhook mode pour Render)
URL: https://url-baccara.onrender.com
"""

import asyncio
import random
import signal
import sys
from contextlib import suppress

from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import config
from strategies import StrategyManager
from utils import get_latest_results, update_history

# ==================== VARIABLES GLOBALES ====================
bot_running = False
prediction_history = []
history = {}
games_to_skip = 0
skipped_games = []
strategy_manager = StrategyManager()
application = None

# URL de votre service Render
WEBHOOK_URL = "https://url-baccara.onrender.com"
WEBHOOK_PATH = "/webhook"

# ==================== SERVEUR WEB & WEBHOOK ====================

async def health_check(request):
    """Health check pour Render"""
    return web.json_response({
        "status": "alive",
        "bot_running": bot_running,
        "predictions": len(prediction_history)
    })

async def root_handler(request):
    """Page d'accueil"""
    html = f"""
    <html>
        <head><title>Baccara Bot</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h1>🎰 Baccara Prediction Bot</h1>
            <p><strong>Status:</strong> {'✅ Running' if bot_running else '⏸️ Stopped'}</p>
            <p><strong>Predictions active:</strong> {len(prediction_history)}</p>
            <p>Send <code>/startbot</code> in Telegram to start</p>
        </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def webhook_handler(request):
    """Gère les mises à jour Telegram via webhook"""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response(status=200)

async def start_web_server():
    """Démarre le serveur web avec webhook"""
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_check)
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    
    print(f"🌐 Web server: http://{config.HOST}:{config.PORT}")
    print(f"🔗 Webhook: {WEBHOOK_URL}{WEBHOOK_PATH}")
    return runner

# ==================== LOGIQUE PRÉDICTIONS ====================

async def prediction_loop():
    """Boucle de prédictions en arrière-plan"""
    global bot_running, history, games_to_skip, skipped_games
    
    while True:
        if not bot_running:
            await asyncio.sleep(1)
            continue
            
        await asyncio.sleep(config.CHECK_INTERVAL)
        
        results = get_latest_results()
        if not results:
            continue
        
        history = update_history(results, history)
        
        # Gérer les sauts
        if skipped_games:
            all_finished = all(
                game_number in history and history[game_number]["is_finished"]
                for game_number in skipped_games
            )
            if not all_finished:
                continue
            skipped_games = []
            print("[✅] Skip ended")
        
        # Nouvelle prédiction
        if not prediction_history and not skipped_games:
            await generate_prediction()
        
        # Vérifier prédictions
        await verify_predictions(results)

async def generate_prediction():
    """Génère et envoie une prédiction"""
    prediction = strategy_manager.generate_prediction(history)
    if not prediction:
        return
    
    text = config.get_translation("prediction").format(
        symbol=prediction["symbol"],
        game_number=prediction["game_number"]
    )
    
    for chat_id in config.get_chat_ids():
        try:
            message = await application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML"
            )
            prediction_history.append({
                "message_id": message.message_id,
                "chat_id": chat_id,
                "data": prediction
            })
            print(f"[📤] Sent: {prediction['symbol']}")
            await asyncio.sleep(config.MESSAGE_DELAY)
        except Exception as e:
            print(f"[❌] Send error: {e}")

async def verify_predictions(results):
    """Vérifie les prédictions en cours"""
    global games_to_skip, skipped_games
    
    for pred in prediction_history[:]:
        if pred["data"]["status"] is not None:
            continue
        
        pred_num = pred["data"]["number"]
        init_game = pred["data"]["game_number"]
        relevant = [g for g in results if init_game <= g["game_number"] <= init_game + config.MAX_RETRIES]
        
        # Check victoire
        for result in relevant:
            if any(card["S"] == pred_num for card in result["player_cards"]):
                pred["data"]["status"] = "✅"
                pred["data"]["result_game"] = result["game_number"]
                print(f"[🎉] Win at #{result['game_number']}")
                break
        
        # Check défaite
        if pred["data"]["status"] is None:
            if all(g["is_finished"] for g in relevant):
                pred["data"]["status"] = "❌"
                print("[💥] Loss")
        
        # Mettre à jour message
        if pred["data"]["status"] is not None:
            await update_message(pred)

async def update_message(pred):
    """Met à jour le message Telegram"""
    global games_to_skip, skipped_games
    
    status = pred["data"]["status"]
    result_game = pred["data"]["result_game"]
    init_game = pred["data"]["game_number"]
    index = ""
    
    if status == "✅":
        if result_game == init_game:
            index = "0️⃣"
        elif result_game == init_game + 1:
            index = "1️⃣"
        elif result_game == init_game + 2:
            index = "2️⃣"
        
        games_to_skip = random.randint(config.SKIP_AFTER_WIN_MIN, config.SKIP_AFTER_WIN_MAX)
        skipped_games = [result_game + i for i in range(1, games_to_skip + 1)]
        print(f"[⏭️] Skip: {skipped_games}")
    
    message = config.get_translation("prediction").format(
        symbol=pred["data"]["symbol"],
        game_number=pred["data"]["game_number"]
    ) + f"{status}{index}"
    
    try:
        await application.bot.edit_message_text(
            chat_id=pred["chat_id"],
            message_id=pred["message_id"],
            text=message,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[❌] Edit error: {e}")
    
    prediction_history.remove(pred)

# ==================== COMMANDES TELEGRAM ====================

async def start_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /startbot"""
    global bot_running
    
    user_id = update.effective_user.id
    if user_id not in config.get_admin_ids():
        await update.message.reply_text("⛔ No permission")
        return
    
    if bot_running:
        await update.message.reply_text("❌ Already running")
        return
    
    bot_running = True
    await update.message.reply_text("✅ Bot started! Predictions active.")
    print(f"[🚀] Started by {user_id}")

async def stop_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /stopbot"""
    global bot_running
    
    user_id = update.effective_user.id
    if user_id not in config.get_admin_ids():
        await update.message.reply_text("⛔ No permission")
        return
    
    if not bot_running:
        await update.message.reply_text("❌ Already stopped")
        return
    
    bot_running = False
    await update.message.reply_text("🛑 Bot stopped!")
    print(f"[🛑] Stopped by {user_id}")

# ==================== DÉMARRAGE ====================

async def setup_bot():
    """Configure le bot avec webhook"""
    global application
    
    # Créer l'application
    application = ApplicationBuilder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler("startbot", start_bot_cmd))
    application.add_handler(CommandHandler("stopbot", stop_bot_cmd))
    
    # Initialiser
    await application.initialize()
    await application.start()
    
    # Configurer le webhook
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await application.bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook set: {webhook_url}")
    
    return application

async def main():
    print("=" * 50)
    print("🎰 BACCARA BOT - Starting")
    print(f"🌐 URL: {WEBHOOK_URL}")
    print("=" * 50)
    
    # 1. Démarrer le serveur web (d'abord pour que Render détecte le port)
    web_runner = await start_web_server()
    
    # 2. Configurer le bot avec webhook
    await setup_bot()
    
    # 3. Démarrer la boucle de prédictions
    asyncio.create_task(prediction_loop())
    print("✅ Prediction loop started")
    
    print("=" * 50)
    print("🚀 BOT READY!")
    print("Send /startbot in Telegram")
    print("=" * 50)
    
    # Garder vivant
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print("\n[🛑] Shutting down...")
    finally:
        await application.stop()
        await web_runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
