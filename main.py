"""NEFORUPDATE entry point. Made by Neforus (https://neforus.com).

  python main.py          open the window
  python main.py --list   scan every source and print the merged list (read-only, no window)
  python main.py --list --untracked   ...plus installed programs no package manager tracks
"""
import sys


def list_only() -> int:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from neforupdate.logger import Logger
    from neforupdate.merge import DEFAULT_ORDER, merge
    from neforupdate.runner import ProcessRegistry
    from neforupdate.settings import Settings
    from neforupdate.sources import all_sources
    from neforupdate.workers import scan_one

    log = Logger()
    cancel, registry = threading.Event(), ProcessRegistry()
    sources = all_sources()
    settings = Settings().as_source_settings()   # includes the apps you linked in the window

    def one(src):
        def state(st, text):
            if st != "scanning":
                print(f"  {src.name:<16} {st:<9} {text}", file=sys.stderr, flush=True)
        return scan_one(src, log, cancel, registry, settings, state) or []

    print("Scanning (read-only)...", file=sys.stderr, flush=True)
    with ThreadPoolExecutor(max_workers=len(sources)) as ex:
        cands = [c for lst in ex.map(one, sources) for c in lst]
    items = merge(cands, DEFAULT_ORDER, {})
    items.sort(key=lambda i: (DEFAULT_ORDER.index(i.chosen), i.name.lower()))
    print(f"\n{'Tick':<5}{'Name':<44}{'Installed':<18}{'Available':<18}{'Via':<22}Note")
    for i in items:
        tick = "-" if i.locked else (" " if i.caution else "x")
        via = i.chosen + (f" (+{','.join(s for s in i.candidates if s != i.chosen)})" if len(i.candidates) > 1 else "")
        print(f"{tick:<5}{i.name[:42]:<44}{i.installed[:16]:<18}{i.available[:16]:<18}{via:<22}{i.note}")
    print(f"\n{len(items)} updates; log: {log.path}", file=sys.stderr)

    if "--untracked" in sys.argv:
        from neforupdate import inventory
        apps = inventory.from_sources(sources)
        if apps is None:
            print("\nUntracked apps: not available (needs the Microsoft.WinGet.Client module)")
        else:
            print(f"\n{'Untracked app':<46}{'Version':<16}{'Publisher':<30}{'Type':<20}{'Linked to':<30}Website")
            for a in apps:
                print(f"{a.name[:44]:<46}{a.version[:14]:<16}{a.publisher[:28]:<30}{a.scope:<20}"
                      f"{a.link_id[:28]:<30}{a.website}")
            print(f"\n{len(apps)} untracked apps", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if "--list" in sys.argv and sys.stdout is not None:  # the windowed .exe has no console
        sys.exit(list_only())
    from neforupdate.ui import run_gui
    sys.exit(run_gui())
