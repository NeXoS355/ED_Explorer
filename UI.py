from datetime import datetime
from textual.widgets import Header, Footer, Static, Tree
from rich.text import Text

SCOOPABLE_STARS = {"O", "B", "A", "F", "G", "K", "M"}

# =============================================================
# WIDGETS
# =============================================================

class SystemHeader(Static):
    def __init__(self, state):
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


class UnifiedSystemsTree(Tree):
    """Vereinheitlichter Tree mit allen Systemen und Details"""

    def __init__(self, state):
        super().__init__("Exploration Overview")
        self.state = state
        self.root.expand()

    def update_systems(self):
        self.clear()
        total = len(self.state.systems) + (1 if self.state.current_system else 0)
        self.root.label = f"🌌 Exploration Overview ({total} Systeme)"

        # Aktuelles System
        if self.state.current_system:
            self._add_system(self.state.current_system, True)

        # Alte Systeme
        for system in self.state.systems:
            self._add_system(system, False)

    def _calculate_priority(self, body):
        """Berechnet Prioritätsscore für Sortierung"""
        priority = 0

        # 1. Wert (höchste Priorität)
        priority += body.get("value", 0) * 0.1

        # 2. Planetentyp
        if "Earthlike" in body["type"]:
            priority += 1_000_000
        elif "Water" in body["type"] and "Terraformable" in body["type"]:
            priority += 900_000
        elif "Water" in body["type"]:
            priority += 800_000
        elif "Ammonia" in body["type"]:
            priority += 700_000
        elif "Terraformable" in body["type"]:
            priority += 600_000

        # 3. Signale (nach Typ gewichtet)
        priority += body.get("bio_signals", 0) * 50_000
        priority += body.get("guardian_signals", 0) * 40_000
        priority += body.get("thargoid_signals", 0) * 30_000
        priority += body.get("human_signals", 0) * 20_000
        priority += body.get("geo_signals", 0) * 5_000

        return priority

    def _add_system(self, system, is_current: bool):
        """Fügt ein System mit allen Details zum Tree hinzu"""
        # System-Header
        dss = " 💾" if system.dss_used else ""
        current = " 🎯" if is_current else ""

        system_label = Text()
        system_label.append(f"{system.name}", style="bold cyan" if is_current else "cyan")
        system_label.append(f" ({len(system.bodies)} Bodies)", style="dim")
        system_label.append(dss, style="green")
        system_label.append(current, style="yellow")
        system_label.append(f" — {system.total_value:,} cr", style="bold yellow")

        system_node = self.root.add(system_label, expand=is_current)

        if len(system.bodies) == 0:
            system_node.add_leaf("Keine Körper gescannt")
            return

        # Bodies nach Priorität sortieren
        sorted_bodies = sorted(system.bodies, key=self._calculate_priority, reverse=True)

        # Bodies hinzufügen
        for body in sorted_bodies:
            self._add_body_to_tree(system_node, body)

    def _add_body_to_tree(self, parent_node, body):
        """Fügt einen Körper mit kompakten Infos hinzu"""
        icon = body.get("icon", "◯")
        name = body["name"]
        body_type = body["type"]
        value = body.get("value", 0)

        # Scan Status
        scan_fss = body.get("scanned_fss", False)
        scan_dss = body.get("scanned_dss", False)
        scan_badges = []
        if scan_fss:
            scan_badges.append("[cyan]FSS[/cyan]")
        if scan_dss:
            scan_badges.append("[green]DSS[/green]")
        scan_str = " ".join(scan_badges) if scan_badges else "[dim]Unscanned[/dim]"

        # Hauptzeile: Icon Name [Scans] | Type | Value
        body_label = Text()
        body_label.append(f"{icon} ", style="white")
        body_label.append(f"{name}", style="bold white")

        # Signale kompakt
        signals = []
        bio = body.get("bio_signals", 0)
        geo = body.get("geo_signals", 0)
        human = body.get("human_signals", 0)
        guardian = body.get("guardian_signals", 0)
        thargoid = body.get("thargoid_signals", 0)
        other = body.get("other_signals", 0)

        if bio > 0:
            signals.append(f"🧬 {bio}")
        if geo > 0:
            signals.append(f"🌋 {geo}")
        if human > 0:
            signals.append(f"👤 {human}")
        if guardian > 0:
            signals.append(f"🛡️ {guardian}")
        if thargoid > 0:
            signals.append(f"👽 {thargoid}")
        if other > 0:
            signals.append(f"❓ {other}")

        if signals:
            body_label.append(f" | {' '.join(signals)}")

        # Scan-Badges
        if scan_fss:
            body_label.append(" [FSS]", style="cyan")
        if scan_dss:
            body_label.append(" [DSS]", style="green")

        # Type und Value
        body_label.append(f" │ {body_type}", style="magenta")
        if value > 0:
            body_label.append(f" │ {value:,} cr", style="yellow")

        body_node = parent_node.add(body_label, expand=False)

        # Details-Sektion
        details_added = False

        # 📊 Zusammenfassung (Signals, Distance, Gravity, Landable)
        summary_parts = []

        if signals:
            summary_parts.append(f"Signals: {' '.join(signals)}")

        # Distance
        distance = body.get("distance", 0)
        if distance > 0:
            summary_parts.append(f"📍 {distance:,.0f} Ls")

        # Gravity
        gravity = body.get("gravity", 0)
        if gravity > 0:
            grav_color = "red" if gravity > 2.0 else "yellow" if gravity > 1.5 else "green"
            summary_parts.append(f"⚖️ {gravity:.2f}g")

        # Landable
        if body.get("landable"):
            summary_parts.append("✅ Landable")

        # Zusammenfassung als eine Zeile
        if summary_parts:
            summary_text = Text(" │ ".join(summary_parts))
            body_node.add_leaf(summary_text)
            details_added = True

        # 🧬 Bio-Details (Genuses)
        if body.get("bio_details"):
            bio_node = body_node.add("🧬 Biological Signals")
            scanned = set(body.get("scanned_genomes", []))

            for genus in body.get("bio_details", []):
                if genus in scanned:
                    bio_node.add_leaf(Text(f"✓ {genus}", style="green"))
                else:
                    bio_node.add_leaf(Text(f"○ {genus}", style="white"))
            details_added = True

        # 📦 Materials (Top 5)
        materials = body.get("materials", [])
        if materials:
            sorted_mats = sorted(materials, key=lambda x: x["percent"], reverse=True)[:5]
            mat_text = ", ".join([f"{m['name']} ({m['percent']:.1f}%)" for m in sorted_mats])
            body_node.add_leaf(f"📦 {mat_text}")
            details_added = True

        # Fallback wenn keine Details
        if not details_added:
            body_node.add_leaf(Text("No additional data", style="dim"))


class CompactSystemsTree(Tree):
    """Ultra-kompakte Variante - nur wichtigste Infos"""

    def __init__(self, state):
        super().__init__("Systems")
        self.state = state
        self.root.expand()

    def update_systems(self):
        self.clear()
        total = len(self.state.systems) + (1 if self.state.current_system else 0)
        self.root.label = f"🌌 Systems ({total})"

        if self.state.current_system:
            self._add_compact_system(self.state.current_system, True)

        for system in self.state.systems:
            self._add_compact_system(system, False)

    def _add_compact_system(self, system, is_current):
        """Fügt System mit inline Body-Infos hinzu"""
        dss = "💾" if system.dss_used else ""
        current = "🎯" if is_current else ""

        # System-Zeile
        sys_text = Text()
        if is_current:
            sys_text.append("► ", style="bold yellow")
        sys_text.append(f"{system.name}", style="bold cyan" if is_current else "cyan")
        sys_text.append(f" {dss}{current}", style="green")
        sys_text.append(f" │ {len(system.bodies)} bodies", style="dim")
        sys_text.append(f" │ {system.total_value:,} cr", style="yellow")

        system_node = self.root.add(sys_text, expand=is_current)

        if len(system.bodies) == 0:
            return

        # Sortiere Bodies
        sorted_bodies = sorted(system.bodies, key=lambda b: (
            b.get("value", 0) +
            b.get("bio_signals", 0) * 50000 +
            (1000000 if "Earthlike" in b["type"] else 0)
        ), reverse=True)

        # Zeige nur Top 20 oder alle wenn weniger
        display_count = min(20, len(sorted_bodies))

        for body in sorted_bodies[:display_count]:
            self._add_compact_body(system_node, body)

        # "Show more" wenn es mehr gibt
        if len(sorted_bodies) > display_count:
            remaining = len(sorted_bodies) - display_count
            system_node.add_leaf(Text(f"... and {remaining} more bodies", style="dim italic"))

    def _add_compact_body(self, parent, body):
        """Kompakte Body-Zeile: Icon Name [Scans] Signals Value"""
        icon = body.get("icon", "◯")
        name = body["name"].split()[-1]  # Nur letzter Teil (z.B. "A 1" statt "System A 1")

        line = Text()
        line.append(f"{icon} {name} ", style="white")

        # Scans
        if body.get("scanned_dss"):
            line.append("[DSS] ", style="green")
        elif body.get("scanned_fss"):
            line.append("[FSS] ", style="cyan")

        # Signale (nur Icons mit Zahlen)
        signals = []
        for emoji, key in [("🧬", "bio_signals"), ("🌋", "geo_signals"),
                           ("👤", "human_signals"), ("🛡️", "guardian_signals"),
                           ("👽", "thargoid_signals")]:
            count = body.get(key, 0)
            if count > 0:
                signals.append(f"{emoji}{count}")

        if signals:
            line.append(" ".join(signals) + " ", style="white")

        # Value
        value = body.get("value", 0)
        if value > 0:
            line.append(f"│ {value:,} cr", style="yellow")

        parent.add_leaf(line)
