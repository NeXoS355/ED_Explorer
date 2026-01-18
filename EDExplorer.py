#!/usr/bin/env python3

import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Tree, DataTable
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.reactive import reactive
from textual.binding import Binding
from textual import work
from persistence import ExplorationCache
from planet_values import calculate_system_value, calculate_body_value

# =============================================================
# KONFIGURATION
# =============================================================

JOURNAL_DIR = Path(
    "/linuxGames/SteamLibrary/steamapps/compatdata/359320/pfx/"
    "drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous"
)

NAV_ROUTE_FILE = JOURNAL_DIR / "NavRoute.json"
STATUS_FILE = JOURNAL_DIR / "Status.json"
SCOOPABLE_STARS = {"O", "B", "A", "F", "G", "K", "M"}

# =============================================================
# STATE
# =============================================================

class SystemData:
    """Daten für ein einzelnes System"""
    def __init__(self, name, star_class=None, system_address=None):
        self.name = name
        self.star_class = star_class
        self.system_address = system_address
        self.bodies = []
        self.total_value = 0
        self.dss_used = False
        self.timestamp = datetime.now()

class ExplorationState:
    def __init__(self):
        self.systems = []
        self.current_system = None
        self.session_start = datetime.now()
        self.next_route_system = None
        self.next_route_star_class = None
        self.remaining_jumps = 0

    def new_system(self, name, star_class=None, system_address=None):
        if self.current_system is not None and len(self.current_system.bodies) > 0:
            self.systems.insert(0, self.current_system)
        self.current_system = SystemData(name, star_class, system_address)

    def update_route(self):
        if self.current_system is None:
            return
        try:
            destination_address = None
            if STATUS_FILE.exists():
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                    destination = status_data.get("Destination", {})
                    destination_address = destination.get("System", None)
            if NAV_ROUTE_FILE.exists() and destination_address:
                with open(NAV_ROUTE_FILE, "r", encoding="utf-8") as f:
                    route_data = json.load(f)
                    route = route_data.get("Route", [])
                    current_index = -1
                    for i, system in enumerate(route):
                        if system.get("SystemAddress") == self.current_system.system_address:
                            current_index = i
                            break
                    if current_index >= 0:
                        self.remaining_jumps = len(route) - current_index - 1
                    else:
                        self.remaining_jumps = len(route)
                    for system in route:
                        sys_addr = system.get("SystemAddress")
                        if sys_addr == destination_address and sys_addr != self.current_system.system_address:
                            self.next_route_system = system.get("StarSystem", "Unbekannt")
                            self.next_route_star_class = system.get("StarClass", None)
                            return
                    self.next_route_system = None
                    self.next_route_star_class = None
            else:
                self.next_route_system = None
                self.next_route_star_class = None
                self.remaining_jumps = 0
        except Exception:
            self.next_route_system = None
            self.next_route_star_class = None
            self.remaining_jumps = 0

    def add_body(self, body_data):
        if self.current_system is None:
            return
        for i, body in enumerate(self.current_system.bodies):
            if body["name"] == body_data["name"]:
                for key in ["bio_signals", "geo_signals", "human_signals", "guardian_signals", "thargoid_signals", "other_signals", "scanned_fss", "scanned_dss"]:
                    if body.get(key):
                        body_data[key] = body[key]
                self.current_system.bodies[i] = body_data
                self.current_system.bodies[i]["value"] = calculate_body_value(body_data, body_data.get("scanned_dss", False))
                self.current_system.total_value = calculate_system_value(self.current_system.bodies)
                return
        body_data["value"] = calculate_body_value(body_data, body_data.get("scanned_dss", False))
        self.current_system.bodies.append(body_data)
        self.current_system.total_value = calculate_system_value(self.current_system.bodies)

# =============================================================
# WIDGETS
# =============================================================

class SystemHeader(Static):
    def __init__(self, state: ExplorationState):
        super().__init__()
        self.state = state

    def render(self) -> str:
        session_duration = datetime.now() - self.state.session_start
        hours = int(session_duration.total_seconds() // 3600)
        minutes = int((session_duration.total_seconds() % 3600) // 60)

        lines = ["🚀 Elite Dangerous Explorer", ""]

        if self.state.current_system is None:
            lines.append("System: Unbekannt")
            return "\n".join(lines)

        system_line = f"System: {self.state.current_system.name}"
        if self.state.current_system.dss_used:
            system_line += " 💾"
        if self.state.current_system.star_class:
            is_scoopable = self.state.current_system.star_class in SCOOPABLE_STARS
            scoop_indicator = "⛽" if is_scoopable else "✗"
            system_line += f" ({self.state.current_system.star_class} {scoop_indicator})"
        lines.append(system_line)

        if self.state.next_route_system:
            route_line = f"→  {self.state.next_route_system}"
            if self.state.next_route_star_class:
                is_next_scoopable = self.state.next_route_star_class in SCOOPABLE_STARS
                next_scoop = "⛽" if is_next_scoopable else "✗"
                route_line += f" ({self.state.next_route_star_class} {next_scoop})"
            lines.append(route_line)

        stats_line = f"Session: {hours:02d}:{minutes:02d}"
        if self.state.remaining_jumps > 0:
            stats_line += f"  |  Sprünge: {self.state.remaining_jumps}"
        lines.append(stats_line)
        lines.append(f"est. System Value: {self.state.current_system.total_value:,} cr")

        return "\n".join(lines)

class SystemsTree(Tree):
    def __init__(self, state: ExplorationState):
        super().__init__("Besuchte Systeme")
        self.state = state
        self.root.expand()

    def update_systems(self):
        self.clear()
        total = len(self.state.systems) + (1 if self.state.current_system else 0)
        self.root.label = f"Besuchte Systeme ({total})"

        if self.state.current_system:
            self._add_system(self.state.current_system, True)
        for system in self.state.systems:
            self._add_system(system, False)

    def _add_system(self, system: SystemData, is_current: bool):
        dss = " 💾" if system.dss_used else ""
        current = " [AKTUELL]" if is_current else ""
        label = f"{system.name} ({len(system.bodies)}){dss}{current} - {system.total_value:,} cr"
        node = self.root.add(label, expand=is_current)

        if len(system.bodies) == 0:
            node.add_leaf("Keine Körper")
            return

        sorted_bodies = sorted(system.bodies, key=lambda b: (
            1000 if "Earthlike" in b["type"] else
            900 if "Water" in b["type"] else
            800 if "Ammonia" in b["type"] else
            700 if "Terraformable" in b["type"] else 0
        ) + b.get("bio_signals", 0) * 100, reverse=True)

        for body in sorted_bodies:
            icon = body.get("icon", "◯")
            name = body["name"]
            body_type = body["type"]
            value = body.get("value", 0)

            scanned = ""
            if body.get("scanned_fss"):
                scanned += "F"
            if body.get("scanned_dss"):
                scanned += "D"
            scan_str = f"[{scanned}]" if scanned else ""

            label = f"{icon} {name} {scan_str} - {body_type} - {value:,} cr"
            body_node = node.add(label, expand=False)

            for sig_type, emoji, key in [
                ("Biological", "🧬", "bio_signals"),
                ("Geological", "🌋", "geo_signals"),
                ("Human", "👤", "human_signals"),
                ("Guardian", "🛡️", "guardian_signals"),
                ("Thargoid", "👽", "thargoid_signals"),
                ("Other", "❓", "other_signals")
            ]:
                count = body.get(key, 0)
                if count > 0:
                    signal_label = f"{emoji} {sig_type} Signals: {count}"
                    signal_node = body_node.add_leaf(signal_label)

                    # Bei Bio-Signalen: Genus-Details anzeigen
                    if key == "bio_signals" and body.get("bio_details"):
                        for genus in body.get("bio_details", []):
                            body_node.add_leaf(f"  └─ {genus}")

            distance = body.get("distance", 0)
            if distance > 0:
                body_node.add_leaf(f"📍 Distance: {distance:,.0f} Ls")

            gravity = body.get("gravity", 0)
            if gravity > 0:
                body_node.add_leaf(f"⚖️ Gravity: {gravity:.2f}g")

            if body.get("landable"):
                body_node.add_leaf("✓ Landable")

            materials = body.get("materials", [])
            if materials:
                sorted_mats = sorted(materials, key=lambda x: x["percent"], reverse=True)[:5]
                mat_node = body_node.add("📦 Materials")
                for mat in sorted_mats:
                    mat_node.add_leaf(f"  {mat['name']}: {mat['percent']:.1f}%")

class BodiesTable(DataTable):
    def __init__(self, state: ExplorationState):
        super().__init__()
        self.state = state
        self.cursor_type = "row"
        self.add_column("Body", width=25)
        self.add_column("Type", width=25)
        self.add_column("Scan", width=6)
        self.add_column("Signals", width=18)
        self.add_column("G", width=5)
        self.add_column("L", width=3)
        self.add_column("Value", width=12)
        self.add_column("Distance", width=10)

    def update_bodies(self):
        self.clear()

        if self.state.current_system is None or len(self.state.current_system.bodies) == 0:
            self.add_row("—", "Keine Körper gescannt", "—", "—", "—", "—", "—", "—")
            return

        sorted_bodies = sorted(self.state.current_system.bodies, key=lambda b: (
            1000 if "Earthlike" in b["type"] else
            900 if "Water" in b["type"] else
            800 if "Ammonia" in b["type"] else
            700 if "Terraformable" in b["type"] else 0
        ) + b.get("bio_signals", 0) * 100, reverse=True)

        for body in sorted_bodies:
            name = body["name"]
            icon = body.get("icon", "◯")
            type_str = f"{icon} {body['type']}"

            scan = ("F" if body.get("scanned_fss") else "-") + "/" + ("D" if body.get("scanned_dss") else "-")

            signals = []
            for emoji, key in [("🧬", "bio_signals"), ("🌋", "geo_signals"), ("👤", "human_signals"),
                               ("🛡️", "guardian_signals"), ("👽", "thargoid_signals"), ("❓", "other_signals")]:
                count = body.get(key, 0)
                if count > 0:
                    signals.append(f"{emoji}{count}")
            signals_str = " ".join(signals) if signals else "—"

            gravity = body.get("gravity", 0)
            gravity_str = f"{gravity:.2f}" if gravity > 0 else "—"

            landable_str = "✓" if body.get("landable") else "✗"

            value = body.get("value", 0)
            value_str = f"{value:,} cr" if value > 0 else "—"

            distance = body.get("distance", 0)
            distance_str = f"{distance:,.0f} Ls" if distance > 0 else "—"

            self.add_row(name, type_str, scan, signals_str, gravity_str, landable_str, value_str, distance_str)

class ExplorerApp(App):
    CSS = """
    SystemHeader {
        height: auto;
        background: $boost;
        padding: 1;
        border: solid cyan;
    }
    SystemsTree {
        height: 1fr;
        border: solid magenta;
    }
    BodiesTable {
        height: 1fr;
        border: solid yellow;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        ("c", "collapse_all", "Collapse"),
        ("e", "expand_all", "Expand"),
    ]

    def __init__(self):
        super().__init__()
        self.state = ExplorationState()
        self.cache = ExplorationCache(Path.home() / ".elite_explorer_cache.json")
        self.journal_path = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield SystemHeader(self.state)
        yield SystemsTree(self.state)
        yield BodiesTable(self.state)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Elite Dangerous Explorer"
        try:
            self.journal_path = max(JOURNAL_DIR.glob("Journal.*.log"), key=lambda f: f.stat().st_mtime)
            self.initialize_state()
            self.refresh_ui()
        except Exception as e:
            self.notify(f"❌ Fehler: {e}", severity="error")
            return
        self.watch_journal()

    def initialize_state(self):
        with open(self.journal_path, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                try:
                    event = json.loads(line)
                    if event.get("event") == "Location":
                        self.state.new_system(event.get("StarSystem", "Unbekannt"),
                                             event.get("StarClass"), event.get("SystemAddress"))
                        self.state.update_route()
                        return
                except:
                    pass

    @work(exclusive=True)
    async def watch_journal(self):
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.5)
                        continue
                    try:
                        event = json.loads(line)
                        if self.handle_event(event):
                            self.refresh_ui()
                    except:
                        pass
        except Exception as e:
            self.notify(f"❌ Journal-Fehler: {e}", severity="error")

    def handle_event(self, event: dict) -> bool:
        evt = event.get("event")

        if evt == "FSDJump" or evt == "Location":
            self.state.new_system(event.get("StarSystem", "Unbekannt"),
                                 event.get("StarClass"), event.get("SystemAddress"))
            if evt == "FSDJump":
                time.sleep(1)
            self.state.update_route()
            return True

        if evt == "Scan" and event.get("ScanType") in ["Detailed", "AutoScan", "Basic", "NavBeaconDetail"]:
            body_data = self.evaluate_planet(event)
            body_data["scanned_fss"] = True
            self.state.add_body(body_data)
            return True

        if evt in ["FSSBodySignals", "SAASignalsFound"]:
            self.handle_signals(event)
            return True

        if evt == "SAAScanComplete":
            if self.state.current_system:
                self.state.current_system.dss_used = True
                for body in self.state.current_system.bodies:
                    if body["name"] == event.get("BodyName"):
                        body["scanned_dss"] = True
                        body["value"] = calculate_body_value(body, True)
                self.state.current_system.total_value = calculate_system_value(self.state.current_system.bodies)
            return True

        return False

    def handle_signals(self, event: dict):
        if not self.state.current_system:
            return
        signals = event.get("Signals", [])
        body_name = event.get("BodyName", "")
        genuses = event.get("Genuses", [])  # Für SAASignalsFound

        counts = {"bio": 0, "geo": 0, "human": 0, "guardian": 0, "thargoid": 0, "other": 0}
        bio_details = []

        # Genus-Informationen sammeln
        for genus in genuses:
            genus_name = genus.get("Genus_Localised", genus.get("Genus", "Unknown"))
            bio_details.append(genus_name)

        for sig in signals:
            st = sig.get("Type", "")
            c = sig.get("Count", 0)
            if "Biological" in st:
                counts["bio"] = c
            elif "Geological" in st:
                counts["geo"] = c
            elif "Human" in st:
                counts["human"] = c
            elif "Guardian" in st:
                counts["guardian"] = c
            elif "Thargoid" in st:
                counts["thargoid"] = c
            else:
                counts["other"] += c

        found = False
        for body in self.state.current_system.bodies:
            if body["name"] == body_name:
                for k, v in counts.items():
                    body[f"{k}_signals"] = v
                if bio_details:
                    body["bio_details"] = bio_details
                found = True
                break

        if not found and any(counts.values()):
            new_body = {
                "name": body_name, "type": "Unbekannt", "bio_signals": counts["bio"],
                "geo_signals": counts["geo"], "human_signals": counts["human"],
                "guardian_signals": counts["guardian"], "thargoid_signals": counts["thargoid"],
                "other_signals": counts["other"], "distance": 0, "gravity": 0,
                "landable": False, "materials": [], "scanned_fss": False,
                "scanned_dss": False, "value": 0, "icon": "◯", "style": None, "urgency": "normal"
            }
            if bio_details:
                new_body["bio_details"] = bio_details
            self.state.add_body(new_body)

    def evaluate_planet(self, scan: dict) -> dict:
        planet = scan.get("PlanetClass", "")
        star_type = scan.get("StarType", "")
        terraform = scan.get("TerraformState", "")
        body_name = scan.get("BodyName", "Unbekannt")

        materials = [{"name": m.get("Name", "").replace("_name", ""), "percent": m.get("Percent", 0)}
                    for m in scan.get("Materials", [])]

        body_data = {
            "name": body_name, "type": planet, "bio_signals": 0, "geo_signals": 0,
            "human_signals": 0, "guardian_signals": 0, "thargoid_signals": 0, "other_signals": 0,
            "distance": scan.get("DistanceFromArrivalLS", 0),
            "gravity": scan.get("SurfaceGravity", 0) / 9.81 if scan.get("SurfaceGravity") else 0,
            "landable": scan.get("Landable", False), "materials": materials,
            "scanned_fss": False, "scanned_dss": False, "value": 0, "icon": "◯",
            "style": None, "urgency": "normal"
        }

        if "Belt Cluster" in body_name:
            body_data.update({"icon": "🪨", "type": "Asteroid Cluster"})
        elif star_type:
            body_data.update({"icon": "⭐", "type": f"Star Class {star_type}"})
        elif planet == "Earthlike body":
            body_data.update({"icon": "🌍", "type": "Earthlike World", "urgency": "critical"})
        elif planet == "Water world":
            body_data.update({"icon": "💧", "type": f"Water World{' (Terraformable)' if terraform == 'Terraformable' else ''}", "urgency": "critical" if terraform == "Terraformable" else "normal"})
        elif terraform == "Terraformable":
            body_data.update({"icon": "🛸", "type": f"{planet} (Terraformable)"})
        elif planet == "Ammonia world":
            body_data.update({"icon": "☢", "type": "Ammonia World"})

        body_data["value"] = calculate_body_value(body_data, False)
        return body_data

    def refresh_ui(self):
        self.query_one(SystemHeader).refresh()
        self.query_one(SystemsTree).update_systems()
        self.query_one(BodiesTable).update_bodies()

    def action_refresh(self):
        self.refresh_ui()
        self.notify("✓ UI aktualisiert")

    def action_collapse_all(self):
        self.query_one(SystemsTree).root.collapse_all()
        self.notify("✓ Alle zugeklappt")

    def action_expand_all(self):
        self.query_one(SystemsTree).root.expand_all()
        self.notify("✓ Alle aufgeklappt")

def main():
    ExplorerApp().run()

if __name__ == "__main__":
    main()
