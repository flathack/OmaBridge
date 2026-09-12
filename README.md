# OmaBridge

**English** | [Deutsch](README.de.md)

Automatically log in to **Citrix remote sites** from the Omarchy bar.
Save multiple sites with your username, password and TOTP secret, select a site,
then launch an app or virtual desktop using **Citrix Workspace** or the
**integrated HTML5 browser**.

![OmaBridge preview](docs/tabs.png)

- Credentials stored in the Linux keyring (Secret Service).
- Multi-step sign-in, including a TOTP prompt after username and password.
- A compact top bar with navigation and tabs; the remaining space is yours.

## Install

Requires Omarchy's **Quickshell bar**, Python 3.11+, pip/venv and a working Secret
Service such as GNOME Keyring. Native sessions need Citrix Workspace (`wfica`);
browser sessions need HTML5 enabled on the Citrix server.

```bash
git clone https://github.com/flathack/OmaBridge.git
cd OmaBridge
./scripts/install.sh
```

The installer sets up the app and bar widget under your user account.
Run it again to update. `omarchy plugin add` alone does not install the Python app.

## Use

Click **Citrix → Sites verwalten**, then **+**. Enter the portal's HTTPS URL,
your credentials and a **TOTP secret** (Base32 or `otpauth://` link, not a one-time
code). Choose Workspace or Browser, save, and select the site from the bar.
Choose the app or desktop in the Citrix portal. Settings are under **⋮**.
The app's UI currently uses German labels.

## Remove

Run `omarchy plugin disable local.omabridge` to disable the widget.
Delete sites in OmaBridge first if you also want to remove saved credentials.
[Full removal instructions](docs/usage.md#removal).

## More

[User guide](docs/usage.md) · [Development](CONTRIBUTING.md) ·
[Changelog](CHANGELOG.md) · [Security review](docs/security-review.md)

Development version: portal compatibility needs testing with your Citrix setup.
The security review lists open findings; this is not an official Marketplace approval.
