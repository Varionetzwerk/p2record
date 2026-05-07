# P2-Record

**Linux game clip recorder** — like Medal.tv or ShadowPlay, but native.

P2-Record runs silently in the background, recording your screen into a rolling ring buffer. Press a hotkey and the last N seconds are saved as a clip. No browser, no cloud, no subscription.

---

## Features

- **Ring buffer** — FFmpeg runs continuously, only the last N seconds are kept
- **VAAPI hardware encoding** — `h264_vaapi` via AMD/Intel GPU, near-zero CPU overhead
- **Wayland & X11** — xdg-desktop-portal + PipeWire on Wayland, x11grab on X11, auto-detected
- **Flexible audio** — None / Desktop / Mic / Both (mixed via FFmpeg amix)
- **Global hotkeys** — evdev backend (works even with grabbed inputs), X11 fallback
- **Clip library** — thumbnails, duration, date; open or delete without a file manager
- **GTK4 + Libadwaita** — native look, dark mode, system theme integration
- **DE / EN** — full UI in German and English

---

## Installation

### AUR (recommended)

```bash
yay -S p2record-git
```

### Manual

```bash
git clone https://aur.archlinux.org/p2record-git.git
cd p2record-git
makepkg -si
```

---

## Default hotkeys

| Key | Action |
|-----|--------|
| `F8` | Start / stop recording |
| `F9` | Save clip (last N seconds) |

Hotkeys are freely configurable in the settings.

---

## Requirements

**Required:**
`python` `python-gobject` `gtk4` `libadwaita` `ffmpeg` `python-evdev` `python-xlib` `python-dbus` `gstreamer` `gst-plugins-base` `gst-plugin-pipewire`

**Wayland:**
`xdg-desktop-portal` + one of: `xdg-desktop-portal-gnome` / `-kde` / `-wlr`

**Audio:**
`pipewire-pulse` (recommended) or `pulseaudio`

**Optional:**
`libayatana-appindicator` (system tray)

---

## How it works

```
FFmpeg (ring buffer)
  └─ writes 5-second segments continuously
       └─ F9 pressed → SIGUSR1 → FFmpeg cuts at next keyframe
            └─ last N segments → ffmpeg concat → clip.mkv
```

---

## Bugs & feature requests

Please use the [GitHub Issues](https://github.com/Varionetzwerk/p2record/issues) page.
Use the **Bug Report** template and include terminal output (`p2record` run from terminal).

---

## License

MIT
