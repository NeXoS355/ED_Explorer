#!/usr/bin/env python3

import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Console
from rich.text import Text
from persistence import ExplorationCache
from planet_values import calculate_system_value,calculate_body_value

# =============================================================
# KONFIGURATION
# =============================================================

JOURNAL_DIR = Path(
    "/linuxGames/SteamLibrary/steamapps/compatdata/359320/pfx/"
    "drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous"
)

NAV_ROUTE_FILE = JOURNAL_DIR / "NavRoute.json"
STATUS_FILE = JOURNAL_DIR / "Status.json"

OVERLAY_TIMEOUT_MS = 8000

# Fuel Scoop-fähige Sternklassen (KGBFOAM)
SCOOPABLE_STARS = {"O", "B", "A", "F", "G", "K", "M"}

# =============================================================
# STATE
# =============================================================

class ExplorationState:
    def __init__(self):
        self.current_system = "Unbekannt"
        self.current_system_address = None
        self.current_star_class = None
        self.bodies = []
        self.session_start = datetime.now()
        self.next_route_system = None
        self.next_route_star_class = None
        self.remaining_jumps = 0
        self.dss_used = False
        self.total_value = 0
        self.system_signals = []  # Für FSSSignalDiscovered

    def new_system(self, name, star_class=None, system_address=None):
        """Neues System → State zurücksetzen"""
        self.current_system = name
        self.current_star_class = star_class
        self.current_system_address = system_address
        self.bodies = []

    def update_route(self):
        """NavRoute.json und Status.json einlesen und nächstes Ziel bestimmen"""
        try:
            # Destination aus Status.json lesen
            destination_address = None
            if STATUS_FILE.exists():
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                    destination = status_data.get("Destination", {})
                    destination_address = destination.get("System", None)

            # Route aus NavRoute.json lesen
            if NAV_ROUTE_FILE.exists() and destination_address:
                with open(NAV_ROUTE_FILE, "r", encoding="utf-8") as f:
                    route_data = json.load(f)
                    route = route_data.get("Route", [])

                    # Finde das aktuelle System in der Route
                    current_index = -1
                    for i, system in enumerate(route):
                        if system.get("SystemAddress") == self.current_system_address:
                            current_index = i
                            break

                    # Berechne verbleibende Sprünge (vom aktuellen System bis zum Ende)
                    if current_index >= 0:
                        self.remaining_jumps = len(route) - current_index - 1
                    else:
                        # Aktuelles System nicht in Route gefunden, nimm Gesamtanzahl
                        self.remaining_jumps = len(route)

                    # Finde das System in der Route mit der passenden SystemAddress
                    # ABER: Überspringe das aktuelle System
                    for system in route:
                        sys_addr = system.get("SystemAddress")
                        # Nur anzeigen wenn es NICHT das aktuelle System ist
                        if sys_addr == destination_address and sys_addr != self.current_system_address:
                            self.next_route_system = system.get("StarSystem", "Unbekannt")
                            self.next_route_star_class = system.get("StarClass", None)
                            return

                    # Falls nicht gefunden oder aktuelles System, Route leer
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
        """Körper zur Liste hinzufügen oder aktualisieren"""
        # Prüfen ob Körper bereits existiert
        for i, body in enumerate(self.bodies):
            if body["name"] == body_data["name"]:
                # Aktualisieren - BEHALTE aber die Signal-Daten und Scan-Status!
                # FSSBodySignals kommt vor Scan, also Signale nicht überschreiben
                existing_bio = body.get("bio_signals", 0)
                existing_geo = body.get("geo_signals", 0)
                existing_human = body.get("human_signals", 0)
                existing_guardian = body.get("guardian_signals", 0)
                existing_thargoid = body.get("thargoid_signals", 0)
                existing_other = body.get("other_signals", 0)
                existing_fss = body.get("scanned_fss", False)
                existing_dss = body.get("scanned_dss", False)

                self.bodies[i] = body_data

                # Werte wiederherstellen falls sie vorher gesetzt waren
                if existing_bio > 0:
                    self.bodies[i]["bio_signals"] = existing_bio
                if existing_geo > 0:
                    self.bodies[i]["geo_signals"] = existing_geo
                if existing_human > 0:
                    self.bodies[i]["human_signals"] = existing_human
                if existing_guardian > 0:
                    self.bodies[i]["guardian_signals"] = existing_guardian
                if existing_thargoid > 0:
                    self.bodies[i]["thargoid_signals"] = existing_thargoid
                if existing_other > 0:
                    self.bodies[i]["other_signals"] = existing_other
                if existing_fss:
                    self.bodies[i]["scanned_fss"] = existing_fss
                if existing_dss:
                    self.bodies[i]["scanned_dss"] = existing_dss

                # Wert NEU BERECHNEN mit aktuellem DSS-Status
                self.bodies[i]["value"] = calculate_body_value(
                    self.bodies[i],
                    has_dss=self.bodies[i]["scanned_dss"]
                )

                # Systemwert neu berechnen
                self.total_value = calculate_system_value(self.bodies)
                return

        # Neukalkulieren des Planeten beim Hinzufügen
        body_data["value"] = calculate_body_value(body_data, body_data.get("scanned_dss", False))
        # Neu hinzufügen
        self.bodies.append(body_data)
        # Neukalkulieren des Systemwerts
        self.total_value = calculate_system_value(self.bodies)

# =============================================================
# UI RENDERING
# =============================================================

def create_header(state: ExplorationState) -> Panel:
    """Header mit Systemname, Sternklasse, Route und Session-Info"""
    session_duration = datetime.now() - state.session_start
    hours = int(session_duration.total_seconds() // 3600)
    minutes = int((session_duration.total_seconds() % 3600) // 60)

    header_text = Text()
    header_text.append("🚀 Elite Dangerous Explorer\n", style="bold cyan")

    # Aktuelles System mit Sternklasse
    header_text.append("System: ", style="white")
    header_text.append(f"{state.current_system}", style="bold yellow")

    if state.dss_used:
         header_text.append(" 💾", style="green")

    if state.current_star_class:
        is_scoopable = state.current_star_class in SCOOPABLE_STARS
        scoop_indicator = "⛽" if is_scoopable else "✗"
        scoop_style = "green" if is_scoopable else "red"
        header_text.append(f" ({state.current_star_class} ", style="white")
        header_text.append(scoop_indicator, style=scoop_style)
        header_text.append(")", style="white")

    # Nächstes Routenziel
    if state.next_route_system:
        header_text.append(f"  →  ", style="dim white")
        header_text.append(f"{state.next_route_system}", style="bold cyan")

        if state.next_route_star_class:
            is_next_scoopable = state.next_route_star_class in SCOOPABLE_STARS
            next_scoop = "⛽" if is_next_scoopable else "✗"
            next_scoop_style = "green" if is_next_scoopable else "red"
            header_text.append(f" ({state.next_route_star_class} ", style="white")
            header_text.append(next_scoop, style=next_scoop_style)
            header_text.append(")", style="white")

    # Verbleibende Sprünge
    if state.remaining_jumps > 0:
        header_text.append(f"  |  ", style="dim white")
        header_text.append(f"Sprünge: ", style="white")
        header_text.append(f"{state.remaining_jumps}", style="bold magenta")

    header_text.append(f"  |  Session: {hours:02d}:{minutes:02d}\n", style="dim white")

    header_text.append("est. System Value: ", style="white")
    header_text.append(f"{state.total_value:,} cr", style="bold yellow")

    return Panel(header_text, border_style="cyan")


def create_body_table(state: ExplorationState) -> Table:
    """Tabelle mit allen gescannten Körpern"""
    table = Table(show_header=True, header_style="bold magenta", expand=True)

    table.add_column("Body", style="cyan", width=25)
    table.add_column("Type", style="white", width=20)
    table.add_column("Scan", style="white", width=3)
    table.add_column("Signals", justify="center", style="white", width=15)
    table.add_column("Gravity", justify="center", style="white", width=3)
    table.add_column("Landable", justify="center", style="white", width=3)
    table.add_column("Materials", style="dim white", width=25)
    table.add_column("Value", justify="center", style="yellow", width=10)
    table.add_column("Distance", justify="right", style="yellow", width=8)

    if not state.bodies:
        table.add_row("—", "Keine Körper gescannt", "—", "—", "—", "—", "—", "—", "—")
        return table

    # Sortiere Körper nach Wichtigkeit
    def get_priority(body):
        """Berechne Priorität für Sortierung (höher = wichtiger)"""
        priority = 0

        # Wichtige Planeten-Typen
        if "Earthlike" in body["type"]:
            priority += 1000
        elif "Water" in body["type"]:
            priority += 900
        elif "Ammonia" in body["type"]:
            priority += 800
        elif "Terraformable" in body["type"]:
            priority += 700

        # Signale nach Wichtigkeit gewichten
        priority += body.get("bio_signals", 0) * 100      # Bio am wichtigsten
        priority += body.get("guardian_signals", 0) * 80   # Guardian sehr wichtig
        priority += body.get("thargoid_signals", 0) * 70   # Thargoid wichtig
        priority += body.get("human_signals", 0) * 50      # Human interessant
        priority += body.get("geo_signals", 0) * 10        # Geo weniger wichtig
        priority += body.get("other_signals", 0) * 5       # Andere am wenigsten

        return priority

    # Sortiere nach Priorität (wichtigste zuerst)
    sorted_bodies = sorted(state.bodies, key=get_priority, reverse=True)

    # Begrenze auf die ersten 30 Einträge (oder weniger wenn Terminal klein ist)
    max_rows = 30
    display_bodies = sorted_bodies[:max_rows]

    for body in display_bodies:
        # Name
        name = body["name"]

        # Type mit Icon
        type_str = body["type"]
        icon = body.get("icon", "●")
        type_display = f"{icon} {type_str}"

        # Scanned By - mit .get() für sichere Abfrage
        scanned_fss = body.get("scanned_fss", False)
        scanned_dss = body.get("scanned_dss", False)

        scan_str = ""
        if scanned_fss:
            scan_str += "[cyan]F[/cyan]"
        else:
            scan_str += "[dim]-[/dim]"

        scan_str += "/"

        if scanned_dss:
            scan_str += "[green]D[/green]"
        else:
            scan_str += "[dim]-[/dim]"

        # Signals (Bio, Geo, Human, Guardian, Thargoid, Other)
        signals_parts = []
        bio_count = body.get("bio_signals", 0)
        geo_count = body.get("geo_signals", 0)
        human_count = body.get("human_signals", 0)
        guardian_count = body.get("guardian_signals", 0)
        thargoid_count = body.get("thargoid_signals", 0)
        other_count = body.get("other_signals", 0)

        if bio_count > 0:
            signals_parts.append(f"[green]🧬{bio_count}[/green]")
        if geo_count > 0:
            signals_parts.append(f"[yellow]🌋{geo_count}[/yellow]")
        if human_count > 0:
            signals_parts.append(f"[cyan]👤{human_count}[/cyan]")
        if guardian_count > 0:
            signals_parts.append(f"[blue]🛡️{guardian_count}[/blue]")
        if thargoid_count > 0:
            signals_parts.append(f"[red]👽{thargoid_count}[/red]")
        if other_count > 0:
            signals_parts.append(f"[dim]❓{other_count}[/dim]")

        signals_str = " ".join(signals_parts) if signals_parts else "—"

        # Gravity
        gravity = body.get("gravity", 0)
        gravity_str = f"{gravity:.2f}g" if gravity > 0 else "—"

        # Landable
        landable = body.get("landable", False)
        landable_str = "[green]✓[/green]" if landable else "[dim]✗[/dim]"

        # Materials (Top 3)
        materials = body.get("materials", [])
        if materials:
            # Sortiere nach Prozent und nimm die Top 3
            sorted_mats = sorted(materials, key=lambda x: x["percent"], reverse=True)[:3]
            materials_str = ", ".join([f"{m['name']} {m['percent']:.1f}%" for m in sorted_mats])
        else:
            materials_str = "—"

        # Body Value
        value = body.get("value", 0)
        value_str = f"{value:,} cr" if value > 0 else "—"

        # Distance from Arrival
        distance = body.get("distance", 0)
        distance_str = f"{distance:,.0f} Ls" if distance > 0 else "—"

        # Style basierend auf Wichtigkeit
        style = body.get("style", None)

        table.add_row(name, type_display, scan_str, signals_str, gravity_str, landable_str, materials_str, value_str, distance_str, style=style)

    # Info wenn mehr Körper vorhanden sind
    if len(sorted_bodies) > max_rows:
        remaining = len(sorted_bodies) - max_rows
        table.add_row(
            f"[dim]... und {remaining} weitere Körper[/dim]",
            "[dim](nur wichtigste angezeigt)[/dim]",
            "—", "—", "—", "—", "—", "—", "—",
            style="dim"
        )

    return table


def create_layout(state: ExplorationState) -> Layout:
    """Gesamtes Layout zusammenstellen"""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="body")
    )

    layout["header"].update(create_header(state))
    layout["body"].update(create_body_table(state))

    return layout

# =============================================================
# BEWERTUNG
# =============================================================

def evaluate_planet(scan: dict) -> dict:
    """Planet bewerten und Metadaten zurückgeben"""
    planet = scan.get("PlanetClass", "")
    star_type = scan.get("StarType", "")
    terraform = scan.get("TerraformState", "")
    body_name = scan.get("BodyName", "Unbekannt")

    # Materials verarbeiten
    materials = []
    if "Materials" in scan:
        for mat in scan["Materials"]:
            materials.append({
                "name": mat.get("Name", "").replace("_name", ""),
                "percent": mat.get("Percent", 0)
            })

    body_data = {
        "name": body_name,
        "type": planet,
        "bio_signals": 0,
        "geo_signals": 0,
        "human_signals": 0,
        "guardian_signals": 0,
        "thargoid_signals": 0,
        "other_signals": 0,
        "distance": scan.get("DistanceFromArrivalLS", 0),
        "gravity": scan.get("SurfaceGravity", 0) / 9.81 if scan.get("SurfaceGravity") else 0,
        "landable": scan.get("Landable", False),
        "materials": materials,
        "scanned_fss": False,
        "scanned_dss": False,
        "value": 0,
        "icon": "●",
        "style": None,
        "urgency": "normal"
    }

    body_data["value"] = calculate_body_value(body_data, False)

    # Belt Cluster erkennen
    if "Belt Cluster" in body_name:
        body_data["icon"] = "🪨"
        body_data["type"] = "Asteroid Cluster"
        body_data["style"] = "dim"
        return body_data

    # Stern erkennen
    if star_type:
        body_data["icon"] = "⭐"
        body_data["type"] = f"Star Class {star_type}"
        if star_type in SCOOPABLE_STARS:
            body_data["style"] = "bright_yellow"
        else:
            body_data["style"] = "dim yellow"
        return body_data

    # Earthlike
    if planet == "Earthlike body":
        body_data["icon"] = "🌍"
        body_data["type"] = "Earthlike World"
        body_data["style"] = "bold red"
        body_data["urgency"] = "critical"
        return body_data

    # Water World
    if planet == "Water world":
        body_data["icon"] = "💧"
        if terraform == "Terraformable":
            body_data["type"] = "Water World (Terraformable)"
            body_data["style"] = "bold red"
            body_data["urgency"] = "critical"
        else:
            body_data["type"] = "Water World"
            body_data["style"] = "magenta"
        return body_data

    # Terraformable
    if terraform == "Terraformable":
        body_data["icon"] = "🛸"
        body_data["type"] = f"{planet} (Terraformable)"
        body_data["style"] = "yellow"
        return body_data

    # Ammonia World
    if planet == "Ammonia world":
        body_data["icon"] = "☢"
        body_data["type"] = "Ammonia World"
        body_data["style"] = "cyan"
        return body_data

    # Standard
    return body_data


# =============================================================
# JOURNAL
# =============================================================

def follow(file):
    """Journal-Datei kontinuierlich lesen"""
    file.seek(0, 2)
    while True:
        line = file.readline()
        if not line:
            time.sleep(0.2)
            continue
        yield line


def get_latest_journal():
    """Neueste Journal-Datei finden"""
    journals = list(JOURNAL_DIR.glob("Journal.*.log"))
    if not journals:
        raise RuntimeError("❌ Keine Journal-Dateien gefunden!")
    return max(journals, key=lambda f: f.stat().st_mtime)

# =============================================================
# EVENT HANDLER
# =============================================================

def handle_event(event: dict, state: ExplorationState, cache: ExplorationCache) -> bool:
    """Event verarbeiten und State aktualisieren. Returns True wenn UI-Update nötig"""
    evt = event.get("event")

    # FSD Jump started
    if evt == "FSDTarget":
        if state.dss_used:
            cache.store_system(state)

    # FSD Jump finished
    if evt == "FSDJump":
        system_name = event.get("StarSystem", "Unbekannt")
        star_class = event.get("StarClass", None)
        system_address = event.get("SystemAddress", None)
        # Erst System setzen, DANN Route updaten (sonst vergleich mit alten Daten)
        state.current_system = system_name
        state.current_star_class = star_class
        state.current_system_address = system_address
        state.total_value = 0
        state.bodies = []
        state.dss_used = False
        # 1 Sekunde warten damit Status.json aktualisiert wird
        time.sleep(1)
        state.update_route()
        return True

    # Location → Beim Start (bereits im System)
    if evt == "Location":
        system_name = event.get("StarSystem", "Unbekannt")
        star_class = event.get("StarClass", None)
        system_address = event.get("SystemAddress", None)
        # Erst System setzen, DANN Route updaten
        state.current_system = system_name
        state.current_star_class = star_class
        state.current_system_address = system_address
        state.total_value = 0
        state.bodies = []
        state.update_route()
        return True

    # Scan → Planet gescannt
    if evt == "Scan":
        scan_type = event.get("ScanType", "")

        # Nur DetailedSurface und AutoScan interessieren uns
        if scan_type in ["Detailed", "AutoScan", "Basic", "NavBeaconDetail"]:
            body_data = evaluate_planet(event)
            body_data["scanned_fss"] = True
            state.add_body(body_data)
            return True

    # FSSSignalDiscovered → System-weite Signale (Installationen, etc.)
    if evt == "FSSSignalDiscovered":
        signal_name = event.get("SignalName", "Unknown")
        signal_type = event.get("SignalType", "Unknown")

        # Speichere Signal in System-Liste (optional für spätere Anzeige)
        state.system_signals.append({
            "name": signal_name,
            "type": signal_type
        })

        return True

    # FSSBodySignals → Bio/Geo/Human/etc-Signale gefunden (kommt VOR Scan!)
    if evt == "FSSBodySignals":
        signals = event.get("Signals", [])
        body_name = event.get("BodyName", "Unbekannt")

        signal_counts = {
            "bio": 0,
            "geo": 0,
            "human": 0,
            "guardian": 0,
            "thargoid": 0,
            "other": 0
        }

        for signal in signals:
            signal_type = signal.get("Type", "")
            count = signal.get("Count", 0)

            # Klassifiziere Signal-Typ
            if "Biological" in signal_type or signal_type == "$SAA_SignalType_Biological;":
                signal_counts["bio"] = count
            elif "Geological" in signal_type or signal_type == "$SAA_SignalType_Geological;":
                signal_counts["geo"] = count
            elif "Human" in signal_type or signal_type == "$SAA_SignalType_Human;":
                signal_counts["human"] = count
            elif "Guardian" in signal_type or signal_type == "$SAA_SignalType_Guardian;":
                signal_counts["guardian"] = count
            elif "Thargoid" in signal_type or signal_type == "$SAA_SignalType_Thargoid;":
                signal_counts["thargoid"] = count
            else:
                signal_counts["other"] += count

        # Body in Liste finden und aktualisieren
        found = False
        for body in state.bodies:
            if body["name"] == body_name:
                body["bio_signals"] = signal_counts["bio"]
                body["geo_signals"] = signal_counts["geo"]
                body["human_signals"] = signal_counts["human"]
                body["guardian_signals"] = signal_counts["guardian"]
                body["thargoid_signals"] = signal_counts["thargoid"]
                body["other_signals"] = signal_counts["other"]
                found = True
                break

        # Falls Körper noch nicht in Liste, erstelle Platzhalter
        if not found and any(signal_counts.values()):
            placeholder_body = {
                "name": body_name,
                "type": "Unbekannt",
                "bio_signals": signal_counts["bio"],
                "geo_signals": signal_counts["geo"],
                "human_signals": signal_counts["human"],
                "guardian_signals": signal_counts["guardian"],
                "thargoid_signals": signal_counts["thargoid"],
                "other_signals": signal_counts["other"],
                "distance": 0,
                "gravity": 0,
                "landable": False,
                "materials": [],
                "scanned_fss": False,
                "scanned_dss": False,
                "value": 0,
                "icon": "●",
                "style": None,
                "urgency": "normal"
            }
            state.add_body(placeholder_body)

        return True

    # SAA Signals → Für DSS (Detailed Surface Scanner)
    if evt == "SAASignalsFound":
        signals = event.get("Signals", [])
        body_name = event.get("BodyName", "Unbekannt")

        signal_counts = {
            "bio": 0,
            "geo": 0,
            "human": 0,
            "guardian": 0,
            "thargoid": 0,
            "other": 0
        }

        for signal in signals:
            signal_type = signal.get("Type", "")
            count = signal.get("Count", 0)

            if "Biological" in signal_type or signal_type == "$SAA_SignalType_Biological;":
                signal_counts["bio"] = count
            elif "Geological" in signal_type or signal_type == "$SAA_SignalType_Geological;":
                signal_counts["geo"] = count
            elif "Human" in signal_type or signal_type == "$SAA_SignalType_Human;":
                signal_counts["human"] = count
            elif "Guardian" in signal_type or signal_type == "$SAA_SignalType_Guardian;":
                signal_counts["guardian"] = count
            elif "Thargoid" in signal_type or signal_type == "$SAA_SignalType_Thargoid;":
                signal_counts["thargoid"] = count
            else:
                signal_counts["other"] += count

        # Body in Liste finden und aktualisieren
        found = False
        for body in state.bodies:
            if body["name"] == body_name:
                body["bio_signals"] = signal_counts["bio"]
                body["geo_signals"] = signal_counts["geo"]
                body["human_signals"] = signal_counts["human"]
                body["guardian_signals"] = signal_counts["guardian"]
                body["thargoid_signals"] = signal_counts["thargoid"]
                body["other_signals"] = signal_counts["other"]
                found = True
                break

        # Falls Körper noch nicht in Liste, erstelle Platzhalter
        if not found and any(signal_counts.values()):
            placeholder_body = {
                "name": body_name,
                "type": "Unbekannt",
                "bio_signals": signal_counts["bio"],
                "geo_signals": signal_counts["geo"],
                "human_signals": signal_counts["human"],
                "guardian_signals": signal_counts["guardian"],
                "thargoid_signals": signal_counts["thargoid"],
                "other_signals": signal_counts["other"],
                "distance": 0,
                "gravity": 0,
                "landable": False,
                "materials": [],
                "scanned_fss": False,
                "scanned_dss": False,
                "value": 0,
                "icon": "●",
                "style": None,
                "urgency": "normal"
            }
            state.add_body(placeholder_body)

        return True

    # SAAScanComplete → DSS Scan abgeschlossen
    if evt == "SAAScanComplete":
        body_name = event.get("BodyName", "Unbekannt")
        # Marker setzen, dass DSS im System benutzt wurde
        state.dss_used = True

        for body in state.bodies:
            if body["name"] == body_name:
                body["scanned_dss"] = True
                # WICHTIG: Wert mit DSS-Multiplikator neu berechnen!
                body["value"] = calculate_body_value(body, has_dss=True)
                break

        # System

def initialize_state_from_files(state: ExplorationState):
    """Initialisiere State aus Journal beim Start"""
    try:
        journal = get_latest_journal()
        with open(journal, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("event") == "Location":
                    state.current_system = event.get("StarSystem", "Unbekannt")
                    state.current_system_address = event.get("SystemAddress")
                    state.current_star_class = event.get("StarClass")
                    return True
    except Exception:
        pass
    return False

# =============================================================
# MAIN
# =============================================================

def main():
    console = Console()
    state = ExplorationState()

    CACHE_FILE = Path.home() / ".elite_explorer_cache.json"
    cache = ExplorationCache(CACHE_FILE)

    journal = get_latest_journal()

    console.print(f"[cyan]📘 Beobachte Journal:[/cyan] {journal.name}\n")
    console.print("[yellow]Starte TUI in 2 Sekunden...[/yellow]\n")
    time.sleep(2)

    initialized = initialize_state_from_files(state)

    if initialized:
        state.update_route()

    with open(journal, "r", encoding="utf-8") as f:
        with Live(create_layout(state), refresh_per_second=4, console=console) as live:
            for line in follow(f):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Event verarbeiten
                needs_update = handle_event(event, state, cache)

                # UI aktualisieren falls nötig
                if needs_update:
                    live.update(create_layout(state))


if __name__ == "__main__":
    main()
