# Security and maintainer review

Reviewed on **2026-09-12**, against code commit
[`22b2fd5`](https://github.com/flathack/OmaBridge/tree/22b2fd55876fb9fe593ad07a18a6b3d9ba7aa99b).
The accompanying changes only shorten and reorganize documentation; the findings
below remain open. This is a local review, not an official Omarchy approval.

## Open findings

| Priority | Finding | Required change |
| --- | --- | --- |
| Medium | A password-change field can receive the saved account password. | Reject visible `autocomplete="new-password"` fields before assigning any login role. |
| Medium | An ICA download can launch Workspace after switching to browser mode. | Recheck the current launch mode and session lifetime at download completion. |
| Publication blocker | No root license file. | Choose a license and add it before submission. |

### Password-change form detection

[`src/omabridge/assets/login.js:40–55`](https://github.com/flathack/OmaBridge/blob/22b2fd55876fb9fe593ad07a18a6b3d9ba7aa99b/src/omabridge/assets/login.js#L40-L55)
identifies password fields by selectors without excluding `autocomplete="new-password"`.
The later password-change guard only rejects password fields that were *not* already
assigned a role. A new-password field with `id="password"` therefore bypasses it.

Reproduced in Qt WebEngine using the existing local login fixture: add
`autocomplete="new-password"` to its password input and run the login script.
The result is `submitted`, and the field contains the saved account password.
This can submit an unintended password change on the trusted portal. It does not
bypass the cross-origin credential guard.

### Launch mode changes during an ICA download

[`src/omabridge/browser.py:264–275`](https://github.com/flathack/OmaBridge/blob/22b2fd55876fb9fe593ad07a18a6b3d9ba7aa99b/src/omabridge/browser.py#L264-L275)
launches a completed download without rechecking `site.mode`. The check at download
start cannot account for a mode change while the request is in flight.

Reproduced with the existing download fixture: accept the request in Workspace mode,
change the site to browser mode, then signal completion. A mocked `launch_workspace`
is called once. This violates the browser-only preference; the reproduction did not
launch a real client or contact a Citrix server.

## Automated checks

| Check | Result |
| --- | --- |
| Official Marketplace Security Baseline V3 | `review-required`; **0 findings**; capabilities: `installer`, `package-manager`, `remote-build`. |
| Official Marketplace submission validator | **Failed: `license-missing`**. Later compatibility checks are not claimed to have passed. |
| Local `omarchy plugin validate` | Passed for the staged manifest and QML entry point. |
| Bandit 1.9.4, application Python source | 0 high, 0 medium, 2 low findings (`B404`, `B603`). Both concern the intended Workspace subprocess. |
| pip-audit 2.10.1, installed application environment | No known advisories in 10 checked packages; OmaBridge itself is not on PyPI and was reviewed as source instead. |
| Local regression suite | 64 tests passed. Two additional targeted reproductions confirmed the open findings above. |

The Marketplace tools were run directly from
[`omacom/omarchy-plugin-marketplace@3942261`](https://github.com/omacom/omarchy-plugin-marketplace/tree/3942261b4943d19359b84e01be149491b800d3bc),
with the baseline bound to the complete OmaBridge commit SHA above. No submission,
review label or approval attestation was created.

## Manual assessment

- **Credential handling:** Secret Service only, masked password/secret inputs,
  redacted credential representations and no plaintext credential fallback.
  Site configuration is atomically written with private permissions.
- **Browser boundary:** per-site off-the-record profiles, exact-origin checks before
  filling, form-action checks, rejected invalid TLS certificates, no exposed Python
  web bridge, and Chromium sandbox enabled in the application. The trusted portal
  necessarily receives entered values; its own scripts are inside that trust boundary.
- **Native launch:** ICA files come from the saved portal origin, use random names
  inside a private temporary directory, have a size limit and are parsed before launch.
  `Popen` uses an argument array without a shell; this explains the two low Bandit
  findings. `wfica` is resolved through PATH or the documented Citrix installation.
  ICA validation checks format, not the safety of every Citrix client option.
- **Installer and QML:** installation stays under the user's directories, backs up
  bar configuration and documents the separate Python dependency. QML launches
  argument arrays and receives only site IDs, names and modes. These capabilities
  still require human Marketplace review. A standard plugin-only install is insufficient.
- **Dependencies and CI:** GitHub Actions are pinned to commits with read-only repository
  permissions. Runtime dependencies use version ranges, not a reproducible lockfile;
  installed versions can differ. The audit covered PySide6 6.11.2 and SecretStorage 3.5.0.

## Scope and next steps

Fix the two reproduced issues and add regression tests before a release. Choose the
license and a permanent plugin ID, then request the Marketplace's manual-setup review
for the installer. A maintainer must review the exact submitted commit under the
[submission rules](https://github.com/omacom/omarchy-plugin-marketplace/blob/3942261b4943d19359b84e01be149491b800d3bc/SUBMISSION.md)
and [security policy](https://github.com/omacom/omarchy-plugin-marketplace/blob/3942261b4943d19359b84e01be149491b800d3bc/SECURITY.md).

No live customer portal, real credentials or active VM was used. Dependency auditing
is advisory-database matching, not a binary audit of embedded Chromium/Qt or Citrix
Workspace. The two reproduced findings show why passing automated checks alone does
not establish that the application is ready for release.
