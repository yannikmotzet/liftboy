from __future__ import annotations

from datetime import timedelta
from types import TracebackType

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, ProgressColumn, SpinnerColumn, Task, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text

from shared.models import RecordingMetadata

class _RsyncSpeedColumn(ProgressColumn):
    def render(self, task: Task) -> Text:
        bps = task.fields.get("rsync_speed")
        if not bps:
            return Text("", style="progress.data.speed")
        if bps >= 1e9:
            s = f"{bps / 1e9:.1f} GB/s"
        elif bps >= 1e6:
            s = f"{bps / 1e6:.1f} MB/s"
        else:
            s = f"{bps / 1e3:.1f} KB/s"
        return Text(s, style="progress.data.speed")


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


def _fmt_speed(bps: float | None) -> str:
    if bps is None:
        return "—"
    if bps >= 1e9:
        return f"{bps / 1e9:.1f} GB/s"
    if bps >= 1e6:
        return f"{bps / 1e6:.1f} MB/s"
    return f"{bps / 1e3:.1f} KB/s"


class TuiManager:
    def __init__(self, recordings: list[RecordingMetadata], console: Console | None = None) -> None:
        self._recordings = recordings
        # row state: name → (status, progress_pct, eta_secs, bytes_xfrd, size_bytes, speed_bps)
        self._state: dict[str, tuple[str, float, float | None, int, int, float | None]] = {
            r.name: ("pending", 0.0, None, 0, r.size_bytes, None) for r in recordings
        }
        self._connected: bool = True
        total_bytes = sum(r.size_bytes for r in recordings)
        self._overall_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]Overall"),
            DownloadColumn(),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            _RsyncSpeedColumn(),
            TimeElapsedColumn(),
            TextColumn("[dim]eta"),
            TimeRemainingColumn(),
        )
        self._overall_task = self._overall_progress.add_task(
            "overall", total=total_bytes
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
        table.add_column("Transfer", justify="right")
        table.add_column("ETA", justify="right")

        for rec in self._recordings:
            status, pct, eta, bytes_xfrd, size_bytes, speed_bps = self._state[rec.name]
            style = _STATUS_STYLES.get(status, "")
            pct_str = f"{pct:.0f}%" if status in ("uploading", "completed") else "—"

            if status == "uploading":
                remaining = max(0, size_bytes - bytes_xfrd)
                transfer_str = f"{_fmt_size(bytes_xfrd)} / {_fmt_size(remaining)}"
                eta_str = _fmt_eta(eta)
            elif status == "completed":
                transfer_str = _fmt_size(size_bytes)
                eta_str = "—"
            else:
                transfer_str = f"— / {_fmt_size(size_bytes)}"
                eta_str = "—"

            table.add_row(
                rec.name,
                rec.robot_name,
                _fmt_size(rec.size_bytes),
                _fmt_duration(rec.duration_seconds),
                Text(status, style=style),
                pct_str,
                transfer_str,
                eta_str,
            )

        if self._connected:
            conn_indicator = "[bold green]● connected[/]"
        else:
            conn_indicator = "[bold red]● server unreachable[/]"
        panel = Panel(
            table,
            title=f"[bold]Liftboy — Recording Upload[/]  {conn_indicator}",
            border_style="dim blue" if self._connected else "red",
        )
        return Group(panel, self._overall_progress)

    def set_connection_status(self, connected: bool) -> None:
        if self._connected != connected:
            self._connected = connected
            self._live.update(self._render())

    def update_row(
        self,
        name: str,
        status: str,
        progress_pct: float,
        eta_secs: float | None = None,
        bytes_xfrd: int = 0,
        size_bytes: int | None = None,
        speed_bps: float | None = None,
    ) -> None:
        prev = self._state[name]
        sz = size_bytes if size_bytes is not None else prev[4]
        self._state[name] = (status, progress_pct, eta_secs, bytes_xfrd, sz, speed_bps)

        transferred = sum(
            s[4] if s[0] == "completed"
            else s[3]
            for s in self._state.values()
            if s[0] in ("completed", "uploading")
        )
        # Sum speed across active uploads for the overall speed display
        total_speed = sum(
            s[5] for s in self._state.values()
            if s[0] == "uploading" and s[5] is not None
        )
        self._overall_progress.update(
            self._overall_task,
            completed=transferred,
            rsync_speed=total_speed if total_speed > 0 else None,
        )
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
