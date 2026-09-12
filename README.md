# OmaBridge

**English** | [Deutsch](README.de.md)

[![CI](https://github.com/flathack/OmaBridge/actions/workflows/ci.yml/badge.svg)](https://github.com/flathack/OmaBridge/actions/workflows/ci.yml)

Open Citrix StoreFront from the **Omarchy bar**: choose a site, sign in with your
username, password and TOTP, then launch a published app or virtual desktop from
the Citrix portal.

![OmaBridge with site and session tabs (preview)](docs/tabs.png)

## Features

- Add, edit and remove multiple sites; select them directly from the bar popup.
- Store usernames, passwords and TOTP secrets in the Linux keyring (Secret Service).
- Automatic sign-in for recognized StoreFront forms, including multiple steps.
- Choose **Citrix Workspace** or **Browser / HTML5 inside OmaBridge** for each site.
- Each site has its own browser session that is not persisted to disk. HTML5 popups
  open in additional tabs sharing that session. Open sites stay connected when switching tabs.
- A single 42-pixel top bar with navigation, tabs, add, info and menu controls.
  The portal and VM fill the remaining space, without a sidebar, inner margins or status bar.
- Configure form fields and client selection for customized portals using CSS selectors.
- Further clicks in the bar reuse the running OmaBridge window.

## Requirements

- Omarchy with the **Quickshell bar** and `omarchy plugin` (this is not a Waybar plugin).
- Python **3.11+**, pip and venv. Installation downloads PySide6, including Qt WebEngine.
- A running **Secret Service** that can be unlocked, such as GNOME Keyring.
- For native mode: Citrix Workspace for Linux with `wfica` on your PATH or at
  `/opt/Citrix/ICAClient/wfica`.
- For HTML5: a StoreFront portal with the browser client enabled on the server and
  an appropriate HDX/WebSocket configuration.
- Valid HTTPS certificates and a correctly synchronized system clock for TOTP.

## Installation

Clone the repository and install:

```bash
git clone https://github.com/flathack/OmaBridge.git
cd OmaBridge
./scripts/install.sh
```

The script installs the app into `~/.local/share/omabridge/venv`, a launcher into
`~/.local/bin/omabridge`, a desktop entry, and the `local.omabridge` plugin into
`~/.config/omarchy/plugins/`. It backs up an existing `shell.json`, enables the widget
and places it on the right side of the bar. It does not modify Omarchy system files.
XDG_CONFIG_HOME and XDG_DATA_HOME are respected.

Running the script again updates the app and widget while preserving the keyring
and saved sites. `omarchy plugin add` alone does not install the Python app;
use the script for a complete installation.

## Your first connection

The app currently uses German UI labels; the instructions below include those
labels so you can find the corresponding controls.

1. Click **Citrix → Sites verwalten** (manage sites) in the bar, then **+** at the top of OmaBridge.
2. Enter a name and the full **Receiver for Web URL**, for example
   `https://citrix.firma.de/Citrix/StoreWeb/`. Do not save a URL containing a session ticket.
3. Enter your username, password and **TOTP secret**. Base32 secrets and
   `otpauth://totp/...` links are supported; an individual six-digit code is not a secret.
   A QR code must be provided as its otpauth link or secret; image import is not included.
4. Choose the launch mode and save.
5. Select the site in the bar menu. OmaBridge opens the portal and signs in.
6. Select the desired **app or desktop** in the portal.

For client selection, OmaBridge recognizes common English and German buttons such
as “Use web browser”, “Webbrowser verwenden” and “Already installed”. If your portal
uses different controls, select the client manually once or configure a selector
under **Anmeldeformular anpassen** (customize sign-in form). The launch mode is a saved
preference that automatically operates recognized portal buttons; it cannot enable
features blocked by the server or override every existing portal preference.
Changing modes later may require another selection in the portal.

**Browser** means OmaBridge's integrated Chromium browser, not an external Firefox
or Chrome process. Sign-in and the HTML5 session therefore share the same isolated
context. Browser mode never launches a native ICA session by accident.

The top bar stays visible. **⋮** contains site settings, launch mode, sign-in and
fullscreen controls; **ⓘ** shows status and the portal address. **F11** toggles fullscreen,
**Ctrl+Tab** switches tabs, and **Ctrl+W** closes the current tab. Closed sites remain
saved and can be reopened under **⋮ → Gespeicherte Sites** (saved sites).
HTML5 apps and desktops open in their own tabs; closing their parent site tab also
closes these session tabs. Native Workspace windows remain independent.

## Customized sign-in and troubleshooting

Default detection includes `#username`, `#password`, `#otp`, `#passwd1`, common `name`
attributes and `autocomplete` values. Configure custom portals under
**⋮ → Site bearbeiten → Anmeldeformular anpassen** (edit site → customize sign-in form):

| Field | Example CSS selector |
| --- | --- |
| Username | `#username` |
| Password | `#password` |
| TOTP | `#verificationCode` |
| Sign-in button | `#loginBtn` |
| Browser selection | `#useHtml5` (only if this element exists in the portal) |

For two-step sign-in, OmaBridge waits for the code form after submitting the username
and password, then generates a fresh TOTP for that step. Citrix nFactor forms with
an `input#response` of type `password` and the label “Kennwort” are also recognized
using visible prompts such as “Enter Your Microsoft verification code”. Without an
unambiguous prompt, a generic password field is not treated as a TOTP field.
OmaBridge continues watching for a submit button that appears later.

OmaBridge only fills visible, unambiguous fields in the main document on the exact
saved HTTPS origin. A redirect to another host or port, sign-in inside an iframe,
unknown fields or a password change stops automatic credential submission.
Continue manually in the portal in those cases. The current portal address is
available under **ⓘ**, with query parameters and fragments removed.

Each field combination is submitted at most once per connection attempt, with a
maximum of three steps overall. Each submitted step starts a new 90-second window
for the next form. If an error appears, check your credentials first.
**Anmeldung erneut** (retry sign-in) explicitly allows another attempt;
**Automatik pausieren** (pause automation) stops further automatic steps.
TOTP codes with fewer than five seconds remaining are not used.

If the keyring is unavailable, OmaBridge displays an error rather than falling back
to plaintext files. If `wfica` is missing, install Workspace or choose browser mode.
If the portal still returns an ICA file in browser mode, OmaBridge prompts you to
select HTML5 in the portal.

## Privacy and sessions

- `~/.config/omabridge/sites.json` stores site IDs, names, URLs, launch modes and form
  settings. Writes are atomic; directory permissions are `0700`, file permissions `0600`.
- Secret Service stores the username, password and TOTP secret together for each
  site ID. There is no plaintext fallback. Credentials also reside in process memory during use.
- The bar plugin only receives the site ID, display name and launch mode. It has no
  credential API of its own. Other processes running as the same Linux user are not
  separated by a security boundary.
- Automation runs in an isolated JavaScript context. Portal fields receive the
  values needed to sign in; the TOTP secret itself is never injected into the portal.
- ICA downloads are accepted only from the saved portal origin, validated and saved
  under random filenames in a private temporary directory. Workspace receives only
  the file path as an argument, not shell commands. `RemoveICAFile=yes`, process exit,
  a five-minute timeout and app shutdown provide ticket cleanup.
- The Chromium sandbox and certificate validation remain enabled. Portal console
  logs are suppressed. OmaBridge has no telemetry or remote data storage.
- **Tab schließen** (close tab) on a site tab discards the local context. This is not
  a server-side logoff; sign out in the Citrix portal first if needed. Native Workspace
  sessions continue independently; integrated HTML5 tabs close with their portal session.

## Development and testing

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Changes:
[CHANGELOG.md](CHANGELOG.md). Release preparation:
[docs/releasing.md](docs/releasing.md). These supporting documents are currently in German.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
./scripts/run.sh
.venv/bin/python -m pytest -q
bash scripts/check-plugin.sh
.venv/bin/python scripts/preview.py
```

Tests cover TOTP against RFC 6238 vectors, private and atomic storage, keyring errors,
site management with rollback, Chromium sign-in forms, origin checks, retry limits,
client selection and ICA handoff. Form and download tests use local fixtures;
they **do not prove that a real Citrix connection works**.

The initial version has not yet been tested against a real customer StoreFront.
Portal detection, client selection and HDX compatibility must be verified against
the specific installation. There is no separate StoreFront API resource catalog:
apps and desktops are selected in the original portal. SAML automation, push MFA,
client certificates and session transfer to an external browser are not implemented.

Technical references: [Citrix StoreFront Web API](https://developer-docs.citrix.com/en-us/storefront/storefront-web-api/getting-started.html),
[Citrix browser access](https://docs.citrix.com/en-us/storefront/current-release/get-started/user-access-options.html),
[Qt WebEngine Profile](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineProfile.html).

## Removal

`omarchy plugin disable local.omabridge` removes the widget from the bar. You can then
remove the app files, launcher and desktop entry. To remove stored credentials as well,
delete the sites in OmaBridge first; disabling the widget intentionally preserves credentials.
