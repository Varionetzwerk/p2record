# Security Policy

## Supported Versions

Only the latest release is supported with security fixes.

| Version        | Supported |
| -------------- | --------- |
| latest (0.2.x) | ✅        |
| older releases | ❌        |

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report them privately:

- **Email:** metzs843@gmail.com
- Or use GitHub's private vulnerability reporting on this repository
  (*Security → Report a vulnerability*), if enabled.

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce (proof of concept if possible)
- Your environment (distro, display server, P2-Record version)

You can expect an initial response within **7 days**. Once the issue is
confirmed, a fix will be released as soon as possible and you will be credited
in the release notes unless you prefer to remain anonymous.

## Scope notes

P2-Record runs locally and records the user's own screen. Reports are
especially welcome for anything that could:

- expose recordings or the ring buffer to other local users
  (e.g. predictable paths in `/tmp` with wrong permissions)
- allow command injection via file names, settings, or game titles
- escalate privileges through the evdev/input-group integration
