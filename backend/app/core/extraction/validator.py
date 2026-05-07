"""Value validation and unit normalization for extracted ESG metrics.

Unit normalization rules (from CLAUDE.md):
- Energy   → GJ  (accept kWh, MWh, TJ, toe)
- Emissions → tCO2e
- Water    → m3  (accept liters, gallons, ML)

Always store both normalized and original values.
"""

from __future__ import annotations

# ── Unit normalization maps ──────────────────────────────────────────────
_ENERGY_CONVERSIONS: dict[str, float] = {
    "kwh": 0.0036,       # kWh → GJ
    "mwh": 3.6,          # MWh → GJ
    "gwh": 3600.0,       # GWh → GJ
    "tj": 1000.0,        # TJ → GJ
    "gj": 1.0,           # already GJ
    "toe": 41.868,       # tonnes of oil equivalent → GJ
    "mmbtu": 1.05505,    # MMBtu → GJ
}

_WATER_CONVERSIONS: dict[str, float] = {
    "m3": 1.0,
    "m³": 1.0,
    "liter": 0.001,
    "litre": 0.001,
    "l": 0.001,
    "ml": 0.000001,
    "kl": 1.0,           # kiloliter = m3
    "megaliter": 1000.0,
    "ml_volume": 1000.0,
    "gallon": 0.003785,
    "usgallon": 0.003785,
}

_EMISSION_UNITS = {"tco2e", "tco2", "t co2e", "tonnes co2e", "metric tons co2e"}


def normalize_energy(value: float, unit: str) -> tuple[float, str] | None:
    """Convert an energy value to GJ.

    Returns:
        ``(normalized_value, "GJ")`` or ``None`` if unit is unrecognized.
    """
    key = unit.lower().strip()
    factor = _ENERGY_CONVERSIONS.get(key)
    if factor is None:
        return None
    return round(value * factor, 4), "GJ"


def normalize_water(value: float, unit: str) -> tuple[float, str] | None:
    """Convert a water volume to m³.

    Returns:
        ``(normalized_value, "m3")`` or ``None`` if unit is unrecognized.
    """
    key = unit.lower().strip()
    factor = _WATER_CONVERSIONS.get(key)
    if factor is None:
        return None
    return round(value * factor, 4), "m3"


def is_emission_unit(unit: str) -> bool:
    """Return True if the unit string looks like a CO2e unit."""
    return unit.lower().strip() in _EMISSION_UNITS


# ── Type-safe helpers ────────────────────────────────────────────────────
def safe_float(val: object) -> float | None:
    """Convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def safe_int(val: object) -> int | None:
    """Convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def clamp(v: float, lo: float, hi: float) -> float:
    """Clamp v to the range [lo, hi]."""
    return max(lo, min(hi, v))
