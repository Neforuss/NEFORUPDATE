"""Run a batch of commands as Administrator with ONE UAC prompt, while the app itself stays non-admin.

An elevated process can't stream its output back through a pipe to a non-elevated parent,
so the elevated script appends to a log file and we tail it. Markers in that file:
  ##START <n>   ##EXIT <n> <code>   ##SKIP <n>   ##DONE
Cancel is a flag file the elevated script checks between commands.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import runner

BATCH_TEMPLATE = r"""
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$log = '__LOG__'
$cancel = '__CANCEL__'
$items = '__DATA__' | ConvertFrom-Json
function W([string]$t) { [IO.File]::AppendAllText($log, $t + "`n", [Text.Encoding]::UTF8) }
$n = 0
foreach ($it in $items) {
    if (Test-Path -LiteralPath $cancel) { W "##SKIP $n"; $n++; continue }
    W "##START $n"
    $a = @($it.args)
    & $it.exe @a 2>&1 | ForEach-Object { W (("$_" -split "`r")[-1]) }
    W "##EXIT $n $LASTEXITCODE"
    $n++
}
W '##DONE'
"""

UAC_DECLINED = 1223


def _q(s: str) -> str:
    return s.replace("'", "''")


def run_elevated_batch(commands: list[list[str]], registry: runner.ProcessRegistry,
                       is_cancelled: Callable[[], bool],
                       on_start: Callable[[int], None],
                       on_line: Callable[[int, str], None],
                       on_exit: Callable[[int, int], None],
                       on_skip: Callable[[int], None]) -> int:
    """Returns the launcher's exit code; UAC_DECLINED if the prompt was refused."""
    work = Path(tempfile.mkdtemp(prefix="neforupdate-"))
    log, cancel, script = work / "out.log", work / "cancel.flag", work / "batch.ps1"
    log.write_text("", encoding="utf-8")
    data = json.dumps([{"exe": c[0], "args": c[1:]} for c in commands])
    script.write_text(BATCH_TEMPLATE.replace("__LOG__", _q(str(log))).replace("__CANCEL__", _q(str(cancel)))
                      .replace("__DATA__", _q(data)), encoding="utf-8-sig")
    launcher = (
        "try { $p = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -PassThru -Wait "
        f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"{_q(str(script))}\"'; "
        "exit $p.ExitCode } catch { exit 1223 }")

    import subprocess
    proc = subprocess.Popen(runner.ps_args(launcher), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, creationflags=runner.CREATE_NO_WINDOW)
    registry.add(proc)
    pos, current, buf = 0, -1, ""
    try:
        while True:
            finished = proc.poll() is not None
            if is_cancelled() and not cancel.exists():
                cancel.write_text("1")
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
            buf += chunk
            *lines, buf = buf.split("\n")
            for line in lines:
                line = line.lstrip("﻿").rstrip("\r")  # AppendAllText writes a BOM into the empty file
                parts = line.split()
                if line.startswith("##START ") and len(parts) == 2:
                    current = int(parts[1]); on_start(current)
                elif line.startswith("##EXIT ") and len(parts) >= 2:
                    code = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else -1
                    on_exit(int(parts[1]), code); current = -1
                elif line.startswith("##SKIP ") and len(parts) == 2:
                    on_skip(int(parts[1]))
                elif line.startswith("##DONE"):
                    pass
                elif current >= 0:
                    on_line(current, line)
            if finished:
                break
            time.sleep(0.3)
    finally:
        registry.remove(proc)
    return proc.returncode
