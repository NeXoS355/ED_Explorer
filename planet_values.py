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
    "Earthlike body": 1_200_000,
    "Water world": 600_000,
    "Ammonia world": 400_000,

    # Terraformierbare Welten
    "Rocky body": 130_000,  # wenn terraformierbar
    "High metal content body": 160_000,  # wenn terraformierbar
    "Metal rich body": 140_000,  # wenn terraformierbar

    # Gas Giants
    "Class I gas giant": 3_800,
    "Class II gas giant": 28_000,
    "Class III gas giant": 1_000,
    "Class IV gas giant": 1_100,
    "Class V gas giant": 1_000,
    "Gas giant with water based life": 900_000,
    "Gas giant with ammonia based life": 900_000,
    "Helium rich gas giant": 900,
    "Helium gas giant": 900,
    "Water giant": 670,

    # Eisige Körper
    "Icy body": 500,

    # Felsige Körper (nicht terraformierbar)
    "Rocky ice body": 500,

    # Metal-Körper
    "Metal rich body": 31_000,
    "High metal content body": 14_000,
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
    planet_type = body_data.get("type", "")

    # Spezialfall: Asteroidencluster sind wertlos
    if "Asteroid Cluster" in planet_type:
        return 0

    # Spezialfall: Sterne
    if "Star Class" in planet_type:
        # Extrahiere Sternklasse aus "Star Class X"
        star_class = planet_type.replace("Star Class ", "").strip()
        base_value = STAR_BASE_VALUES.get(star_class, DEFAULT_VALUE)
        # Sterne können nicht gemappt werden, also kein DSS-Multiplikator
        return int(base_value)

    # Basis-Wert ermitteln
    base_value = PLANET_BASE_VALUES.get(planet_type, DEFAULT_VALUE)

    # Spezialfall: Terraformierbare Welten
    if "Terraformable" in planet_type:
        # Extrahiere Original-Typ
        original_type = planet_type.replace(" (Terraformable)", "").strip()
        base_value = PLANET_BASE_VALUES.get(original_type, DEFAULT_VALUE)
        base_value *= TERRAFORMABLE_MULTIPLIER

    total_value = base_value

    # DSS Mapping Bonus
    if has_dss:
        total_value *= DSS_MULTIPLIER

    return int(total_value)


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
