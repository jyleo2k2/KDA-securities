import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ACCOUNT_TYPES = {"dc", "irp", "pension_savings"}


@dataclass(frozen=True, slots=True)
class PensionAccountUniverse:
    account_type: str
    as_of: date
    products: tuple[dict[str, Any], ...]

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        expected_account: str,
    ) -> "PensionAccountUniverse":
        if expected_account not in ACCOUNT_TYPES:
            raise ValueError(f"unsupported pension account: {expected_account}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("pension universe root must be an object")
        if payload.get("report_type") != "pension_account_eligible_etfs_by_account":
            raise ValueError("portfolio engine requires an account-specific report")
        if payload.get("algorithm_input") is not True:
            raise ValueError("pension universe is not approved as algorithm input")
        if payload.get("product_scope") != "account_eligible_only":
            raise ValueError("pension universe must contain account-eligible ETFs only")
        if payload.get("account_type") != expected_account:
            raise ValueError("pension universe account type does not match request")

        products = payload.get("products")
        if not isinstance(products, list):
            raise ValueError("pension universe products must be an array")
        if payload.get("product_count") != len(products):
            raise ValueError("pension universe product count does not match products")

        codes = []
        for product in products:
            if not isinstance(product, dict):
                raise ValueError("pension universe product must be an object")
            code = product.get("isu_code")
            classification = product.get("classification")
            eligibility = product.get("account_eligibility")
            if not isinstance(code, str) or not code:
                raise ValueError("pension universe product has no ETF code")
            if not isinstance(classification, dict):
                raise ValueError(f"ETF {code} has no classification")
            if classification.get("leverage_type") != "normal":
                raise ValueError(f"ETF {code} is leveraged or inverse")
            if (
                not isinstance(eligibility, dict)
                or eligibility.get("eligible") is not True
            ):
                raise ValueError(f"ETF {code} is not eligible for {expected_account}")
            codes.append(code)
        if len(codes) != len(set(codes)):
            raise ValueError("pension universe contains duplicate ETF codes")

        return cls(
            account_type=expected_account,
            as_of=date.fromisoformat(str(payload["as_of"])),
            products=tuple(products),
        )

    @classmethod
    def from_latest_cache(
        cls,
        account_type: str,
        cache_root: Path = Path("data/cache/classification"),
    ) -> "PensionAccountUniverse":
        candidates = sorted(cache_root.glob(f"{account_type}_eligible_etfs_*.json"))
        if not candidates:
            raise FileNotFoundError(
                f"no account-eligible ETF report for {account_type} in {cache_root}"
            )
        return cls.from_path(candidates[-1], expected_account=account_type)
