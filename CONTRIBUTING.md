# Contributing to P2-Record

Thanks for your interest in contributing! Issues and pull requests are welcome —
in **English or German**, whichever you prefer.

## Reporting bugs & requesting features

Please use the issue templates:

- [Bug Report](https://github.com/Varionetzwerk/p2record/issues/new?template=bug_report.yml)
- [Feature Request](https://github.com/Varionetzwerk/p2record/issues/new?template=feature_request.yml)

For bugs, always include your display server (Wayland/X11), GPU, and the output
of the app when run from a terminal (`p2record` or `python python/main.py`).
The FFmpeg log at `/tmp/p2record_ffmpeg.log` is usually the most helpful detail.

## Development setup

P2-Record is Python 3 + GTK4/Libadwaita. On Arch Linux:

```bash
sudo pacman -S python-gobject gtk4 libadwaita ffmpeg \
               gst-plugin-pipewire gstreamer xdg-desktop-portal \
               python-dbus python-evdev python-xlib
git clone https://github.com/Varionetzwerk/p2record.git
cd p2record
python python/main.py
```

For in-game hotkeys (evdev backend) your user must be in the `input` group:

```bash
sudo usermod -aG input $USER   # then re-login
```

## Project layout

| Path                 | Purpose                                              |
| -------------------- | ---------------------------------------------------- |
| `python/core/`       | Recording, portal/PipeWire, hotkeys, clips, settings |
| `python/ui/`         | GTK4 application, window, pages                      |
| `python/resources/`  | CSS theme                                            |
| `python/core/i18n.py`| All UI strings (DE/EN) — add both languages          |

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Keep changes focused — one fix or feature per PR.
3. Every user-visible string goes through `t('key')` in `core/i18n.py`
   with **both** a `de` and an `en` entry.
4. Test on your display server and mention in the PR whether you tested
   Wayland, X11, or both.
5. Make sure the app starts cleanly: `python python/main.py`.

There is no CI yet, so please compile-check before pushing:

```bash
python -m py_compile python/main.py python/core/*.py python/ui/*.py python/ui/pages/*.py
```
