#!/usr/bin/env bash
# P2-Record GTK4 — install script (Arch / Ubuntu / Fedora)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> P2-Record GTK4 Setup"
echo ""

# ── Detect distro ──────────────────────────────────────────────────────────────
if command -v pacman &>/dev/null; then
  DISTRO=arch
elif command -v apt &>/dev/null; then
  DISTRO=ubuntu
elif command -v dnf &>/dev/null; then
  DISTRO=fedora
else
  echo "Unbekannte Distribution. Bitte manuell installieren."
  DISTRO=unknown
fi

# ── System packages ────────────────────────────────────────────────────────────
echo "==> Installiere System-Pakete ($DISTRO)…"

if [[ $DISTRO == arch ]]; then
  sudo pacman -S --needed --noconfirm \
    python python-gobject python-pip \
    gtk4 libadwaita \
    ffmpeg \
    python-evdev \
    xdg-desktop-portal

elif [[ $DISTRO == ubuntu ]]; then
  sudo apt-get update -qq
  sudo apt-get install -y \
    python3 python3-gi python3-gi-cairo python3-pip \
    gir1.2-gtk-4.0 gir1.2-adw-1 \
    libgtk-4-dev libadwaita-1-dev \
    ffmpeg \
    python3-evdev \
    xdg-desktop-portal

elif [[ $DISTRO == fedora ]]; then
  sudo dnf install -y \
    python3 python3-gobject python3-pip \
    gtk4 libadwaita \
    ffmpeg \
    python3-evdev \
    xdg-desktop-portal
fi

# ── Python packages ────────────────────────────────────────────────────────────
echo ""
echo "==> Installiere Python-Pakete…"
pip install --user -r "$SCRIPT_DIR/requirements.txt" || \
  pip3 install --user -r "$SCRIPT_DIR/requirements.txt"

# ── evdev group ────────────────────────────────────────────────────────────────
echo ""
if ! groups | grep -q input; then
  echo "==> Füge $USER zur 'input' Gruppe hinzu (für Wayland-Hotkeys)…"
  sudo usermod -aG input "$USER"
  echo "    ⚠  Bitte neu einloggen damit die Gruppe aktiv wird!"
else
  echo "==> ✓ $USER ist bereits in der 'input' Gruppe"
fi

# ── Desktop entry ──────────────────────────────────────────────────────────────
DESKTOP_FILE="$HOME/.local/share/applications/p2record.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=P2-Record
Comment=Game Clip Recorder
Exec=python3 $SCRIPT_DIR/main.py
Icon=video-display
Categories=Game;Recorder;
StartupNotify=true
EOF

echo ""
echo "==> ✓ Desktop-Eintrag erstellt: $DESKTOP_FILE"

# ── Launcher ───────────────────────────────────────────────────────────────────
LAUNCHER="$HOME/.local/bin/p2record"
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec python3 "$SCRIPT_DIR/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"

echo "==> ✓ Launcher: $LAUNCHER"
echo ""
echo "==> Installation abgeschlossen!"
echo "    Starten mit:  p2record"
echo "    Oder:         python3 $SCRIPT_DIR/main.py"
