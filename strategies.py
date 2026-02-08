import random
from datetime import datetime

class StrategyManager:
    def __init__(self):
        random.seed(int(datetime.now().timestamp()))
        self.last_two_games = [
            "#n905 4 (10♥️4♠️) - ✅9 (6♠️3♥️) #T13 #R🔵 #П2 #C2_2",
            "#n905 1 (4♠️10♣️7♥️) - ✅2 (9♥️6♦️7♠️) #T3 #П2 #M #C3_3"
        ]
        self.last_color = "♥️"
        self.color_stats = {}

    def predict_color(self, last_predicted_color):
        colors = ["♥️", "♣️", "♦️", "♠️"]
        filtered = [color for color in colors if color != last_predicted_color]
        new_color = random.choice(filtered)

        if new_color == "♠️":
            return "♦️"
        if new_color == "♦️":
            return "♠️"
        return new_color

    def generate_prediction(self, history):
        if not history:
            return None

        current_game_number = max(history.keys())
        color = self.predict_color(self.last_color)
        self.last_color = color
        self.color_stats[color] = self.color_stats.get(color, 0) + 1
        
        predicted_game_number = current_game_number + 1
        
        print(f"[Stratégie] Prédiction : {color} (jeu {predicted_game_number})")
        return {
            "symbol": color,
            "number": None,
            "game_number": predicted_game_number,
            "status": None,
            "result_game": None,
            "message_id": None
        }

    def notify_result(self, success):
        pass
                      
