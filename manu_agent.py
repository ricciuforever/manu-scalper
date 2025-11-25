import os
import google.generativeai as genai
import json
from config import GEMINI_API_KEY, DEFAULT_AI_PROMPT

# Controlliamo una variabile d'ambiente per attivare la modalità di test
IS_TEST_ENV = os.getenv('IS_TEST_ENV', 'false').lower() == 'true'

class AIAgent:
    def __init__(self, db_manager):
        """Initializes the AI Agent."""
        self.db = db_manager
        self.model = None

        if IS_TEST_ENV:
            print("🔧 AI AGENT: In esecuzione in modalità MOCK (Test). Nessuna chiamata reale all'API verrà effettuata.")
        else:
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY non trovato nelle variabili d'ambiente.")

            genai.configure(api_key=GEMINI_API_KEY)
            # Nome del modello corretto come da tua indicazione
            self.model = genai.GenerativeModel('gemini-2.0-flash-lite')

    def get_trade_decision(self, symbol, market_data):
        """Analyzes market data to make a trade decision. Returns a mock decision in test env."""
        if IS_TEST_ENV:
            return self._get_mock_decision(market_data)

        try:
            prompt = self._build_prompt(symbol, market_data)
            response = self.model.generate_content(prompt)
            decision_text = response.text.strip()
            return self._parse_json_response(decision_text)
        except Exception as e:
            print(f"🤖 AI AGENT ERROR for {symbol}: {e}")
            return None

    def _get_mock_decision(self, market_data):
        """Returns a hardcoded, sample AI decision for testing purposes."""
        print(f"🔧 AI AGENT (MOCK): Generazione di una decisione fittizia per {market_data.get('symbol', 'N/A')}")
        return {
          "bias": "LONG",
          "entry_price": market_data.get('current_price', 100),
          "stop_loss": market_data.get('current_price', 100) * 0.99, # 1% SL
          "take_profit": market_data.get('current_price', 100) * 1.02, # 2% TP
          "confidence": 0.88,
          "reason": "Decisione MOCK: Il prezzo sembra basso, potenziale rimbalzo."
        }

    def _build_prompt(self, symbol, market_data):
        """Constructs the prompt to be sent to the AI model using a template from the DB."""
        data_str = json.dumps(market_data, indent=2, default=str)
        system_prompt_template = self.db.get_setting('AI_PROMPT', DEFAULT_AI_PROMPT)

        final_prompt = f"""
{system_prompt_template}

**Symbol:**
{symbol}

**Market Data:**
```json
{data_str}
```

Now, analyze the data for **{symbol}** and provide your trading decision in the specified JSON format.
"""
        return final_prompt

    def _parse_json_response(self, text):
        """Safely extracts and parses the JSON part of the AI's response."""
        json_start = text.find('{')
        json_end = text.rfind('}') + 1

        if json_start == -1 or json_end == 0:
            raise ValueError(f"No JSON object found in AI response: {text}")

        json_str = text[json_start:json_end]
        return json.loads(json_str)
