import importlib.util
import tempfile
import unittest
from collections import Counter
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

    def test_customer_attributes_follow_survey_calibration(self):
        users, _ = mock_generator.generate_records(user_count=1_000, seed=29)

        expected_management_counts = mock_generator.allocate_counts(
            1_000, mock_generator.PREFERRED_MANAGEMENT_WEIGHTS
        )
        self.assertEqual(
            Counter(user["preferred_management_type"] for user in users),
            Counter(expected_management_counts),
        )
        self.assertEqual(
            Counter(user["risk_profile"] for user in users),
            Counter(
                {
                    mock_generator.PREFERRED_MANAGEMENT_TO_RISK_PROFILE[key]: count
                    for key, count in expected_management_counts.items()
                }
            ),
        )
        for field, weights in (
            ("investment_readiness", mock_generator.INVESTMENT_READINESS_WEIGHTS),
            ("primary_outside_asset", mock_generator.PRIMARY_OUTSIDE_ASSET_WEIGHTS),
        ):
            self.assertEqual(
                Counter(user[field] for user in users),
                Counter(mock_generator.allocate_counts(1_000, weights)),
            )

        for user in users:
            self.assertEqual(
                user["risk_profile"],
                mock_generator.PREFERRED_MANAGEMENT_TO_RISK_PROFILE[
                    user["preferred_management_type"]
                ],
            )
            self.assertIn("KEF_RETIREMENT_AWARENESS_2025", user["source_ids"])

        for age_group, age_total in mock_generator.allocate_counts(
            1_000, mock_generator.AGE_GROUP_WEIGHTS
        ).items():
            age_users = [user for user in users if user["age_group"] == age_group]
            self.assertEqual(
                Counter(user["retirement_fund_attitude"] for user in age_users),
                Counter(
                    mock_generator.allocate_counts(
                        age_total,
                        mock_generator.RETIREMENT_FUND_ATTITUDE_WEIGHTS[age_group],
                    )
                ),
            )
            self.assertEqual(
                Counter(user["payout_preference"] for user in age_users),
                Counter(
                    mock_generator.allocate_counts(
                        age_total,
                        mock_generator.PAYOUT_PREFERENCE_WEIGHTS[age_group],
                    )
                ),
            )

    def test_contributions_follow_income_and_activity_rules(self):
        users, accounts = mock_generator.generate_records(user_count=2_000, seed=41)
        gross_salary_by_user = {
            user["user_id"]: user["gross_salary_krw"] for user in users
        }

        for account in accounts:
            monthly = account["monthly_contribution_krw"]
            self.assertEqual(account["annual_contribution_krw"], monthly * 12)
            self.assertEqual(account["contribution_status"] == "ACTIVE", monthly > 0)
            self.assertEqual(
                account["contribution_frequency"] == "NONE", monthly == 0
            )
            if account["account_type"] == mock_generator.DC:
                self.assertEqual(
                    monthly,
                    mock_generator.round_to_10k(
                        gross_salary_by_user[account["user_id"]] / 144
                    ),
                )

        by_type = {
            account_type: [
                account
                for account in accounts
                if account["account_type"] == account_type
            ]
            for account_type in mock_generator.ALLOWED_ACCOUNT_TYPES
        }
        dc_mean = sum(
            account["monthly_contribution_krw"]
            for account in by_type[mock_generator.DC]
        ) / len(by_type[mock_generator.DC])
        self.assertGreater(dc_mean, 450_000)
        self.assertLess(dc_mean, 570_000)

        for account_type in (
            mock_generator.IRP,
            mock_generator.PENSION_SAVINGS_FUND,
        ):
            statuses = {
                account["contribution_status"] for account in by_type[account_type]
            }
            self.assertEqual(statuses, {"ACTIVE", "INACTIVE"})

    def test_tax_scenarios_follow_income_limits_and_receipt_rules(self):
        users, accounts = mock_generator.generate_records(user_count=2_000, seed=53)
        accounts_by_user = {}
        for account in accounts:
            accounts_by_user.setdefault(account["user_id"], []).append(account)

        for user in users:
            user_accounts = accounts_by_user[user["user_id"]]
            if user["employment_type"] == mock_generator.SALARIED_EMPLOYEE:
                self.assertIsNotNone(user["gross_salary_krw"])
                self.assertIsNone(user["comprehensive_income_krw"])
                self.assertEqual(user["tax_credit_income_basis"], "GROSS_SALARY")
                threshold = mock_generator.GROSS_SALARY_TAX_CREDIT_THRESHOLD_KRW
            else:
                self.assertIsNone(user["gross_salary_krw"])
                self.assertIsNotNone(user["comprehensive_income_krw"])
                self.assertEqual(
                    user["tax_credit_income_basis"], "COMPREHENSIVE_INCOME"
                )
                self.assertFalse(
                    any(
                        account["account_type"] == mock_generator.DC
                        for account in user_accounts
                    )
                )
                threshold = (
                    mock_generator.COMPREHENSIVE_INCOME_TAX_CREDIT_THRESHOLD_KRW
                )
            expected_rate = (
                16.5
                if user["tax_credit_income_amount_krw"] <= threshold
                else 13.2
            )
            self.assertEqual(user["pension_tax_credit_rate_pct"], expected_rate)
            self.assertGreater(user["planned_pension_start_age"], user["age"])
            self.assertLessEqual(
                user["total_tax_credit_eligible_contribution_krw"],
                mock_generator.COMBINED_PENSION_TAX_CREDIT_LIMIT_KRW,
            )
            self.assertEqual(
                user["total_tax_credit_eligible_contribution_krw"],
                sum(
                    account["tax_credit_eligible_contribution_krw"]
                    for account in user_accounts
                ),
            )
            pension_savings_eligible = sum(
                account["tax_credit_eligible_contribution_krw"]
                for account in user_accounts
                if account["account_type"]
                == mock_generator.PENSION_SAVINGS_FUND
            )
            self.assertLessEqual(
                pension_savings_eligible,
                mock_generator.PENSION_SAVINGS_TAX_CREDIT_LIMIT_KRW,
            )
            for account in user_accounts:
                self.assertEqual(
                    account["account_open_year"],
                    mock_generator.TAX_YEAR - account["contribution_years"] + 1,
                )
                expected_years_at_receipt = account["contribution_years"] + (
                    user["planned_pension_start_age"] - user["age"]
                )
                self.assertEqual(
                    account["planned_contribution_years_at_receipt"],
                    expected_years_at_receipt,
                )
                if user["payout_preference"] != "LUMP_SUM" and (
                    expected_years_at_receipt >= 5
                ):
                    self.assertEqual(
                        account["pension_receipt_eligibility"], "ELIGIBLE"
                    )
                if account["account_type"] == mock_generator.DC:
                    self.assertEqual(
                        account["tax_credit_eligible_contribution_krw"], 0
                    )

            if user["payout_preference"] == "LUMP_SUM":
                expected_treatment = "NON_PENSION_WITHDRAWAL_REVIEW"
            elif (
                user["planned_annual_personal_pension_receipt_krw"]
                <= mock_generator.PRIVATE_PENSION_SEPARATE_TAX_THRESHOLD_KRW
            ):
                expected_treatment = "LOW_RATE_SEPARATE_TAX"
            else:
                expected_treatment = (
                    "COMPREHENSIVE_OR_16_5_SEPARATE_CHOICE"
                )
            self.assertEqual(
                user["planned_receipt_tax_treatment"], expected_treatment
            )


if __name__ == "__main__":
    unittest.main()
