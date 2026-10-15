# AI installation runbook — Cube Baby Editor

This file is written **for an AI agent with shell access** (Claude Code, Codex, Gemini CLI, etc.)
that has been asked by a user to install Cube Baby Editor. Humans can follow it too.

Follow the steps **in order**. Each step has a **check**; do not continue if a check fails —
go to the matching entry in [If something fails](#if-something-fails).

## Ground rules (read before running anything)

1. **Never write firmware to the pedal** and never run commands that erase or write the pedal's
   flash outside this program. Installing the editor needs no such action.
2. **Do not download or redistribute Cuvave files** (`BCIF.bin`, firmware `.up` files, `CubeSuite.exe`)
   from unofficial sources. The editor works without them; only the optional "factory IRs" button
   needs `BCIF.bin`, which the user obtains from the official CubeSuite download.
3. Commands with `sudo` need the user's password. If you cannot enter it, **show the exact command
   to the user and ask them to run it**, then continue after they confirm.
4. Do not run the editor while CubeSuite (Wine) is running — ask the user to close CubeSuite first.
5. Report results honestly: if a check fails, say so and show the output.

## Step 1 — Identify the system

```bash
. /etc/os-release && echo "$PRETTY_NAME | ID=$ID | VERSION_ID=$VERSION_ID | ID_LIKE=$ID_LIKE"
python3 --version
```

Choose the path:

| System | Path |
|---|---|
| Ubuntu ≥ 24.04, Zorin ≥ 18, Linux Mint ≥ 22, Pop!_OS ≥ 24.04, Debian ≥ 12 (and derivatives) | **Path A — .deb** |
| Older Ubuntu/Debian derivatives (e.g. Ubuntu 22.04, Mint 21) | **Path B — virtual environment** |
| Fedora, Arch, openSUSE, others | **Path B** (or Path C if the system has PyQt6 packages) |

Quick test for Path A eligibility (Debian family):

```bash
apt-cache policy python3-pyqt6 python3-rtmidi | grep -E "^[a-z]|Candidate|Candidato"
```

**Check:** both packages show a candidate version (not `(none)`/`(nenhum)`). Otherwise use Path B.

## Step 2A — Install the .deb (preferred)

```bash
# 1. Download the latest release package
mkdir -p ~/Downloads && cd ~/Downloads
curl -fsSL https://api.github.com/repos/walbertfreitas/cubebaby-editor/releases/latest \
  | python3 -c 'import json,sys; print(next(a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"].endswith("_all.deb")))' \
  | xargs -n1 curl -fLO

# 2. Install it (apt resolves the dependencies automatically)
sudo apt update
sudo apt install -y ./cubebaby-editor_*_all.deb
```

**Check:**

```bash
dpkg -l cubebaby-editor | grep ^ii
command -v cubebaby-editor
PYTHONPATH=/usr/lib/cubebaby-editor python3 -c "import cubebaby.gui; print('import ok')"
```

Expected: the package line starts with `ii`, the command is `/usr/bin/cubebaby-editor`, and
`import ok` is printed. Then go to **Step 3**.

## Step 2B — Virtual environment (any distribution)

```bash
# System pieces: venv support, ALSA headers (to build python-rtmidi if no wheel), Qt xcb cursor lib, git
# Debian/Ubuntu family:
sudo apt install -y python3-venv python3-dev libasound2-dev libxcb-cursor0 git
# Fedora (untested):   sudo dnf install -y python3-devel alsa-lib-devel xcb-util-cursor git
# Arch (untested):     sudo pacman -S --needed python alsa-lib xcb-util-cursor git

git clone https://github.com/walbertfreitas/cubebaby-editor.git ~/cubebaby-editor
cd ~/cubebaby-editor
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install PyQt6 python-rtmidi numpy scipy

# Launcher command and menu entry for the current user
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
cat > ~/.local/bin/cubebaby-editor <<EOF
#!/bin/sh
cd "$HOME/cubebaby-editor" && exec "$HOME/cubebaby-editor/.venv/bin/python" -m cubebaby "\$@"
EOF
chmod +x ~/.local/bin/cubebaby-editor
cp cubebaby/icon.svg ~/.local/share/icons/hicolor/scalable/apps/cubebaby-editor.svg
cp packaging/cubebaby-editor.desktop ~/.local/share/applications/
```

**Check:**

```bash
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -1     # expect: OK (a skip is fine)
.venv/bin/python -c "import cubebaby.gui; print('import ok')"
```

If `~/.local/bin` is not on `PATH`, tell the user to log out and back in (most distributions add it
automatically once the directory exists).

## Step 2C — System packages without the .deb (Fedora/Arch with PyQt6 packaged)

```bash
# Fedora (untested):  sudo dnf install -y python3-pyqt6 python3-rtmidi python3-numpy python3-scipy xcb-util-cursor git
# Arch (untested):    sudo pacman -S --needed python-pyqt6 python-rtmidi python-numpy python-scipy xcb-util-cursor git
git clone https://github.com/walbertfreitas/cubebaby-editor.git ~/cubebaby-editor
cd ~/cubebaby-editor && python3 -c "import cubebaby.gui; print('import ok')"
```

Then create the launcher as in Step 2B, replacing the `.venv/bin/python` path with `/usr/bin/python3`.

## Step 3 — Verify the pedal is visible

Ask the user to **switch the pedal on and connect it via USB** (with a data-capable cable), and to
close CubeSuite if it is running. Then:

```bash
lsusb | grep -i 301a:5555                 # expect: SmartlinkTechnology USB2.0 Device
amidi -l | grep -i "USB2.0 Device"        # expect: a MIDI port "USB2.0 Device MIDI 1"
cat /proc/asound/cards | grep -i "USB2.0" # expect: an audio card "USB2.0 Device"
```

If `amidi` is missing: `sudo apt install alsa-utils` (Debian family).

**Check:** all three commands print a matching line.

## Step 4 — First launch

Ask the user to open **Cube Baby Editor** from the applications menu (or run `cubebaby-editor`).
Tell them what to expect:

- The bottom bar shows `Conectado: Cube Baby AC (chip 0x4FCE)` (the UI is in Portuguese).
- On the very first connection the app backs up the pedal's 8 IRs and 3 presets (~15 s, progress bar)
  and shows a message with the backup folder `~/.local/share/cubebaby-editor/backups/`.

You can confirm the backup afterwards:

```bash
ls -la ~/.local/share/cubebaby-editor/backups/
```

**Check:** files `irs-primeira-conexao-*.bin` (32768 bytes) and `presets-primeira-conexao-*.bin`
(48 bytes) exist.

## Step 5 — Hand over to the user

Summarise for the user: what was installed and how (Path A/B/C), how to open the app, where backups
are, and that **firmware updates are intentionally not supported**. Point them to the README's
"Guide to every pedal function" section.

## If something fails

| Problem | Action |
|---|---|
| `python3-pyqt6` has no candidate | Use Path B. |
| `apt install ./…deb` fails on dependencies | Run `sudo apt update` and retry; if still failing, use Path B and report the error. |
| App error mentioning `xcb` / `xcb-cursor` / "no Qt platform plugin" | Install `libxcb-cursor0` (Debian family) or `xcb-util-cursor` (Fedora/Arch). |
| `pip install python-rtmidi` fails compiling | Install ALSA headers (`libasound2-dev` / `alsa-lib-devel` / `alsa-lib`) and a C compiler (`build-essential`), then retry. |
| `lsusb` doesn't show `301a:5555` | Cable or power issue — ask the user to try another cable/port and make sure the pedal is on. |
| App says "Modelo não suportado" | The pedal isn't a Cube Baby AC. **Stop**; do not try to force it. |
| App says "Pedal não encontrado" but `amidi -l` lists it | Another program holds the port (CubeSuite/Wine, a DAW). Ask the user to close it. |
| Running on Wayland and the window doesn't appear | Try `QT_QPA_PLATFORM=xcb cubebaby-editor` and report the output. |

## Uninstall

```bash
sudo apt remove cubebaby-editor                       # Path A
rm -rf ~/cubebaby-editor ~/.local/bin/cubebaby-editor \
       ~/.local/share/applications/cubebaby-editor.desktop \
       ~/.local/share/icons/hicolor/scalable/apps/cubebaby-editor.svg   # Paths B/C
# User data and backups (only if the user explicitly wants them gone):
# rm -rf ~/.local/share/cubebaby-editor ~/.config/cubebaby-editor
```
