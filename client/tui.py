from __future__ import annotations

from datetime import timedelta
from types import TracebackType

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from shared.models import RecordingMetadata

_STATUS_STYLES: dict[str, str] = {
    "pending": "dim",
    "uploading": "bold cyan",
    "completed": "bold green",
    "failed": "bold red",
    "interrupted": "bold yellow",
}


def _fmt_size(b: int) -> str:
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    return f"{b / 1024:.1f} KB"


def _fmt_duration(secs: float | None) -> str:
    if secs is None:
        return "—"
    return str(timedelta(seconds=int(secs)))


def _fmt_eta(secs: float | None) -> str:
    if secs is None:
        return "—"
    return str(timedelta(seconds=int(secs)))


class TuiManager:
    def __init__(self, recordings: list[RecordingMetadata], console: Console | None = None) -> None:
        self._recordings = recordings
        # row state: name → (status, progress_pct, eta_secs)
        self._state: dict[str, tuple[str, float, float | None]] = {
            r.name: ("pending", 0.0, None) for r in recordings
        }
        self._overall_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]Overall"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._overall_task = self._overall_progress.add_task(
            "overall", total=len(recordings)
        )
        self._console = console or Console()
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=4,
            transient=False,
        )

    @property
    def console(self) -> Console:
        return self._console

    def _render(self) -> Group:
        table = Table(
            show_header=True,
            header_style="bold dim",
            border_style="dim",
            expand=True,
        )
        table.add_column("Recording", style="cyan", no_wrap=True)
        table.add_column("Robot", style="dim")
        table.add_column("Size", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Progress", justify="right")
        table.add_column("ETA", justify="right")

        for rec in self._recordings:
            status, pct, eta = self._state[rec.name]
            style = _STATUS_STYLES.get(status, "")
            pct_str = f"{pct:.0f}%" if status in ("uploading", "completed") else "—"
            table.add_row(
                rec.name,
                rec.robot_name,
                _fmt_size(rec.size_bytes),
                _fmt_duration(rec.duration_seconds),
                Text(status, style=style),
                pct_str,
                _fmt_eta(eta) if status == "uploading" else "—",
            )

        panel = Panel(table, title="[bold]Liftboy — Recording Upload", border_style="dim blue")
        return Group(panel, self._overall_progress)

    def update_row(
        self,
        name: str,
        status: str,
        progress_pct: float,
        eta_secs: float | None = None,
    ) -> None:
        self._state[name] = (status, progress_pct, eta_secs)
        if status == "completed":
            completed_count = sum(
                1 for s, _, _ in self._state.values() if s == "completed"
            )
            self._overall_progress.update(self._overall_task, completed=completed_count)
        self._live.update(self._render())

    def __enter__(self) -> "TuiManager":
        self._live.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._live.__exit__(exc_type, exc_val, exc_tb)
