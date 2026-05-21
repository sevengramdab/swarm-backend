"""
Twilio MMS Gateway Interface — Response Builder

Think of this like a friendly answering machine that texts Mom back.
It speaks in plain English (no robot jargon) and can even draw little
picture charts — like a smart fridge that draws a graph of how much
milk is left, then texts it to you.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


# =============================================================================
# Response Builder — The friendly texting robot
# =============================================================================

class ResponseBuilder:
    """
    This is the robot butler that texts Mom back.
    It never uses big scary words, and it always keeps things short
    because texts are like tiny sticky notes, not novels.
    """

    # How many characters fit in one SMS before it splits
    SMS_CHAR_LIMIT: int = 1600

    # Chart image size (like a postcard)
    CHART_WIDTH: int = 1024
    CHART_HEIGHT: int = 768

    def __init__(self) -> None:
        """
        Boot up the butler. Make sure the art desk is ready
        in case we need to draw a chart.
        """
        self._temp_dir = Path(tempfile.gettempdir()) / "simplepod_twilio_charts"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Text Responses — Like pre-written sticky notes
    # -------------------------------------------------------------------------

    def status_response(self, role: str) -> str:
        """
        Mom asked "How's the house?"
        We send back a quick dashboard summary — like a thermostat screen.
        """
        return (
            f"🏠 SimplePod Status (role: {role})\n"
            "────────────────────────\n"
            "🟢 Gateway: Online\n"
            "🟢 Agents: 14 active\n"
            "🟢 Nodes: 3 connected\n"
            "⚡ Load: 42%\n"
            "🌤️  Weather: Clear\n"
            "────────────────────────\n"
            "Reply HELP for commands."
        )

    def agents_response(self) -> str:
        """
        Mom asked "Who's working?"
        We send the crew roster — like a whiteboard by the door.
        """
        agents = [
            "AGENT-001 🟢 Scheduler",
            "AGENT-002 🟢 Logger",
            "AGENT-003 🟡 Backup (syncing)",
            "AGENT-014 🟢 MMS Gateway",
            "AGENT-099 🔴 Idle",
        ]
        return (
            "👥 Active Agents\n"
            "────────────────\n"
            + "\n".join(agents)
            + "\n────────────────\n"
            "5 of 14 shown. Reply NODES for servers."
        )

    def nodes_response(self) -> str:
        """
        Mom asked "Which rooms are connected?"
        We send the server list — like a panel showing which
        light switches have power.
        """
        return (
            "🖥️  Connected Nodes\n"
            "──────────────────\n"
            "node-alpha   🟢 12ms\n"
            "node-beta    🟢 18ms\n"
            "node-gamma   🟡 45ms\n"
            "──────────────────\n"
            "3 nodes online.\n"
            "Reply BREAKER LOCAL to isolate."
        )

    def breaker_response(self, target: str | None) -> str:
        """
        Mom asked to flip a switch.
        We confirm which circuit got toggled — like a breaker box.
        """
        if target == "local":
            return (
                "⚡ Breaker: LOCAL\n"
                "────────────────\n"
                "🔒 Local mode ON.\n"
                "☁️  Cloud link OFF.\n"
                "All traffic staying home."
            )
        if target == "cloud":
            return (
                "⚡ Breaker: CLOUD\n"
                "────────────────\n"
                "☁️  Cloud mode ON.\n"
                "🔒 Local link OFF.\n"
                "Traffic routed to cloud."
            )
        return (
            "⚡ Breaker\n"
            "─────────\n"
            "Please say LOCAL or CLOUD.\n"
            "Example: 'breaker local'"
        )

    def stop_response(self, target: str | None) -> str:
        """
        Mom hit the emergency brake.
        We confirm everything is stopped safely — like a smart
        stove that texts "Burners off." when you ask.
        """
        if target == "all":
            return (
                "🛑 STOP ALL\n"
                "───────────\n"
                "All agents halted.\n"
                "Nodes preserved.\n"
                "Reply STATUS to resume check."
            )
        return (
            f"🛑 STOP {target or 'agent'}\n"
            "────────────\n"
            "Shutdown signal sent.\n"
            "Will confirm when done."
        )

    def help_response(self, role: str) -> str:
        """
        Mom forgot the commands.
        We send a little cheat sheet — like a magnet on the fridge.
        """
        base = (
            "📋 Commands\n"
            "──────────\n"
            "STATUS  — House dashboard\n"
            "AGENTS  — Who's working\n"
            "NODES   — Which rooms on\n"
            "BREAKER — LOCAL or CLOUD\n"
            "STOP    — Emergency brake\n"
            "PICTURE — Send chart pic\n"
            "HELP    — This menu"
        )
        if role == "admin":
            base += "\n\n🔑 Admin: full access"
        elif role == "operator":
            base += "\n\n🔧 Operator: most cmds"
        else:
            base += "\n\n👀 Observer: view only"
        return base

    def unknown_command_response(self, raw_input: str) -> str:
        """
        Mom said something the robot didn't understand.
        We politely ask her to rephrase — like a smart speaker
        saying "I didn't catch that."
        """
        snippet = raw_input[:30] + "…" if len(raw_input) > 30 else raw_input
        return (
            f"🤔 Not sure about: \"{snippet}\"\n"
            "────────────────────────\n"
            "Try: STATUS, AGENTS, NODES,\n"
            "BREAKER, STOP, PICTURE, HELP"
        )

    def unauthorized_response(self) -> str:
        """
        A stranger texted the house!
        We politely lock the door — like a smart lock saying
        "Access denied" on the keypad.
        """
        return (
            "🔒 Access Denied\n"
            "───────────────\n"
            "Your number is not on the guest list.\n"
            "Contact admin to register."
        )

    def permission_denied_response(self, action: str) -> str:
        """
        Mom asked to do something above her pay grade.
        We gently say no — like a child-proof cabinet staying locked.
        """
        return (
            f"🚫 Can't do '{action}'\n"
            "──────────────────\n"
            "Your keycard doesn't open this door.\n"
            "Ask admin to upgrade your role."
        )

    def rate_limit_response(self, window_seconds: int) -> str:
        """
        Mom is texting too fast — like pressing the doorbell 20 times.
        We ask her to slow down.
        """
        minutes = window_seconds // 60
        return (
            "⏳ Slow down!\n"
            "────────────\n"
            f"Too many texts in {minutes} min.\n"
            "Please wait a bit."
        )

    def acknowledge_image_sent(self) -> str:
        """
        We drew a chart and sent it.
        This is the quick "heads up" text that goes with the picture.
        """
        return "📊 Chart sent! Check your picture messages."

    # -------------------------------------------------------------------------
    # Chart Drawing — Like a smart whiteboard that takes a photo
    # -------------------------------------------------------------------------

    async def generate_status_chart(self) -> str:
        """
        Draw a pretty dashboard picture and save it.
        It's like a robot that draws a house status report
        on a whiteboard, then takes a photo to text Mom.
        """
        img = Image.new("RGB", (self.CHART_WIDTH, self.CHART_HEIGHT), color="#1e1e2e")
        draw = ImageDraw.Draw(img)

        # Try to load a nice font; fall back to default if not found
        font_title = self._load_font(size=36)
        font_body = self._load_font(size=24)
        font_small = self._load_font(size=18)

        # Title bar — like a header on a report card
        draw.rectangle([0, 0, self.CHART_WIDTH, 80], fill="#313244")
        draw.text((30, 20), "🏠 SimplePod Surgical Strike Swarm", fill="#cdd6f4", font=font_title)
        draw.text((30, 55), "Twilio Gateway Dashboard", fill="#a6adc8", font=font_small)

        # Draw status boxes — like little Post-it notes on a board
        boxes = [
            ("Gateway", "ONLINE", "#a6e3a1", 100, 120),
            ("Agents", "14/14", "#a6e3a1", 100, 300),
            ("Nodes", "3/3", "#a6e3a1", 100, 480),
            ("CPU Load", "42%", "#f9e2af", 550, 120),
            ("Memory", "1.2 GB", "#89b4fa", 550, 300),
            ("Uptime", "3d 4h", "#cba6f7", 550, 480),
        ]

        for label, value, color, x, y in boxes:
            self._draw_status_box(draw, label, value, color, x, y, font_body, font_title)

        # Draw a simple bar chart — like a kids' growth chart on the wall
        self._draw_bar_chart(draw, font_body, font_small)

        # Footer
        draw.text(
            (30, self.CHART_HEIGHT - 40),
            "Generated by AGENT-014 · Twilio MMS Gateway",
            fill="#6c7086",
            font=font_small,
        )

        # Save the photo to the temp desk
        path = str(self._temp_dir / "status_chart.png")
        img.save(path, "PNG")
        return path

    def _draw_status_box(
        self,
        draw: ImageDraw.ImageDraw,
        label: str,
        value: str,
        color: str,
        x: int,
        y: int,
        font_body: ImageFont.FreeTypeFont,
        font_value: ImageFont.FreeTypeFont,
    ) -> None:
        """
        Draw one little Post-it note on the whiteboard.
        Each note shows one thing about the house.
        """
        box_width = 350
        box_height = 140
        # Rounded rectangle look (using normal rect + border lines)
        draw.rectangle([x, y, x + box_width, y + box_height], fill="#313244", outline="#45475a", width=2)
        # Color accent strip on the left — like a colored tab on a folder
        draw.rectangle([x, y, x + 10, y + box_height], fill=color)
        # Label text
        draw.text((x + 25, y + 15), label, fill="#a6adc8", font=font_body)
        # Value text (big and bold feeling)
        draw.text((x + 25, y + 55), value, fill=color, font=font_value)

    def _draw_bar_chart(
        self,
        draw: ImageDraw.ImageDraw,
        font_body: ImageFont.FreeTypeFont,
        font_small: ImageFont.FreeTypeFont,
    ) -> None:
        """
        Draw a simple bar chart — like coloring in a thermometer
        to show how warm each room is.
        """
        chart_x = 100
        chart_y = 640
        chart_w = 824
        chart_h = 80

        draw.text((chart_x, chart_y - 30), "Load History (last 6 hours)", fill="#cdd6f4", font=font_body)

        bars = [30, 45, 42, 60, 38, 42]
        colors = ["#a6e3a1", "#a6e3a1", "#a6e3a1", "#f9e2af", "#a6e3a1", "#a6e3a1"]
        bar_width = chart_w // len(bars)

        for idx, (height_pct, color) in enumerate(zip(bars, colors)):
            bar_h = int(chart_h * (height_pct / 100))
            bx = chart_x + idx * bar_width + 10
            by = chart_y + chart_h - bar_h
            draw.rectangle(
                [bx, by, bx + bar_width - 20, chart_y + chart_h],
                fill=color,
                outline="#45475a",
            )

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        """
        Pick a marker pen for drawing.
        If our favorite pen is missing, we use a boring default pen.
        """
        candidates: Iterable[str | None] = [
            "arial.ttf",
            "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]
        for name in candidates:
            if name is None:
                continue
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def chunk_text(text: str, limit: int = SMS_CHAR_LIMIT) -> list[str]:
        """
        Sometimes a note is too long for one sticky note.
        This splits it into multiple sticky notes so nothing gets cut off.
        """
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        while text:
            chunk = text[:limit]
            text = text[limit:]
            chunks.append(chunk)
        return chunks
