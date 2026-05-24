#!/bin/bash
set -e

INSTALL_DIR="$HOME/.local/share/watercooler"
BIN_DIR="$HOME/.local/bin"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="watercooler"

echo "=== Water Cooler CLI — Rootless Install ==="
echo ""

# --- Check dependencies ---
echo "Checking dependencies..."
for cmd in python3 pip3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found — install Python 3 first"
        exit 1
    fi
done

# Check bluetooth service is running (system-wide)
if ! systemctl is-active --quiet bluetooth 2>/dev/null; then
    echo "WARNING: bluetooth service not running. You may need:"
    echo "  sudo systemctl enable --now bluetooth"
    echo "(This is the only step that may need sudo)"
fi

# Enable lingering so user services run without login
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
    echo "NOTE: Enable lingering so the daemon keeps running after logout:"
    echo "  sudo loginctl enable-linger $USER"
fi

# --- Install app ---
echo ""
echo "Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$(dirname "$0")/watercooler.py" "$INSTALL_DIR/"
cp "$(dirname "$0")/requirements.txt" "$INSTALL_DIR/"

# --- Create venv + install deps ---
echo "Setting up Python venv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q 2>/dev/null || true
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
echo "Done."

# --- Create default configs ---
mkdir -p "$INSTALL_DIR"
if [ ! -f "$INSTALL_DIR/rgb.conf" ]; then
    echo '{"mode": "static", "hex": "#00ffff"}' > "$INSTALL_DIR/rgb.conf"
    echo "Created default RGB config (Cyan static)"
fi
if [ ! -f "$INSTALL_DIR/speed.conf" ]; then
    echo '{"mode": "auto"}' > "$INSTALL_DIR/speed.conf"
    echo "Created default speed config (Auto)"
fi

# --- Install wrapper ---
echo ""
echo "Installing CLI wrapper to $BIN_DIR/watercooler..."
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/watercooler" <<WRAPPER
#!/bin/bash
export WATERCOOLER_CONF_DIR="$INSTALL_DIR"
exec "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/watercooler.py" "\$@"
WRAPPER
chmod +x "$BIN_DIR/watercooler"
echo "Done."

# --- Install user systemd service ---
echo ""
echo "Installing user systemd service..."
mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_DIR/$SERVICE_NAME.service" <<SERVICE
[Unit]
Description=Water Cooler Auto Speed Daemon
After=bluetooth.target
Wants=bluetooth.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/watercooler.py daemon
Restart=on-failure
RestartSec=10

Environment=WATERCOOLER_CONF_DIR=$INSTALL_DIR
Environment=DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload
echo "Done."

# --- Check PATH ---
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "NOTE: $BIN_DIR is not in your PATH. Add this to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$PATH:$BIN_DIR\""
fi

echo ""
echo "=== Installed ==="
echo ""
echo "CLI usage:"
echo "  watercooler scan"
echo "  watercooler pump --voltage 8"
echo "  watercooler fan --speed 75"
echo "  watercooler temp"
echo ""
echo "Daemon (auto speed) — runs as user service:"
echo "  systemctl --user start ${SERVICE_NAME}"
echo "  systemctl --user enable ${SERVICE_NAME}   # start on login"
echo "  systemctl --user status ${SERVICE_NAME}"
echo "  journalctl --user -u ${SERVICE_NAME} -f   # view logs"
echo ""
echo "To uninstall:"
echo "  systemctl --user stop ${SERVICE_NAME} && systemctl --user disable ${SERVICE_NAME}"
echo "  rm -rf $INSTALL_DIR $BIN_DIR/watercooler $SERVICE_DIR/${SERVICE_NAME}.service"
echo "  systemctl --user daemon-reload"
