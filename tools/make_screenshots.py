"""Website screenshots of the real NEFORUPDATE window, filled with demo data (never your own app list).

    python tools\\make_screenshots.py

Writes website\\*.png. Nothing is scanned, installed or saved: no settings are changed.
"""
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neforupdate import linker, rules, theme, ui, untracked_ui  # noqa: E402
from neforupdate.inventory import UntrackedApp  # noqa: E402
from neforupdate.sources.base import Candidate  # noqa: E402

OUT = ROOT / "website"

C = Candidate
DEMO = {
    "winget": [C("winget", "Mozilla.Firefox", "Mozilla Firefox", "140.0", "141.0.2"),
               C("winget", "VideoLAN.VLC", "VLC media player", "3.0.20", "3.0.21"),
               C("winget", "Microsoft.VisualStudioCode", "Microsoft Visual Studio Code", "1.101.2", "1.102.0"),
               C("winget", "7zip.7zip", "7-Zip", "24.08", "25.01"),
               C("winget", "Notepad++.Notepad++", "Notepad++", "8.8.1", "8.8.3"),
               C("winget", "OBSProject.OBSStudio", "OBS Studio", "31.0.3", "31.1.0"),
               C("winget", "Nvidia.PhysX", "NVIDIA PhysX System Software", "9.23.1019", "9.26.0703"),
               C("winget", "Discord.Discord", "Discord", "1.0.9260", "1.0.9261")],
    "choco": [C("choco", "7zip", "7zip", "24.08", "25.01"), C("choco", "git", "git", "2.49.0", "2.50.1")],
    "scoop": [C("scoop", "ffmpeg", "ffmpeg", "7.1", "7.1.1")],
    "msstore": [C("msstore", "9WZDNCRFHVN5", "Windows Calculator", "11.2502.2.0", "Newer version"),
                C("msstore", "9MSMLRH6LZF3", "Windows Notepad", "11.2504.50.0", "Newer version")],
    "linked": [C("linked", "qBittorrent.qBittorrent", "qBittorrent", "5.1.0", "5.2.4",
                 note="Linked by you - installs winget's version over the installed copy")],
    "wu": [C("wu", "demo-wu", "Security Intelligence Update for Microsoft Defender Antivirus - KB2267602",
             "", "KB2267602", note="List-only: install from Settings > Windows Update", locked=True)],
}

UNTRACKED = [
    UntrackedApp(id="ARP\\demo\\1", name="qBittorrent", version="5.1.0", publisher="The qBittorrent project",
                 scope="All users (64-bit)", website="https://www.qbittorrent.org", link_id="qBittorrent.qBittorrent",
                 latest="5.2.4", installed_on="2025-03-14"),
    UntrackedApp(id="ARP\\demo\\2", name="Mullvad VPN", version="2025.14.0", publisher="Mullvad VPN AB",
                 scope="All users (64-bit)", website="https://mullvad.net", installed_on="2025-08-02", searched=True,
                 matches=[linker.Match("MullvadVPN.MullvadVPN", "Mullvad VPN", "2026.4", 100)]),
    UntrackedApp(id="ARP\\demo\\3", name="Brave", version="154.1.96.61", publisher="Brave Software Inc",
                 scope="All users (32-bit)", installed_on="2026-01-20", searched=True,
                 matches=[linker.Match("Brave.Brave", "Brave", "154.1.96.61", 100)]),
    UntrackedApp(id="ARP\\demo\\4", name="4K Video Downloader", version="4.33.5.172", publisher="Open Media LLC",
                 scope="All users (32-bit)", installed_on="2025-11-09", searched=True,
                 matches=[linker.Match("OpenMedia.4KVideoDownloader", "4K Video Downloader", "4.33.5.0172", 100)]),
    UntrackedApp(id="ARP\\demo\\5", name="Example Synth Plugin", version="2.3.1", publisher="Example Audio",
                 scope="All users (64-bit)", website="https://example.com", installed_on="2024-07-15", searched=True),
    UntrackedApp(id="ARP\\demo\\6", name="Retro Game Launcher", version="1.0.4", publisher="Demo Games",
                 scope="This user", installed_on="2023-12-01", searched=True),
]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    ui.MainWindow.start_scan = lambda self: None       # demo only: never scan
    ui.MainWindow.closeEvent = lambda self, e: e.accept()  # never save window size
    w = ui.MainWindow(app)

    def use_theme(dark: bool) -> None:  # switch look without saving the user's theme choice
        w.tokens = theme.apply(app, dark)
        w._dark = dark
        w.theme_box.blockSignals(True)      # show the matching choice without saving it
        w.theme_box.setCurrentIndex(2 if dark else 1)
        w.theme_box.blockSignals(False)
        theme.set_title_bar(int(w.winId()), dark)
        w.model.refresh_all()

    for sid, cands in DEMO.items():
        for c in cands:
            rules.apply(c)
        w.cands[sid] = cands
    w.rebuild()
    counts = {"winget": 8, "msstore": 2, "choco": 2, "scoop": 1, "linked": 1, "wu": 1}
    for sid, chip in w.chips.items():
        chip.set_state("done", f"{counts[sid]} found")
    w.banner.hide()
    w.resize(1400, 820)
    w.show()

    def updating_state() -> None:
        # mid-update: two done, one downloading, the rest waiting
        by_name = {i.name: i for i in w.model.items}
        for i in w.model.items:
            if i.selected and not i.locked:
                i.state, i.status = "queued", "Waiting"
        for n in ("Mozilla Firefox", "7-Zip"):
            by_name[n].state, by_name[n].status = "ok", "Updated"
        vlc = by_name["VLC media player"]
        vlc.state, vlc.status, vlc.progress = "running", "Downloading 45%", 45.0
        w.update_counts()                   # real "N updates found - N selected" before going busy
        w.set_busy(True, updating=True)
        w.overall.setRange(0, 1000)
        w.overall.setValue(330)
        w.current.show()
        w.current.setRange(0, 100)
        w.current.setValue(45)
        n = sum(1 for i in w.model.items if i.selected and not i.locked)
        w.overall_label.setText(f"Updating 3 of {n}: VLC media player - Downloading 45%")
        w.model.refresh_all()

    steps = []

    def shot(name: str) -> None:
        w.grab().save(str(OUT / name))
        print("wrote", OUT / name)

    def s1():
        use_theme(True)
        w.tabs.setCurrentIndex(0)
        updating_state()
    steps += [s1, lambda: shot("neforupdate-updates-dark.png")]

    def s2():
        use_theme(False)
    steps += [s2, lambda: shot("neforupdate-updates-light.png")]

    def s3():
        use_theme(True)
        w.set_busy(False)
        w.current.hide()
        w._scan_label()                     # back to "winget ✓ · Microsoft Store ✓ ..."
        w.overall.setRange(0, 1)
        w.overall.setValue(1)
        w.untracked.set_apps(UNTRACKED)
        w.untracked.notice.setText("Searched 6 of 6 apps. Likely winget packages for 3 app(s), 1 with a newer "
                                   "version. Click Review matches to link them.")
        w.untracked.notice.show()
        w.untracked._buttons()
        w.untracked._update_count()
        w.tabs.setCurrentIndex(1)
    steps += [s3, lambda: shot("neforupdate-untracked.png")]

    def s4():
        d = untracked_ui.ReviewDialog(w.untracked, w.untracked.reviewable())
        d.show()
        QTimer.singleShot(400, lambda: (d.grab().save(str(OUT / "neforupdate-review-matches.png")),
                                        print("wrote", OUT / "neforupdate-review-matches.png"), d.close()))
    steps += [s4, lambda: None]

    def run(i=0):
        if i < len(steps):
            steps[i]()
            QTimer.singleShot(600, lambda: run(i + 1))
        else:
            app.quit()

    QTimer.singleShot(500, run)
    app.exec()

    shutil.copy(ROOT / "assets" / "splash.png", OUT / "neforupdate-splash.png")
    shutil.copy(ROOT / "assets" / "icon.png", OUT / "neforupdate-icon-512.png")
    print("copied splash and icon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
