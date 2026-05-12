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


# ── Iteration 2 — monetary parsing & currency normalization ──────────────
import re  # noqa: E402  (placed here to keep the module's "logic-then-imports" layout intact)

# Currencies we expect to encounter in MENA + globally-reported finance docs.
# Maps document-spelling fragments (lower-case) to ISO-4217.
_CURRENCY_ALIASES: dict[str, str] = {
    "egp": "EGP",
    "le": "EGP",
    "l.e.": "EGP",
    "egyptian pound": "EGP",
    "جنيه": "EGP",
    "usd": "USD",
    "us$": "USD",
    "$": "USD",
    "dollar": "USD",
    "eur": "EUR",
    "€": "EUR",
    "euro": "EUR",
    "gbp": "GBP",
    "£": "GBP",
    "pound sterling": "GBP",
    "aed": "AED",
    "sar": "SAR",
    "kwd": "KWD",
    "qar": "QAR",
}

# Magnitude suffixes applied to a numeric value.
_MAGNITUDE_FACTORS: dict[str, float] = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "millions": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "billions": 1e9,
    "tn": 1e12,
    "trillion": 1e12,
    "trillions": 1e12,
}


def normalize_currency(raw: str | None) -> str | None:
    """Best-effort currency normalization to ISO-4217.

    Returns ``None`` when no known alias matches. Already-correct ISO codes
    (3 uppercase letters) pass through.
    """
    if not raw:
        return None
    s = raw.strip()
    if len(s) == 3 and s.isalpha() and s.isupper():
        return s
    key = s.lower()
    if key in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[key]
    # Try matching any alias as a substring (e.g., "EGP million", "USD millions").
    for alias, iso in _CURRENCY_ALIASES.items():
        if alias in key:
            return iso
    return None


_MONETARY_RE = re.compile(
    r"""
    ^\s*
    (?P<sign>[-+])?\s*
    (?P<currency_pre>[A-Z]{3}|[$€£])?\s*
    (?P<number>[\d.,٠١٢٣٤٥٦٧٨٩٫٬]+)
    \s*
    (?P<magnitude>k|thousand|m|mn|million|millions|b|bn|billion|billions|tn|trillion|trillions)?
    \s*
    (?P<currency_post>[A-Z]{3}|[$€£]|EGP|USD|EUR|GBP)?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Arabic-Indic digit translation (٠ … ٩ → 0 … 9).
_ARABIC_DIGITS_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _normalize_number_text(num: str) -> float | None:
    """Best-effort numeric parse, handling Arabic-Indic digits + thousands separators."""
    s = num.translate(_ARABIC_DIGITS_TRANS).replace(" ", "")
    # Arabic decimal separator U+066B (٫) and thousands U+066C (٬).
    s = s.replace("٫", ".").replace("٬", ",")
    # If both '.' and ',' present, assume ',' is the thousands separator.
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[-1]) in {1, 2, 3}:
        # Ambiguous single comma — treat as decimal if 1 or 2 trailing digits, else thousands separator.
        whole, frac = s.split(",")
        s = f"{whole.replace(',', '')}.{frac}" if len(frac) in {1, 2} else s.replace(",", "")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_monetary(raw: str | None) -> tuple[float | None, str | None]:
    """Parse a raw monetary string (e.g. ``"EGP 1.2 billion"``, ``"USD 540 mn"``, ``"$2,500"``).

    Returns ``(value, currency_iso)``. Either field can be ``None`` if not parseable.
    Magnitude words (k/m/mn/million/b/bn/billion/tn/trillion) multiply the number.
    Arabic-Indic digits and Arabic decimal/thousands separators are handled.

    Example::

        >>> parse_monetary("EGP 1.2 billion")
        (1200000000.0, 'EGP')
        >>> parse_monetary("$540 mn")
        (540000000.0, 'USD')
    """
    if not raw or not isinstance(raw, str):
        return None, None
    m = _MONETARY_RE.match(raw)
    if not m:
        return None, normalize_currency(raw)
    sign = -1.0 if m.group("sign") == "-" else 1.0
    num = _normalize_number_text(m.group("number"))
    if num is None:
        return None, normalize_currency(m.group("currency_pre") or m.group("currency_post"))
    magnitude = m.group("magnitude")
    factor = _MAGNITUDE_FACTORS.get(magnitude.lower(), 1.0) if magnitude else 1.0
    value = sign * num * factor
    currency = normalize_currency(m.group("currency_pre") or m.group("currency_post"))
    return value, currency
