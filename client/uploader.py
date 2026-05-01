from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

# Matches rsync progress lines:
#     1,234,567  42%   10.50MB/s    0:01:23
_PROGRESS_RE = re.compile(
    r"(?P<bytes>[\d,]+)\s+(?P<pct>\d+)%\s+[\d.]+\w+/s\s+(?P<eta>\d+:\d+:\d+)"
)


def _parse_eta(eta_str: str) -> float:
    parts = eta_str.split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s


ProgressCallback = Callable[[float, int, float | None], None]


class RsyncUploader:
    def __init__(self, bwlimit: int = 0) -> None:
        self._bwlimit = bwlimit

    def upload(
        self,
        src: Path,
        dest: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> bool:
        cmd = ["rsync", "--archive", "--progress", "--stats"]
        if self._bwlimit > 0:
            cmd += [f"--bwlimit={self._bwlimit}"]
        # Trailing slash on src to copy contents into dest, not src dir itself
        cmd += [f"{src}/", f"{dest}/"]

        dest.mkdir(parents=True, exist_ok=True)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                if progress_callback:
                    m = _PROGRESS_RE.search(line)
                    if m:
                        pct = float(m.group("pct"))
                        bytes_xfrd = int(m.group("bytes").replace(",", ""))
                        eta = _parse_eta(m.group("eta"))
                        progress_callback(pct, bytes_xfrd, eta)

            proc.wait()
            return proc.returncode == 0

        except FileNotFoundError:
            raise RuntimeError(
                "rsync not found. Install rsync to use liftboy-client."
            ) from None
        except Exception:
            return False
