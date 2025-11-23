import unittest
import pandas as pd
import numpy as np
from technical_analysis import calculate_rsi

class TestTechnicalAnalysis(unittest.TestCase):
    def test_rsi_calculation(self):
        # Create a sample DataFrame with a known RSI pattern
        # Increasing prices -> High RSI
        data = {'close': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]}
        df = pd.DataFrame(data)
        rsi = calculate_rsi(df, period=14)
        self.assertTrue(rsi > 50, f"RSI should be high for increasing prices, got {rsi}")

        # Decreasing prices -> Low RSI
        data_down = {'close': [24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]}
        df_down = pd.DataFrame(data_down)
        rsi_down = calculate_rsi(df_down, period=14)
        self.assertTrue(rsi_down < 50, f"RSI should be low for decreasing prices, got {rsi_down}")

if __name__ == '__main__':
    unittest.main()
