import unittest
from unittest.mock import patch
import oracle

NOW = 1791540000

class TestOracle(unittest.TestCase):
    def test_convert_price_and_cap(self):
        data = oracle.parse_market_data({"tron": {"usd": 0.123456785, "usd_market_cap": 10750000000.49, "last_updated_at": NOW - 30}}, now=NOW)
        self.assertEqual(data.price_e8, 12345679)
        self.assertEqual(data.market_cap_usd, 10750000000)
        self.assertEqual(data.timestamp, NOW - 30)

    def test_reject_stale_and_future(self):
        for timestamp in [NOW - 2000, NOW + 70]:
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    oracle.parse_market_data({"tron": {"usd": 0.3, "usd_market_cap": 8e9, "last_updated_at": timestamp}}, now=NOW)

    def test_reject_negative_or_missing(self):
        for payload in [{}, {"tron": {"usd": -2, "usd_market_cap": 9e9, "last_updated_at": NOW}}, {"tron": {"usd": .3, "usd_market_cap": None, "last_updated_at": NOW}}]:
            with self.assertRaises(ValueError):
                oracle.parse_market_data(payload, now=NOW)

    def test_method_abi(self):
        for method, getter in oracle.ALLOWED_FUNCTIONS.items():
            abi = oracle.minimal_abi(method)
            self.assertEqual(abi[0]["name"], method)
            self.assertEqual(abi[1]["name"], getter)
            self.assertEqual(len(abi[0]["inputs"]), 3)

    def test_read_only_never_calls_tronpy(self):
        obj = oracle.TrxReference(30_000_000, 9_000_000_000, NOW)
        with patch.object(oracle, 'fetch_market_data', return_value=obj), patch.object(oracle, 'submit_nile_update') as submit, patch.dict('os.environ', {'ENABLE_NILE_WRITES':'false'}):
            oracle.main()
            submit.assert_not_called()

if __name__ == "__main__":
    unittest.main()
