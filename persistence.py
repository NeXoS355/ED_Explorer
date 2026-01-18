import json
from pathlib import Path
from datetime import datetime
from planet_values import calculate_system_value, format_credits, is_valuable_system

class ExplorationCache:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"systems": {}}
        self.load()

    def load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def has_system(self, system_address):
        return str(system_address) in self.data["systems"]

    def store_system(self, state):
        key = str(state.current_system_address)

        # Berechne System-Wert (gibt jetzt direkt int zurück)
        total_value = calculate_system_value(state.bodies)

        # Nur speichern wenn System wertvoll genug ist
        if not is_valuable_system(total_value):
            return  # System nicht relevant → nichts speichern

        # Sammle wichtige Körper mit Werten
        important_bodies = []
        flags = set()

        for body in state.bodies:
            # Wert direkt aus body holen
            body_value = body.get("value", 0)

            # Setze Flags
            if body.get("bio_signals", 0) > 0:
                flags.add("BIO")

            if "Earthlike" in body["type"]:
                flags.add("ELW")
            if "Terraformable" in body["type"]:
                flags.add("TERRAFORMABLE")
            if "Water world" in body["type"]:
                flags.add("WW")
            if "Ammonia" in body["type"]:
                flags.add("AW")

            # Nur wichtige Körper speichern (mit Wert oder Signalen)
            if body_value > 0 or body.get("bio_signals", 0) > 0:
                important_bodies.append({
                    "name": body["name"],
                    "type": body["type"],
                    "value": body_value,
                    "value_formatted": format_credits(body_value),
                    "bio_signals": body.get("bio_signals", 0),
                    "geo_signals": body.get("geo_signals", 0),
                    "landable": body.get("landable", False),
                    "scanned_dss": body.get("scanned_dss", False),
                    "terraformable": "Terraformable" in body.get("type", "")
                })

        self.data["systems"][key] = {
            "name": state.current_system,
            "star_class": state.current_star_class,
            "visited": datetime.now().isoformat(timespec="seconds"),
            "total_value": total_value,
            "total_value_formatted": format_credits(total_value),
            "bodies": important_bodies,
            "flags": sorted(flags)
        }

        self.save()

        # Optional: Info ausgeben
        print(f"\n💾 System gespeichert: {state.current_system}")
        print(f"   Geschätzter Wert: {format_credits(total_value)}")
        if flags:
            print(f"   Flags: {', '.join(sorted(flags))}")
