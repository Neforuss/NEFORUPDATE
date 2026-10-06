# Third-party notices

NEFORUPDATE's own code is under the [MIT License](LICENSE). The packaged app (installer and
portable .exe) also contains the following third-party software, under their own licences.
The licence texts are in the `licenses` folder (installed next to NEFORUPDATE.exe).

## Qt for Python (PySide6, Shiboken6) and Qt 6

- Copyright (C) The Qt Company Ltd. and other contributors.
- Used under the **GNU Lesser General Public License v3** (`licenses/LGPL-3.0.txt`), which builds
  on the GNU General Public License v3 (`licenses/GPL-3.0.txt`).
- Source code: https://code.qt.io/cgit/pyside/pyside-setup.git and https://code.qt.io (Qt),
  or https://download.qt.io/official_releases/QtForPython/. Version used: PySide6 6.11.1.
- Qt is used unmodified, as separate libraries (the `PySide6` and `shiboken6` folders inside the
  installed app's `_internal` folder). You may replace them with a compatible build of your own.
  NEFORUPDATE's complete source code and build scripts are public, so you can also rebuild the
  whole app, including the single-file portable version, against your own Qt.

## Python

- Copyright (c) 2001 Python Software Foundation; All Rights Reserved.
- Used under the **Python Software Foundation License** (`licenses/Python-PSF-LICENSE.txt`).
  Version used: Python 3.11.

## PyInstaller (bootloader)

- Copyright (c) 2010-2026, PyInstaller Development Team.
- The bootloader inside NEFORUPDATE.exe is under the GNU GPL v2 with a special exception that
  allows it to be used in programs under any licence. https://pyinstaller.org

## Inno Setup (installer only)

- Copyright (C) 1997-2026 Jordan Russell and Martijn Laan. https://jrsoftware.org/isinfo.php
- The setup program is made with Inno Setup, which allows free use, including for distribution.

## Not included, but used when installed on your PC

NEFORUPDATE talks to these tools if you have them; they are not part of NEFORUPDATE:
winget and the Microsoft.WinGet.Client PowerShell module (Microsoft, MIT License), Chocolatey,
Scoop, Windows PowerShell, the Microsoft Store and Windows Update.
