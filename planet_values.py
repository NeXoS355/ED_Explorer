"""
Elite Dangerous - Kartendaten Bewertungssystem
Näherungswerte basierend auf Community-Daten und eigener Erfahrung
Stand: Januar 2026
"""

# =============================================================
# BASIS-WERTE FÜR PLANETEN (Credits bei First Discovery + Mapping)
# =============================================================

PLANET_BASE_VALUES = {
    # Hochwertige Welten
    "earthlike body": 1_200_000,
    "water world": 600_000,
    "ammonia world": 400_000,

    # Terraformierbare Welten
    "rocky body": 130_000,
    "high metal content body": 160_000,
    "metal rich body": 140_000,

    # Gas Giants
    "class i gas giant": 3_800,
    "class ii gas giant": 28_000,
    "class iii gas giant": 1_000,
    "class iv gas giant": 1_100,
    "class v gas giant": 1_000,
    "gas giant with water based life": 900_000,
    "gas giant with ammonia based life": 900_000,
    "helium rich gas giant": 900,
    "helium gas giant": 900,
    "water giant": 670,

    # Eisige Körper
    "icy body": 500,
    "rocky ice body": 500,

    # Metal-Körper
    "metal rich body": 31_000,
    "high metal content body": 14_000,
}

# Basis-Werte für Sternklassen
STAR_BASE_VALUES = {
    "O": 4_000,
    "B": 3_000,
    "A": 2_500,
    "F": 2_000,
    "G": 1_500,
    "K": 1_200,
    "M": 1_000,
    "L": 2_500,
    "T": 2_500,
    "Y": 2_500,
    "TTS": 2_000,
    "AeBe": 3_500,
    "W": 15_000,
    "WN": 15_000,
    "WNC": 15_000,
    "WC": 15_000,
    "WO": 15_000,
    "MS": 20_000,
    "S": 20_000,
    "C": 3_000,
    "CN": 3_000,
    "CJ": 3_000,
    "CH": 3_000,
    "CHd": 3_000,
    "N": 22_628,
    "H": 1_200,
    "X": 30_000,
    "SupermassiveBlackHole": 40_000,
    "D": 14_000,
    "DA": 14_000,
    "DAB": 14_000,
    "DAO": 14_000,
    "DAZ": 14_000,
    "DAV": 14_000,
    "DB": 14_000,
    "DBZ": 14_000,
    "DBV": 14_000,
    "DO": 14_000,
    "DOV": 14_000,
    "DQ": 14_000,
    "DC": 14_000,
    "DCV": 14_000,
    "DX": 14_000,
}

# Fallback für unbekannte Typen
DEFAULT_VALUE = 500

# =============================================================
# MULTIPLIKATOREN
# =============================================================

# Terraformierbar
TERRAFORMABLE_MULTIPLIER = 10.0

# Detailed Surface Scanner (DSS) - Mapping Bonus
DSS_MULTIPLIER = 5.0

# =============================================================
# BEWERTUNGSFUNKTION
# =============================================================

def calculate_body_value(body_data, has_dss=False):
    """
    Berechnet den geschätzten Kartendaten-Wert eines Körpers

    Args:
        body_data: Dictionary mit Körper-Informationen
        has_dss: Ob DSS verwendet wurde

    Returns:
        int: Geschätzter Wert in Credits
    """
    planet_type = body_data.get("type", "").lower().strip()

    # Asteroiden
    if "asteroid cluster" in planet_type:
        return 0

    # Sterne
    if planet_type.startswith("star class"):
        star_class = planet_type.replace("star class", "").strip().upper()
        base_value = STAR_BASE_VALUES.get(star_class, DEFAULT_VALUE)
        return int(base_value)

    # Terraformierbar
    if "terraformable" in planet_type:
        original_type = planet_type.replace(" (terraformable)", "").strip()
        base_value = PLANET_BASE_VALUES.get(original_type, DEFAULT_VALUE)
        base_value *= TERRAFORMABLE_MULTIPLIER
    else:
        base_value = PLANET_BASE_VALUES.get(planet_type, DEFAULT_VALUE)

    if has_dss:
        base_value *= DSS_MULTIPLIER

    return int(base_value)


def calculate_system_value(bodies):
    """
    Berechnet den Gesamtwert aller Körper in einem System

    Args:
        bodies: Liste von body_data Dictionaries

    Returns:
        int: Gesamtwert in Credits
    """
    total = 0
    for body in bodies:
        total += body.get("value", 0)
    return total


# =============================================================
# HILFSFUNKTIONEN
# =============================================================

def format_credits(value):
    """Formatiert Credits lesbar (z.B. 1.2M cr)"""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M cr"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K cr"
    else:
        return f"{value} cr"


def is_valuable_system(total_value, threshold=1_000):
    """Prüft ob ein System wertvoll genug ist zum Speichern"""
    return total_value >= threshold
