# AbletonMCP Windows Installer

One-step setup for the Windows side of AbletonMCP. It installs all three parts of
the app:

| Component | Installed to |
|-----------|--------------|
| Python MCP server + REST API (isolated venv) | `%LOCALAPPDATA%\AbletonMCP\venv` |
| Ableton remote script | `<Live User Library>\Remote Scripts\AbletonMCP\` |
| Max for Live device (built from source) | `<Live User Library>\Presets\Audio Effects\Max Audio Effect\AbletonMCP\` |

## Run it

Double-click `Install-AbletonMCP.cmd`, or from PowerShell in the repository root:

```powershell
.\installer\AbletonMCP-Setup.ps1
```

Useful options:

```powershell
.\installer\AbletonMCP-Setup.ps1 -DryRun            # show every action, change nothing
.\installer\AbletonMCP-Setup.ps1 -ConfigureClaude   # also register Claude Desktop's MCP server
.\installer\AbletonMCP-Setup.ps1 -SkipPython        # remote script + M4L device only
.\installer\AbletonMCP-Setup.ps1 -NoM4LDevice       # skip the Max for Live device
.\installer\AbletonMCP-Setup.ps1 -SystemWide        # also copy to Live's own MIDI Remote Scripts (elevated)
.\installer\AbletonMCP-Setup.ps1 -Uninstall         # remove everything it created
```

## Live versions

The installer detects every installed Ableton Live version and reports the newest
one as the maximum. A folder only counts as an installation when it contains
`Resources\MIDI Remote Scripts`, so Live's preference folders
(`%APPDATA%\Ableton\Live 12.2.5` and friends) are never reported as installs and are
never used by `-SystemWide`. The remote script goes into the
User Library, which Live 10 and newer all use, so one install covers every version
on the machine, including the newest.

The User Library is not always `<Documents>\Ableton`: if you moved it (a OneDrive
folder, another drive), Live records the real path in its `Library.cfg`. The
installer reads that file for every installed Live version, newest first, and uses
the configured library; `<Documents>\Ableton` is only the fallback. A folder outside
the library - such as the one an older build of this installer created under
`<Documents>` - is never scanned by Live, and shows up as missing from the Control
Surface list.

`-SystemWide` additionally drops a copy into
the newest Live's `Resources\MIDI Remote Scripts`.

## What the installer needs

- Windows PowerShell 5.1 (built in)
- [uv](https://astral.sh/uv) or any Python 3.10+ — with `uv` the installer fetches
  Python 3.13 automatically
- Ableton Live 10+; the Max for Live device requires Live Suite or the M4L add-on

## After installing

1. Start Ableton Live.
2. Settings > Link, Tempo & MIDI > Control Surface: select **AbletonMCP**, Input/Output: **None**.
3. REST API: Start Menu > AbletonMCP > **AbletonMCP REST API** (http://127.0.0.1:8000/docs).
4. Max for Live device: Browser > User Library > Audio Effects > Max Audio Effect > **AbletonMCP**.

Log: `%LOCALAPPDATA%\AbletonMCP\logs\install.log`.

## Building the device by hand

```bash
python scripts/build_amxd.py --verify
```

This writes `AbletonMCP_M4L/AbletonMCP.amxd` from `AbletonMCP_M4L/AbletonMCP.amxd.maxpat`.

## Uninstall

Settings > Apps > **AbletonMCP**, Start Menu > AbletonMCP > **Uninstall AbletonMCP**,
or `.\installer\AbletonMCP-Setup.ps1 -Uninstall`. User library folders that other
devices use are kept.
