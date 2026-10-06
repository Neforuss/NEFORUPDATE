# NEFORUPDATE name and artwork

The **source code** of NEFORUPDATE is open source under the [MIT License](LICENSE).
The **name and artwork are not** covered by that licence:

| What | Files | Terms |
|---|---|---|
| The name "NEFORUPDATE" and the Neforus name | - | All rights reserved by Neforus |
| Icon | `assets/icon.png`, `assets/neforupdate.ico`, `website/neforupdate-icon-512.png`, `installer/wizard-*.bmp` | All rights reserved by Neforus |
| Splash screen | `assets/splash.png`, `website/neforupdate-splash.png` | All rights reserved by Neforus. The background image is by **Jason Benjamin** ([perfecthue.com/wallpapers](https://perfecthue.com/wallpapers/)) and is under his terms, not ours |

These files are in the repository so the official app can be built from source. That's fine.

## Making your own version (a fork)

You're welcome to change, rebuild and share NEFORUPDATE under the MIT License. If you **publish**
a modified version, please:

1. **Give it a different name**, so people can tell it apart from the official NEFORUPDATE.
2. **Replace the icon and splash screen** with your own:
   - `python tools\make_icon.py your-icon.png` (writes `assets\neforupdate.ico` and `assets\icon.png`)
   - replace `assets\splash.png` with your own 1280x720 image
   - `python tools\make_installer_images.py` (installer artwork)
3. **Change the installer's `AppId`** in `installer\neforupdate.iss`, so your installer doesn't
   upgrade or uninstall the official one, and update the publisher names and links there and in
   `version_info.txt`.
4. Keep the MIT copyright notice (`LICENSE`), as the licence requires. "Based on NEFORUPDATE by
   Neforus" in your README is appreciated.

Private builds for yourself don't need any of this.
