# NEFORUPDATE

**Made by Neforus** - [neforus.com](https://neforus.com) · Free and open source under the
[MIT License](LICENSE) · Source: [github.com/Neforuss/NEFORUPDATE](https://github.com/Neforuss/NEFORUPDATE)
· Want to help? See [CONTRIBUTING.md](CONTRIBUTING.md)

One window for every pending update on a Windows PC: winget, the Microsoft Store, Chocolatey,
Scoop, Windows Update, and installed programs no package manager tracks. Sources scan in
parallel, duplicates are merged, and selected updates install one at a time through the right
package manager.

## Install it

Run `dist\NEFORUPDATE-Setup-<version>.exe`. Setup asks "only for me" (no admin rights,
`%LOCALAPPDATA%\Programs\NEFORUPDATE`) or "all users" (Program Files), then adds a Start menu entry,
an optional desktop shortcut, a Settings > Apps entry with uninstaller, and the Win+R name
`neforupdate`. Uninstalling asks whether to remove your settings and logs too.

## Release it

```
release.cmd
```

Builds everything into `dist\`: the installer (`NEFORUPDATE-Setup-<version>.exe`, from
`installer\neforupdate.iss` + the folder build `NEFORUPDATE-installer.spec`), the portable single
file (`NEFORUPDATE-<version>-portable.exe`, from `NEFORUPDATE.spec`) and `SHA256SUMS.txt`.
Needs PyInstaller and Inno Setup 6 (`scoop bucket add extras`, `scoop install inno-setup`).
The version comes from `neforupdate\__init__.py` (also update `version_info.txt`).
Website material for neforus.com/neforupdate is in `website\` (see the handoff file there).

## Run it

| How | Command |
|---|---|
| Installed | Start menu > NEFORUPDATE |
| Packaged | `dist\NEFORUPDATE-<version>-portable.exe` - no install, no Python needed |
| From source | double-click `NEFORUPDATE.cmd` (no console window) |
| Read-only list, no window | `python main.py --list --untracked` |

Needs Windows 10 or 11. Running from source needs Python 3.11+ with PySide6. Structured winget
data comes from Microsoft's `Microsoft.WinGet.Client` PowerShell module; without it, NEFORUPDATE
falls back to parsing `winget upgrade` text, and the Untracked apps tab offers to install the module
(for the current user, no admin rights needed).

## Build just the portable .exe

```
python -m pip install --user pyinstaller
build.cmd
```

`build.cmd` runs PyInstaller with `NEFORUPDATE.spec` (`release.cmd` does this too), which adds:

- the icon (`assets\neforupdate.ico`, 16-256 px) to the .exe and its window,
- the 1280x720 splash screen (`assets\splash.png`), shown from launch until the window is ready,
- Windows file properties from `version_info.txt` (Company: Neforus),
- `windows-manifest.xml`, which makes the .exe DPI-aware so the splash isn't stretched on scaled displays.

Output: `dist\NEFORUPDATE.exe` (about 50 MB, single file, windowed).

To change the icon, make a square image (1024x1024 PNG works well) and run
`python tools\make_icon.py path\to\image.png`, then `build.cmd`. It writes `assets\neforupdate.ico`
(16-256 px, scaled down rather than cropped) and `assets\icon.png` (window and taskbar icon).

## How it works

| Source | Scan | Update |
|---|---|---|
| winget | `Get-WinGetPackage` (module), text fallback | `winget upgrade --id ... --exact --silent` |
| Microsoft Store | `AppInstallManager.SearchForAllUpdatesAsync` with auto-download **off** | `SearchForUpdatesAsync` per app, real % progress |
| Chocolatey | `choco outdated -r` | `choco upgrade -y`; one elevated batch (one UAC prompt) when not admin |
| Scoop | `scoop status` objects -> JSON | `scoop update <app>` |
| Linked apps | registry version vs. the linked winget package's latest version | `winget install --id ... --exact --silent` over the installed copy |
| Windows Update | `Microsoft.Update.Session` COM search | list-only for now |

- **Dedup:** rows from different sources merge when the name/id matches *and* the installed
  versions agree. Different versions usually mean separate copies, so those stay separate.
  The preferred source (Settings, winget first by default) does the update; right-click a
  row > *Update with* to override it for that app.
- **Ticks:** risky items start unticked (GPU/audio drivers, filesystem drivers, license-tied
  apps, unknown installed versions). Cold Turkey Blocker can never be ticked or linked.
  Your own tick changes are remembered.
- **Failures:** each app gets its own result with a plain-language reason. One failure
  never stops the batch.
- **Restarts:** apps that need a restart are listed in a banner. NEFORUPDATE never restarts.
- **Logs:** `%LOCALAPPDATA%\NEFORUPDATE\logs\` (one file per run, last 30 kept), also shown
  in the window under *Show log*.
- **Settings:** `HKCU\Software\Neforus\NEFORUPDATE` (theme, source order, ticks, links).

## Untracked apps - and updating them

Installed desktop programs that no package manager recognises (winget lists them as `ARP\...`
entries it can't match). Publisher, website, install folder and date come from each program's
Uninstall registry key; anything Chocolatey or Scoop manage, hotfixes, drivers, system components
and Windows' own servicing tools are left out.

To update them:

1. **Find winget matches** searches the winget catalog for every untracked app (4 searches run in
   parallel; about 10-30 seconds for ~190 apps). Results are cached in
   `%LOCALAPPDATA%\NEFORUPDATE\matches.json`.
2. Each app gets a suggestion (orange, with `?`) only when the name matches, and short one-word
   names also need the publisher to match. *High* confidence = same name and publisher.
3. **Review matches** lists all suggestions; high-confidence ones are pre-ticked. Linking is
   always your decision - nothing is linked automatically.
4. Linked apps (green ✓) are checked by the **Linked apps** source on every scan. When winget has
   a newer version, the app appears in the Updates tab and updates like everything else:
   `winget install` runs the vendor's installer over the existing copy, using the same scope
   (all users / this user) as the existing install when winget offers it.

Right-click a row for: link to a suggestion, *Link to a winget package...* (search by hand),
*Unlink*, open the website, search the web for the latest version, open the install folder, copy
the name, or **Hide** it once you've dealt with it. *Export CSV* saves the whole list.

Apps with no winget package still need their own updater or website - right-click > *Open website*.

## Adding a source (pip, npm, vendor updaters)

1. Create `neforupdate/sources/<name>.py` with a subclass of `Source` (see `sources/base.py`).
2. Implement `available()`, `scan()` (return `Candidate`s) and `update()`
   (or `update_many()` to batch).
3. Add it to `all_sources()` in `neforupdate/sources/__init__.py` and to `DEFAULT_ORDER` /
   `UPDATE_ORDER` in `merge.py` / `workers.py`.

## Not covered yet

- **Installing Windows updates** (list-only by design).
- **Store updates the Store itself paused** (e.g. ChatGPT) are reported as paused; NEFORUPDATE
  can't un-pause them.
- **Store "available version"** shows "Newer version": the Store reports bundle versions
  that can't be compared with installed versions.
- **Cancelling mid-install**: Cancel stops *after* the current app, because killing an
  installer halfway can break the app.
- **winget's "different install technology" updates** (0x8A15008E) need an uninstall and
  reinstall, which NEFORUPDATE doesn't do automatically.
- **Linked apps:** if winget's installer differs from the one you used (e.g. 64-bit vs. 32-bit,
  or an MSI vs. an .exe installer), Windows may end up with a second copy instead of an upgrade.
  Untracked apps with no winget package (most audio plug-ins, Adobe apps, games) can only be
  updated through their own updaters.
- **The non-admin elevation path** (one UAC prompt for Chocolatey) is built and its plumbing
  tested, but the PC it was developed on has UAC turned off.

## Licence and credits

- NEFORUPDATE's code is open source under the [MIT License](LICENSE): use it, change it, share it.
  Contributions are welcome - see [CONTRIBUTING.md](CONTRIBUTING.md).
- The NEFORUPDATE name, icon and splash screen are **not** under the MIT License; if you publish
  your own version, give it its own name and art. See [BRANDING.md](BRANDING.md).
- The packaged app includes Qt/PySide6 (LGPL-3.0), Python (PSF License) and a PyInstaller
  bootloader; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and the `licenses` folder.
- NEFORUPDATE is made by **Neforus** - [neforus.com](https://neforus.com).
- Splash screen background by **Jason Benjamin** - [perfecthue.com/wallpapers](https://perfecthue.com/wallpapers/).
