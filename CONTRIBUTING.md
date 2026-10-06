# Contributing to NEFORUPDATE

Thanks for helping! NEFORUPDATE is open source under the [MIT License](LICENSE). Bug reports,
ideas and pull requests are all welcome.

## Run it from source

Needs Windows 10 or 11 and Python 3.11 or newer.

```
git clone https://github.com/Neforuss/NEFORUPDATE.git
cd NEFORUPDATE
python -m pip install -r requirements.txt
python main.py
```

`python main.py --list --untracked` runs a read-only scan in the terminal - the quickest way to
test source changes without touching anything.

## Build it

```
python -m pip install -r requirements-dev.txt
release.cmd
```

`release.cmd` also needs [Inno Setup 6](https://jrsoftware.org/isdl.php) (`iscc` on PATH; with
Scoop: `scoop bucket add extras` then `scoop install inno-setup`). For just the portable .exe,
run `build.cmd`.

## Where things are

| Path | What |
|---|---|
| `neforupdate/sources/` | One module per update source (winget, Store, Chocolatey, Scoop, linked apps, Windows Update) |
| `neforupdate/sources/base.py` | The `Source` interface every source implements |
| `neforupdate/workers.py` | Background scanning and updating |
| `neforupdate/merge.py` | Merging duplicates across sources |
| `neforupdate/linker.py`, `inventory.py` | Untracked apps and linking them to winget |
| `neforupdate/ui.py`, `untracked_ui.py`, `theme.py` | The window |
| `installer/` | Inno Setup script and wizard art |
| `tools/` | Icon, installer art and screenshot generators |

### Adding a source (pip, npm, a vendor updater...)

1. Create `neforupdate/sources/<name>.py` with a subclass of `Source`.
2. Implement `available()`, `scan()` (return `Candidate`s) and `update()` (or `update_many()`).
3. Add it to `all_sources()` in `neforupdate/sources/__init__.py`, and to `DEFAULT_ORDER` in
   `merge.py` and `UPDATE_ORDER` in `workers.py`.

## Ground rules for changes

- **Never change a user's system without them asking.** Scanning must stay read-only; updates only
  run after the user clicks Update. Never restart the PC.
- **One update at a time**, and one failed update must not stop the others.
- **Explain failures in plain words** (see `ERRORS` in `sources/winget.py`).
- Keep the UI responsive: slow work goes in the background workers, never on the UI thread.
- Match the existing code style; keep comments short and useful.

## Pull requests

1. Fork, make a branch, make your change.
2. Test it: run `python main.py --list --untracked`, and open the window to check what you changed.
3. Describe what you changed and how you tested it.

## Reporting bugs

Open an issue with: what you did, what happened, what you expected, your Windows version, and the
relevant part of the log (*Open log file* in the app, or `%LOCALAPPDATA%\NEFORUPDATE\logs`).
Remove anything private from the log first - it lists programs installed on your PC.

**Security problems:** please don't post them publicly. Report them privately through GitHub
(the repository's *Security* tab > *Report a vulnerability*).

## Name and artwork

The code is MIT, but the NEFORUPDATE name, icon and splash screen are not - see
[BRANDING.md](BRANDING.md). If you publish your own version, give it its own name and art.
