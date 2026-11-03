from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .db import revision_transaction


def _metric(name: str, description: str, unit: str, cadence: str = "quarterly",
            direction: str = "contextual", *, formula: str | None = None,
            scope: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"display_name": name, "description": description, "default_unit": unit,
            "cadence": cadence, "preferred_direction": direction, "formula": formula,
            "required_scope": scope}


UPSTREAM_OIL_METRICS = {
    "proved_reserves": _metric("Total proved reserves", "Year-end proved oil and gas reserves.",
                               "million boe", "annual", "higher", scope=("interest_basis",)),
    "reserve_replacement_ratio": _metric("Reserve replacement ratio",
        "Organic proved reserve additions divided by annualized production.", "%", "annual", "higher",
        formula="reserve_additions / annualized production * 100"),
    "reserve_life": _metric("Reserve life", "Proved reserves divided by annualized production.",
                            "years", "annual", "higher",
                            formula="proved_reserves / annualized production"),
    "production": _metric("Oil and gas production", "Average daily production.",
                          "thousand boe/day", scope=("interest_basis", "product")),
    "upstream_capex": _metric("Upstream capital expenditure",
                              "Capital expenditure attributable to E&P.", "USD million"),
    "realized_oil_price": _metric("Realized oil price", "Average realized crude oil sales price.",
                                  "USD/bbl", direction="higher", scope=("hedge_basis",)),
    "realized_gas_price": _metric("Realized natural gas price", "Average realized gas sales price.",
                                  "USD/boe", direction="higher", scope=("hedge_basis",)),
    "lifting_cost": _metric("Lifting cost", "Unit cost to operate producing assets.",
                            "USD/boe", direction="lower", scope=("cost_definition",)),
}

OFFSHORE_METRICS = {
    "reserve_additions": _metric("Organic proved reserve additions",
        "Extensions, discoveries, improved recovery and revisions, excluding M&A.",
        "million boe", "annual", "higher", scope=("interest_basis",)),
    "fpso_actual_throughput": _metric("FPSO actual throughput",
        "Average oil throughput through one FPSO.", "thousand bbl/day", scope=("asset",)),
    "fpso_capacity": _metric("FPSO design capacity", "Nameplate oil processing capacity.",
                             "thousand bbl/day", "event", scope=("asset",)),
    "fpso_utilization": _metric("FPSO utilization", "Actual throughput divided by design capacity.",
        "%", formula="fpso_actual_throughput / fpso_capacity * 100", scope=("asset",)),
    "fpso_uptime": _metric("FPSO uptime", "Percentage of scheduled time the FPSO was available.",
                           "%", direction="higher", scope=("asset",)),
    "water_cut": _metric("Water cut", "Produced water divided by total produced liquids.",
                         "%", direction="lower", scope=("asset",)),
    "production_efficiency": _metric("Production efficiency",
        "Actual production divided by production potential.", "%", direction="higher", scope=("asset",)),
    "lost_production": _metric("Lost production", "Production lost to planned and unplanned outages.",
                               "thousand boe", scope=("asset", "loss_cause")),
    "project_schedule_variance": _metric("Project schedule variance",
        "Latest expected first oil minus original first-oil date.", "months", "event", "lower",
        scope=("project",)),
    "project_cost_overrun": _metric("Project cost overrun",
        "Latest project cost estimate relative to sanctioned budget.", "%", "event", "lower",
        scope=("project",)),
    "decommissioning_obligation": _metric("Decommissioning obligation",
        "Reported asset retirement or abandonment obligation.", "USD million", "annual", "lower",
        scope=("discount_basis",)),
    "field_netback": _metric("Field netback",
        "Realized price less royalties, transport and lifting cost.", "USD/boe",
        formula="realized price - royalty - transport - lifting cost"),
}

SHALE_METRICS = {
    "base_decline_rate": _metric("Base production decline",
        "Decline of the same producing-well population.", "%", "annual", "lower",
        scope=("cohort_basis",)),
    "wells_turned_to_sales": _metric("Wells turned to sales",
        "Gross or net wells commencing sales in the period.", "wells", scope=("interest_basis",)),
    "well_cost": _metric("Drilling and completion cost per well",
        "Average drilling and completion capital per well.", "USD million/well", direction="lower",
        scope=("basin", "lateral_length_ft")),
    "ip90": _metric("IP90", "Average daily production during the first 90 days.", "boe/day",
                    scope=("basin", "lateral_length_ft", "product_mix")),
    "eur_per_1000ft": _metric("EUR per 1,000 lateral feet",
        "Estimated ultimate recovery normalized by lateral length.", "thousand boe/1000ft",
        "event", "higher", scope=("basin",)),
    "economic_locations": _metric("Economic drilling locations",
        "Undrilled locations meeting a stated price and return threshold.", "locations", "annual", "higher",
        scope=("price_deck", "return_threshold")),
    "maintenance_capex": _metric("Maintenance capital",
        "Capital required to hold production approximately flat.", "USD million", "annual", "lower",
        scope=("methodology",)),
}

METRIC_PACKS = {
    "upstream_oil": UPSTREAM_OIL_METRICS,
    "offshore_ep": {**UPSTREAM_OIL_METRICS, **OFFSHORE_METRICS},
    "shale_ep": {**UPSTREAM_OIL_METRICS, **SHALE_METRICS},
}


def seed_metric_definitions(connection: sqlite3.Connection) -> None:
    seen: set[str] = set()
    for pack, metrics in METRIC_PACKS.items():
        for key, definition in metrics.items():
            if key not in seen:
                connection.execute(
                    """INSERT INTO operating_metric_definitions(
                           metric_key, metric_pack, display_name, description, default_unit,
                           cadence, preferred_direction, definition_version, formula, required_scope_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(metric_key) DO UPDATE SET
                           display_name=excluded.display_name, description=excluded.description,
                           default_unit=excluded.default_unit, cadence=excluded.cadence,
                           preferred_direction=excluded.preferred_direction,
                           definition_version=excluded.definition_version, formula=excluded.formula,
                           required_scope_json=excluded.required_scope_json""",
                    (key, pack, definition["display_name"], definition["description"],
                     definition["default_unit"], definition["cadence"],
                     definition["preferred_direction"], "2.0", definition["formula"],
                     json.dumps(definition["required_scope"])),
                )
                seen.add(key)
            connection.execute("INSERT OR IGNORE INTO metric_pack_members VALUES (?, ?)", (pack, key))


def configure_metric_pack(connection: sqlite3.Connection, ticker: str, metric_pack: str) -> int:
    if metric_pack not in METRIC_PACKS:
        raise ValueError(f"Unknown metric pack: {metric_pack}")
    for key in METRIC_PACKS[metric_pack]:
        connection.execute(
            """INSERT INTO company_metric_config(ticker, metric_key, enabled) VALUES (?, ?, 1)
               ON CONFLICT(ticker, metric_key) DO UPDATE SET enabled=1""", (ticker.upper(), key))
    connection.commit()
    return len(METRIC_PACKS[metric_pack])


def _scope_json(scope: dict[str, Any] | None) -> str:
    return json.dumps(scope or {}, sort_keys=True, separators=(",", ":"))


def _insert_metric(connection: sqlite3.Connection, *, ticker: str, metric_key: str,
                   period_end: str, value: float, unit: str, accession_number: str,
                   period_start: str | None, period_type: str, scope: dict[str, Any] | None,
                   evidence_text: str | None, source_locator: str | None,
                   extraction_method: str, confidence: float, value_status: str,
                   calculation: dict[str, Any] | None) -> int:
    if value_status not in {"reported", "derived", "estimated"}:
        raise ValueError(f"Invalid value status: {value_status}")
    definition = connection.execute(
        "SELECT definition_version FROM operating_metric_definitions WHERE metric_key=?", (metric_key,)
    ).fetchone()
    if definition is None:
        raise ValueError(f"Unknown operating metric: {metric_key}")
    filing = connection.execute(
        "SELECT filing_date, source_url FROM filings WHERE accession_number=? AND ticker=?",
        (accession_number, ticker.upper()),
    ).fetchone()
    if filing is None:
        raise ValueError(f"Filing not found for {ticker}: {accession_number}")
    scope_value = _scope_json(scope)
    connection.execute(
        """INSERT INTO operating_metric_observations(
               ticker, metric_key, period_start, period_end, period_type, value, unit,
               scope_json, accession_number, filed_date, source_url, evidence_text,
               source_locator, extraction_method, confidence, definition_version,
               inserted_at, value_status, calculation_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(ticker, metric_key, period_end, scope_json, accession_number)
           DO UPDATE SET value=excluded.value, unit=excluded.unit,
               evidence_text=excluded.evidence_text, source_locator=excluded.source_locator,
               extraction_method=excluded.extraction_method, confidence=excluded.confidence,
               inserted_at=excluded.inserted_at, value_status=excluded.value_status,
               calculation_json=excluded.calculation_json""",
        (ticker.upper(), metric_key, period_start, period_end, period_type, value, unit,
         scope_value, accession_number, filing["filing_date"], filing["source_url"],
         evidence_text, source_locator, extraction_method, confidence,
         definition["definition_version"], datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
         value_status, json.dumps(calculation, sort_keys=True) if calculation else None),
    )
    return int(connection.execute(
        """SELECT id FROM operating_metric_observations
           WHERE ticker=? AND metric_key=? AND period_end=? AND scope_json=? AND accession_number=?""",
        (ticker.upper(), metric_key, period_end, scope_value, accession_number),
    ).fetchone()[0])


def record_metric(connection: sqlite3.Connection, *, ticker: str, metric_key: str,
                  period_end: str, value: float, unit: str, accession_number: str,
                  period_start: str | None = None, period_type: str = "annual",
                  scope: dict[str, Any] | None = None, evidence_text: str | None = None,
                  source_locator: str | None = None, extraction_method: str = "curated",
                  confidence: float = 1.0, value_status: str = "reported") -> int:
    with revision_transaction(connection) as revision:
        _insert_metric(connection, ticker=ticker, metric_key=metric_key, period_end=period_end,
            value=value, unit=unit, accession_number=accession_number, period_start=period_start,
            period_type=period_type, scope=scope, evidence_text=evidence_text,
            source_locator=source_locator, extraction_method=extraction_method,
            confidence=confidence, value_status=value_status, calculation=None)
    return revision


@dataclass(frozen=True)
class Derivation:
    inputs: tuple[tuple[str, str, str], ...]
    output_unit: str
    calculate: Callable[[dict[str, float]], float]


DERIVATIONS = {
    "reserve_life": Derivation(
        (("reserves", "proved_reserves", "million boe"),
         ("production", "production", "thousand boe/day")),
        "years", lambda x: x["reserves"] / (x["production"] * 365 / 1000)),
    "reserve_replacement_ratio": Derivation(
        (("additions", "reserve_additions", "million boe"),
         ("production", "production", "thousand boe/day")),
        "%", lambda x: x["additions"] / (x["production"] * 365 / 1000) * 100),
    "fpso_utilization": Derivation(
        (("throughput", "fpso_actual_throughput", "thousand bbl/day"),
         ("capacity", "fpso_capacity", "thousand bbl/day")),
        "%", lambda x: x["throughput"] / x["capacity"] * 100),
}


def derive_metric(connection: sqlite3.Connection, *, ticker: str, metric_key: str,
                  period_end: str, scope: dict[str, Any] | None = None) -> int:
    rule = DERIVATIONS.get(metric_key)
    if rule is None:
        raise ValueError(f"No deterministic derivation registered for: {metric_key}")
    inputs: list[tuple[str, sqlite3.Row]] = []
    for role, input_key, required_unit in rule.inputs:
        row = connection.execute(
            """SELECT * FROM operating_metric_observations
               WHERE ticker=? AND metric_key=? AND period_end=? AND scope_json=?
               ORDER BY filed_date DESC, id DESC LIMIT 1""",
            (ticker.upper(), input_key, period_end, _scope_json(scope)),
        ).fetchone()
        if row is None:
            raise ValueError(f"Missing {input_key} for {ticker} {period_end}")
        if row["unit"] != required_unit:
            raise ValueError(f"{input_key} must use {required_unit}; got {row['unit']}")
        inputs.append((role, row))
    values = {role: float(row["value"]) for role, row in inputs}
    try:
        value = rule.calculate(values)
    except ZeroDivisionError as exc:
        raise ValueError("Cannot derive metric with a zero denominator") from exc
    newest = max((row for _, row in inputs), key=lambda row: (row["filed_date"], row["id"]))
    formula = connection.execute(
        "SELECT formula FROM operating_metric_definitions WHERE metric_key=?", (metric_key,)
    ).fetchone()[0]
    calculation = {"formula": formula, "inputs": {role: int(row["id"]) for role, row in inputs}}
    with revision_transaction(connection) as revision:
        derived_id = _insert_metric(connection, ticker=ticker, metric_key=metric_key,
            period_end=period_end, value=value, unit=rule.output_unit,
            accession_number=newest["accession_number"], period_start=None,
            period_type="annual" if metric_key.startswith("reserve_") else "quarterly",
            scope=scope, evidence_text=None, source_locator=None,
            extraction_method="deterministic_formula",
            confidence=min(float(row["confidence"]) for _, row in inputs),
            value_status="derived", calculation=calculation)
        connection.execute("DELETE FROM metric_calculation_inputs WHERE derived_observation_id=?",
                           (derived_id,))
        connection.executemany(
            "INSERT INTO metric_calculation_inputs VALUES (?, ?, ?)",
            [(derived_id, int(row["id"]), role) for role, row in inputs])
    return revision


BOUNDS = {"water_cut": (0, 100), "fpso_uptime": (0, 100),
          "fpso_utilization": (0, 105), "production_efficiency": (0, 105)}


def validate_metrics(connection: sqlite3.Connection, ticker: str | None = None) -> int:
    if ticker:
        connection.execute("DELETE FROM metric_quality_issues WHERE ticker=?", (ticker.upper(),))
        rows = connection.execute(
            """SELECT o.*, d.required_scope_json FROM operating_metric_observations o
               JOIN operating_metric_definitions d USING(metric_key) WHERE o.ticker=?""",
            (ticker.upper(),)).fetchall()
    else:
        connection.execute("DELETE FROM metric_quality_issues")
        rows = connection.execute(
            """SELECT o.*, d.required_scope_json FROM operating_metric_observations o
               JOIN operating_metric_definitions d USING(metric_key)""").fetchall()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    issues: list[tuple[Any, ...]] = []
    for row in rows:
        scope = json.loads(row["scope_json"])
        for key in json.loads(row["required_scope_json"] or "[]"):
            if key not in scope:
                issues.append((row["id"], row["ticker"], row["metric_key"], row["period_end"],
                    "warning", f"missing_scope:{key}", f"Required scope field is missing: {key}", now))
        if row["metric_key"] in BOUNDS:
            low, high = BOUNDS[row["metric_key"]]
            if not low <= float(row["value"]) <= high:
                issues.append((row["id"], row["ticker"], row["metric_key"], row["period_end"],
                    "error", "outside_plausible_range",
                    f"Value {row['value']} is outside the allowed range {low}..{high}", now))
        if row["value_status"] == "derived":
            count = connection.execute(
                "SELECT count(*) FROM metric_calculation_inputs WHERE derived_observation_id=?",
                (row["id"],)).fetchone()[0]
            if count == 0:
                issues.append((row["id"], row["ticker"], row["metric_key"], row["period_end"],
                    "error", "missing_calculation_lineage", "Derived value has no linked inputs", now))
    connection.executemany(
        """INSERT INTO metric_quality_issues(observation_id, ticker, metric_key, period_end,
               severity, rule_key, message, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", issues)
    connection.commit()
    return len(issues)
