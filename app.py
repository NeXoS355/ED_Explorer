import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from persistence import ExplorationCache
from planet_values import calculate_system_value, calculate_body_value
from UI import SystemHeader, UnifiedSystemsTree, CompactSystemsTree
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.binding import Binding
from textual import work

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
                # 🔍 EXISTIERENDE DATEN ERHALTEN
                for key in [
                    "bio_signals", "geo_signals", "human_signals",
                    "guardian_signals", "thargoid_signals", "other_signals",
                    "scanned_fss", "scanned_dss",
                    "bio_details", "scanned_genomes"
                ]:
                    if key in body and body[key]:
                        body_data[key] = body[key]

                self.current_system.bodies[i] = body_data
                self.current_system.bodies[i]["value"] = calculate_body_value(
                    body_data,
                    body_data.get("scanned_dss", False)
                )
                self.current_system.total_value = calculate_system_value(self.current_system.bodies)
                return

        # Neuer Body
        body_data.setdefault("bio_details", [])
        body_data.setdefault("scanned_genomes", set())

        body_data["value"] = calculate_body_value(body_data, body_data.get("scanned_dss", False))
        self.current_system.bodies.append(body_data)
        self.current_system.total_value = calculate_system_value(self.current_system.bodies)


# =============================================================
# APP
# =============================================================

class ExplorerApp(App):
    CSS = """
    SystemHeader {
        height: auto;
        background: $boost;
        padding: 1;
        border: solid cyan;
    }
    UnifiedSystemsTree {
        height: 1fr;
        border: solid magenta;
    }
    CompactSystemsTree {
        height: 1fr;
        border: solid yellow;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        ("c", "collapse_all", "Collapse"),
        ("e", "expand_all", "Expand"),
        ("v", "toggle_view", "Toggle View"),
    ]

    def __init__(self):
        super().__init__()
        self.state = ExplorationState()
        self.cache = ExplorationCache(Path.home() / ".elite_explorer_cache.json")
        self.journal_path = None
        self.compact_view = False  # Toggle zwischen UnifiedSystemsTree und CompactSystemsTree

    def compose(self) -> ComposeResult:
        yield Header()
        yield SystemHeader(self.state)
        yield UnifiedSystemsTree(self.state)
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

        if evt == "ScanOrganic":
            # Bio-Scan Event: Markiere Genus als gescannt
            body_name = event.get("Body")
            genus = event.get("Genus_Localised", event.get("Genus", "Unknown"))

            if self.state.current_system and body_name:
                for body in self.state.current_system.bodies:
                    if body["name"] == body_name:
                        if "scanned_genomes" not in body:
                            body["scanned_genomes"] = set()
                        body["scanned_genomes"].add(genus)
                        return True
            return False

        return False

    def handle_signals(self, event: dict):
        if not self.state.current_system:
            return
        signals = event.get("Signals", [])
        body_name = event.get("BodyName", "")
        genuses = event.get("Genuses", [])

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
                    body.setdefault("bio_details", [])
                    body.setdefault("scanned_genomes", set())

                    for genome in bio_details:
                        if genome not in body["bio_details"]:
                            body["bio_details"].append(genome)
                found = True
                break

        if not found and any(counts.values()):
            new_body = {
                "name": body_name, "type": "Unbekannt", "bio_signals": counts["bio"],
                "geo_signals": counts["geo"], "human_signals": counts["human"],
                "guardian_signals": counts["guardian"], "thargoid_signals": counts["thargoid"],
                "other_signals": counts["other"], "distance": 0, "gravity": 0,
                "landable": False,"terraform_state": "" ,"materials": [], "bio_details": bio_details if bio_details else [],
                "scanned_genomes": set(), "scanned_fss": False,
                "scanned_dss": False, "value": 0, "icon": "◯", "style": None, "urgency": "normal"
            }
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
            "landable": scan.get("Landable", False), "terraform_state": terraform,"materials": materials, "bio_details": [],
            "scanned_genomes": set(),
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
        try:
            tree = self.query_one(UnifiedSystemsTree)
            tree.update_systems()
        except:
            try:
                tree = self.query_one(CompactSystemsTree)
                tree.update_systems()
            except:
                pass

    def action_refresh(self):
        self.refresh_ui()
        self.notify("✓ UI aktualisiert")

    def action_collapse_all(self):
        try:
            self.query_one(UnifiedSystemsTree).root.collapse_all()
        except:
            try:
                self.query_one(CompactSystemsTree).root.collapse_all()
            except:
                pass
        self.notify("✓ Alle zugeklappt")

    def action_expand_all(self):
        try:
            self.query_one(UnifiedSystemsTree).root.expand_all()
        except:
            try:
                self.query_one(CompactSystemsTree).root.expand_all()
            except:
                pass
        self.notify("✓ Alle aufgeklappt")

    def action_toggle_view(self):
        """Wechselt zwischen Unified und Compact View"""
        self.compact_view = not self.compact_view

        # Entferne aktuellen Tree
        try:
            self.query_one(UnifiedSystemsTree).remove()
        except:
            pass
        try:
            self.query_one(CompactSystemsTree).remove()
        except:
            pass

        # Füge neuen Tree hinzu
        if self.compact_view:
            new_tree = CompactSystemsTree(self.state)
            self.notify("✓ Compact View")
        else:
            new_tree = UnifiedSystemsTree(self.state)
            self.notify("✓ Detailed View")

        # Einfügen nach Header
        self.mount(new_tree, after=self.query_one(SystemHeader))
        new_tree.update_systems()


def main():
    ExplorerApp().run()

if __name__ == "__main__":
    main()
