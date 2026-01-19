from datetime import datetime
from textual.widgets import Header, Footer, Static, Tree, DataTable

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
        self.add_column("Body")
        self.add_column("Type")
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
