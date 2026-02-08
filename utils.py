import requests
import config

def get_latest_results():
    try:
        print("[API] Récupération des résultats...")
        response = requests.get(config.API_URL, timeout=config.API_TIMEOUT)
        data = response.json()
        
        if "Value" in data and "G" in data["Value"]:
            games = data["Value"]["G"]
            results = []
            for game in games:
                game_number = int(game["DI"])
                player_cards_raw = game["SC"]["S"][0]["Value"]
                banker_cards_raw = game["SC"]["S"][1]["Value"]
                player_cards = eval(player_cards_raw)
                banker_cards = eval(banker_cards_raw)
                is_finished = game["SC"].get("CPS", "") == "Игра завершена"
                
                results.append({
                    "game_number": game_number,
                    "player_cards": player_cards,
                    "banker_cards": banker_cards,
                    "is_finished": is_finished
                })
            return results
    except Exception as e:
        print(f"[API] Erreur : {e}")
    return []

def update_history(results, history):
    print("[Historique] Mise à jour...")
    for result in results:
        if result["is_finished"]:
            game_number = result["game_number"]
            if game_number not in history:
                history[game_number] = {
                    "player_cards": result["player_cards"],
                    "banker_cards": result["banker_cards"],
                    "is_finished": result["is_finished"]
                }
    return history
              
