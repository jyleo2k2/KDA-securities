import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "generate_mock_pension_data.py"
SPEC = importlib.util.spec_from_file_location("mock_generator", SCRIPT_PATH)
mock_generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mock_generator)


class MockPensionDataTest(unittest.TestCase):
    def test_generation_is_valid_and_reproducible(self):
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            first_summary = mock_generator.generate(
                Path(first), user_count=300, seed=77
            )
            second_summary = mock_generator.generate(
                Path(second), user_count=300, seed=77
            )

            self.assertEqual(first_summary["status"], "PASS")
            self.assertEqual(first_summary, second_summary)
            self.assertEqual(
                (Path(first) / "users.csv").read_bytes(),
                (Path(second) / "users.csv").read_bytes(),
            )
            self.assertEqual(
                (Path(first) / "accounts.csv").read_bytes(),
                (Path(second) / "accounts.csv").read_bytes(),
            )

    def test_only_requested_account_types_are_generated(self):
        users, accounts = mock_generator.generate_records(user_count=300, seed=11)
        holdings = mock_generator.build_holdings(accounts)
        self.assertEqual(len(users), 300)
        self.assertTrue(accounts)
        self.assertLessEqual(
            {account["account_type"] for account in accounts},
            set(mock_generator.ALLOWED_ACCOUNT_TYPES),
        )
        for account in accounts:
            if account["account_type"] in (mock_generator.DC, mock_generator.IRP):
                self.assertLessEqual(account["risky_asset_ratio"], 0.70)
        account_types = {
            account["account_id"]: account["account_type"] for account in accounts
        }
        self.assertFalse(
            any(
                holding["asset_class"] == "PRINCIPAL_GUARANTEED"
                and account_types[holding["account_id"]]
                == mock_generator.PENSION_SAVINGS_FUND
                for holding in holdings
            )
        )


if __name__ == "__main__":
    unittest.main()
