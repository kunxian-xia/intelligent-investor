from __future__ import annotations


# Conservative mappings for common US-GAAP concepts. Values are preserved in the
# issuer's reported unit and sign; the raw taxonomy/concept remains authoritative.
STANDARD_METRICS: dict[str, tuple[str, str]] = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": ("income_statement", "revenue"),
    "Revenues": ("income_statement", "revenue"),
    "SalesRevenueNet": ("income_statement", "revenue"),
    "GrossProfit": ("income_statement", "gross_profit"),
    "OperatingIncomeLoss": ("income_statement", "operating_income"),
    "NetIncomeLoss": ("income_statement", "net_income"),
    "EarningsPerShareDiluted": ("income_statement", "diluted_eps"),
    "Assets": ("balance_sheet", "total_assets"),
    "AssetsCurrent": ("balance_sheet", "current_assets"),
    "Liabilities": ("balance_sheet", "total_liabilities"),
    "LiabilitiesCurrent": ("balance_sheet", "current_liabilities"),
    "StockholdersEquity": ("balance_sheet", "stockholders_equity"),
    "CashAndCashEquivalentsAtCarryingValue": ("balance_sheet", "cash_and_equivalents"),
    "LongTermDebtCurrent": ("balance_sheet", "current_long_term_debt"),
    "LongTermDebtNoncurrent": ("balance_sheet", "long_term_debt"),
    "NetCashProvidedByUsedInOperatingActivities": ("cash_flow", "operating_cash_flow"),
    "NetCashProvidedByUsedInInvestingActivities": ("cash_flow", "investing_cash_flow"),
    "NetCashProvidedByUsedInFinancingActivities": ("cash_flow", "financing_cash_flow"),
    "PaymentsToAcquirePropertyPlantAndEquipment": ("cash_flow", "capital_expenditure"),
    "PaymentsOfDividends": ("cash_flow", "dividends_paid"),
    "PaymentsForRepurchaseOfCommonStock": ("cash_flow", "share_repurchases"),
}

IFRS_STANDARD_METRICS: dict[str, tuple[str, str]] = {
    "Revenue": ("income_statement", "revenue"),
    "GrossProfit": ("income_statement", "gross_profit"),
    "ProfitLossFromOperatingActivities": ("income_statement", "operating_income"),
    "ProfitLoss": ("income_statement", "net_income"),
    "DilutedEarningsLossPerShare": ("income_statement", "diluted_eps"),
    "BasicAndDilutedEarningsLossPerShare": ("income_statement", "diluted_eps"),
    "Assets": ("balance_sheet", "total_assets"),
    "CurrentAssets": ("balance_sheet", "current_assets"),
    "Liabilities": ("balance_sheet", "total_liabilities"),
    "CurrentLiabilities": ("balance_sheet", "current_liabilities"),
    "EquityAttributableToOwnersOfParent": ("balance_sheet", "stockholders_equity"),
    "Equity": ("balance_sheet", "total_equity"),
    "CashAndCashEquivalents": ("balance_sheet", "cash_and_equivalents"),
    "CurrentPortionOfLongtermBorrowings": ("balance_sheet", "current_long_term_debt"),
    "LongtermBorrowings": ("balance_sheet", "long_term_debt"),
    "CashFlowsFromUsedInOperatingActivities": ("cash_flow", "operating_cash_flow"),
    "CashFlowsFromUsedInInvestingActivities": ("cash_flow", "investing_cash_flow"),
    "CashFlowsFromUsedInFinancingActivities": ("cash_flow", "financing_cash_flow"),
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": (
        "cash_flow",
        "capital_expenditure",
    ),
    "DividendsPaid": ("cash_flow", "dividends_paid"),
    "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities": (
        "cash_flow",
        "dividends_paid",
    ),
}


def classify_concept(taxonomy: str, concept: str) -> tuple[str | None, str | None]:
    if taxonomy == "us-gaap":
        return STANDARD_METRICS.get(concept, (None, None))
    if taxonomy == "ifrs-full":
        return IFRS_STANDARD_METRICS.get(concept, (None, None))
    return None, None
