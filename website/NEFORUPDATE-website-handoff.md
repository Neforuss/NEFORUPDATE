# Handoff: NEFORUPDATE project page on neforus.com/neforupdate

**For:** whoever builds the page (you, a web developer, or an AI assistant).
**Goal:** publish NEFORUPDATE as a project on **https://neforus.com/neforupdate**, with downloads, screenshots, and accurate copy.
**Everything needed is in this `website` folder** plus the release files in `..\dist\`.

> The installer already points to `https://neforus.com/neforupdate` as its Support and Updates
> link (shown in Windows Settings > Apps). That URL has to exist before the installer is shared.

---

## 1. Page at a glance

| Item | Value |
|---|---|
| URL | `https://neforus.com/neforupdate` |
| Page title (`<title>`) | NEFORUPDATE - update every app on your PC \| Neforus |
| Meta description | Free Windows app by Neforus that finds pending updates from winget, the Microsoft Store, Chocolatey, Scoop and Windows Update, and installs the ones you pick with one click. |
| Social preview image (`og:image`) | `neforupdate-splash.png` (1280x720) |
| Project-list card | Icon `neforupdate-icon-512.png`, title "NEFORUPDATE", one-liner "Every update on your PC in one window." |
| Tags | Windows, utility, updates, open source, MIT, Python |
| Source code | https://github.com/Neforuss/NEFORUPDATE (MIT License) |
| Current version | 1.2.0 (first public release), released 2026-10-06 |

---

## 2. Files

### Downloads (upload from `..\dist\`)

| File | Size | SHA-256 | Button label |
|---|---|---|---|
| `NEFORUPDATE-Setup-1.2.0.exe` | 34.8 MB | `ee3198f4562429bc5f08f276c2907e072ec3840748843f7924e39288945ac7da` | **Download installer** (main button) |
| `NEFORUPDATE-1.2.0-portable.exe` | 50.0 MB | `63c119659baf75fbaaef35c9c311b9491b67f182f012da82d21433388589f1c2` | Portable version (no install) |

Also publish `..\dist\SHA256SUMS.txt` next to the downloads and show the hashes on the page (small
print), so people can check their download. Suggested location: `https://neforus.com/neforupdate/downloads/`.

### Images (this folder)

All screenshots use **demo data** (well-known free apps), not the developer's own PC. Regenerate
them for future versions with `python tools\make_screenshots.py`.

| File | Size (px) | Use | Alt text |
|---|---|---|---|
| `neforupdate-splash.png` | 1280x720 | Hero image / social preview | NEFORUPDATE splash screen: the name in white over a rainbow light background |
| `neforupdate-icon-512.png` | 512x512 | Project card, favicon-style logo | NEFORUPDATE icon: a white letter U on a fiery orange and purple gradient |
| `neforupdate-updates-dark.png` | 2560x1411 | Main screenshot | NEFORUPDATE updating apps one at a time, with per-app progress and a progress bar for every source |
| `neforupdate-updates-light.png` | 2560x1411 | Light-theme screenshot | The same window in the light theme |
| `neforupdate-untracked.png` | 2560x1411 | Untracked apps feature | Untracked apps tab: installed programs matched to winget packages, one linked and showing a newer version |
| `neforupdate-review-matches.png` | 1225x650 | Linking feature | Review matches dialog listing suggested winget packages with confidence levels |
| `neforupdate-setup.png` | 814x623 | "Install" section | The NEFORUPDATE setup wizard welcome page |

The screenshots are wide (2560 px); show them scaled down with click-to-enlarge.

---

## 3. Page copy (ready to paste)

### Hero

**NEFORUPDATE**
Every update on your PC in one window.

NEFORUPDATE checks winget, the Microsoft Store, Chocolatey, Scoop and Windows Update at the same
time, shows everything in one list, and installs the updates you pick - one at a time, with one click.

[ Download installer ]  [ Portable version ]  [ Source code on GitHub ]
Windows 10 and 11, 64-bit. Free and open source (MIT). Made by Neforus.

### Why

Keeping a Windows PC up to date means checking the Store, Windows Update, and every program's own
updater separately. NEFORUPDATE puts them all in one place, like the Updates page on a phone.

### Features

- **All sources at once.** winget, the Microsoft Store, Chocolatey, Scoop and Windows Update are
  scanned in parallel, with a progress bar for each.
- **One list, no duplicates.** If two package managers can update the same app, it appears once,
  and you choose which one does the update.
- **Pick what to update.** Untick anything you want to skip; NEFORUPDATE remembers your choices.
  Risky updates such as graphics and audio drivers start unticked.
- **Safe, one at a time.** Updates run one after another so installers never collide. One failed
  update never stops the rest, and each failure says why in plain words.
- **Updates for "untracked" programs.** Many programs aren't known to any package manager.
  NEFORUPDATE lists them, suggests matching winget packages, and once you confirm a match, keeps
  them up to date too.
- **Never restarts your PC.** Updates that need a restart are listed so you can restart when it suits you.
- **Light and dark theme**, following Windows by default.
- **Full log** of every command it runs, for troubleshooting.

### How it works

1. Open NEFORUPDATE - it scans every source automatically.
2. Untick anything you don't want updated.
3. Click **Update all** (or **Update selected**) and watch each app update in turn.

### Install

Download the installer and run it. Setup asks whether to install **only for you** (no administrator
rights needed) or **for all users**. NEFORUPDATE then appears in the Start menu and in
Settings > Apps, where it can be uninstalled like any other program.

Prefer not to install? Use the portable version: one file, runs from anywhere.

### System requirements

- Windows 10 or Windows 11, 64-bit.
- **winget** (Microsoft's "App Installer", included with Windows 11 and current Windows 10) for most updates.
- Optional: Chocolatey and/or Scoop - used automatically if installed, skipped if not.
- Optional: Microsoft's WinGet PowerShell module, for the most accurate results and the Untracked
  apps list. NEFORUPDATE offers to install it for you (no administrator rights needed).

### FAQ

**Windows says "Windows protected your PC" when I run the installer.**
NEFORUPDATE isn't code-signed yet, so Microsoft SmartScreen doesn't recognise it. Click
**More info**, then **Run anyway**. You can compare the file's SHA-256 checksum with the one on this page.

**Does it install Windows updates?**
Not yet. It lists pending Windows updates so you can see them in one place; install those from
Settings > Windows Update.

**Will it restart my PC?**
Never. It tells you which updates need a restart.

**Does it need administrator rights?**
Not to run. Some installers ask for permission when they update, and Chocolatey updates ask once
per batch.

**What happens to "untracked" programs?**
They're listed with their publisher and website. When a matching winget package exists,
NEFORUPDATE suggests it; you decide whether to link it. Linking is never automatic.

**How do I uninstall it?**
Settings > Apps > NEFORUPDATE > Uninstall. You'll be asked whether to also remove your settings and logs.

### Open source

NEFORUPDATE is free and open source under the MIT License. The code is on GitHub:
**[github.com/Neforuss/NEFORUPDATE](https://github.com/Neforuss/NEFORUPDATE)**. Anyone can read it,
improve it and suggest changes - bug reports and pull requests are welcome (see CONTRIBUTING.md
in the repository). The NEFORUPDATE name, icon and splash screen stay with Neforus, so if you
publish your own version, give it its own name and look.

### Privacy

NEFORUPDATE runs entirely on your PC. It has no account, no ads and no telemetry. It only
contacts the update services it checks (winget's sources, the Microsoft Store, Windows Update,
and Chocolatey/Scoop if installed) and Microsoft's Store catalog for app names. Web pages and
web searches open only when you click them. Logs stay on your PC in `%LOCALAPPDATA%\NEFORUPDATE`.

### Credits

- NEFORUPDATE is made by **Neforus** - [neforus.com](https://neforus.com).
- Splash screen background by **Jason Benjamin** - [perfecthue.com/wallpapers](https://perfecthue.com/wallpapers/).
- Built with Python and Qt (PySide6, LGPL-3.0); installer made with Inno Setup. Full notices in
  THIRD-PARTY-NOTICES.md (installed next to the app).

### Changelog

**1.2.0 - 2026-10-06 - first public release**
- One window for winget, Microsoft Store, Chocolatey, Scoop and Windows Update updates.
- Parallel scanning with per-source progress; one-at-a-time updating with per-app progress.
- Duplicate detection across package managers, with a preferred-source setting.
- Untracked apps list with winget matching and linking.
- Light/dark theme, splash screen, installer with Start menu entry and uninstaller.

---

## 4. Before publishing - decisions and checks

1. **Licence: decided - MIT** (code), with the name and artwork kept by Neforus (`BRANDING.md`).
   Link the GitHub repository from the page and make sure it's public before the page goes live.
   Attach the release files to a GitHub Release too (tag `v1.2.0`), so the repository has downloads.
2. **Code signing (recommended).** For open-source projects, the SignPath Foundation offers free
   code signing (signpath.org) - worth applying once the repository is public. The installer and portable .exe are unsigned, so SmartScreen
   warns new users (the FAQ above covers it). A code-signing certificate - or Microsoft's Trusted
   Signing service - removes most of that friction. Some antivirus tools also flag unsigned
   PyInstaller apps by mistake; if that happens, submit the file to the vendor (Microsoft:
   https://www.microsoft.com/wdsi/filesubmission).
3. **Credit check.** The splash screen includes "BACKGROUND MADE BY JASON BENJAMIN - perfecthue.com/wallpapers".
   Confirm the wallpaper's licence allows use in a distributed app and on the website.
4. **Checksums.** If the files are rebuilt, the SHA-256 values change. Copy them from
   `..\dist\SHA256SUMS.txt` rather than from this document.
5. **Test the downloads** from the live page on a second PC (download, check the hash, install,
   open, uninstall).

## 5. Facts behind the copy (verified on 2026-10-06)

- Installer: Inno Setup 6.7.3; per-user or all-users install; Start menu entry; optional desktop
  shortcut; Settings > Apps entry (publisher "Neforus", links to neforus.com and this page);
  Win+R name `neforupdate`; closes a running copy before upgrading; uninstaller removes everything
  and asks about settings/logs. Tested: silent per-user install, launch, uninstall.
- File properties of both .exe files: Company "Neforus", Product "NEFORUPDATE", version 1.2.0.0,
  copyright "Made by Neforus - neforus.com".
- Startup: splash appears within about a second; the window opens in a few seconds (longer on PCs
  with thousands of installed fonts).

## 6. Next releases

1. Change `__version__` in `neforupdate\__init__.py` and the numbers in `version_info.txt`.
2. Run `release.cmd` - it builds the installer, the portable .exe and `SHA256SUMS.txt` in `dist\`.
3. Run `python tools\make_screenshots.py` if the interface changed.
4. Upload the new files, update the version, sizes, hashes and changelog on the page.
   Keep old versions' files only if you want to offer them; the installer upgrades in place.
