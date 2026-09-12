# Security and maintainer review

Reviewed on **2026-09-12**, against code commit
[`22b2fd5`](https://github.com/flathack/OmaBridge/tree/22b2fd55876fb9fe593ad07a18a6b3d9ba7aa99b).
The two code findings below were **fixed in 0.3.0** and covered by regression tests.
The original scan results are retained as historical evidence; they do not attest
the newer code. This is a local review, not an official Omarchy approval.

Version 0.3.0 validation: **74 tests passed**, the Omarchy manifest is valid, and
Bandit reports only the same two low-severity Workspace subprocess notices.

## Findings and resolution

| Status | Finding | Resolution / remaining action |
| --- | --- | --- |
| Medium · fixed in 0.3.0 | A password-change field can receive the saved account password. | Visible `autocomplete="new-password"` fields now block the entire sign-in step, including custom selectors. |
| Medium · fixed in 0.3.0 | An ICA download can launch Workspace after switching to browser mode. | Download completion now rechecks the launch mode and session lifetime and deletes rejected tickets. |
| Resolved · MIT license added | No root license file at the original review. | Root `LICENSE` and package metadata now declare MIT. |

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

The 0.3.0 regression tests cover both fixes, including custom password selectors
and late download completion after session disposal. Choose a permanent plugin ID, then request the Marketplace's manual-setup review
for the installer. A maintainer must review the exact submitted commit under the
[submission rules](https://github.com/omacom/omarchy-plugin-marketplace/blob/3942261b4943d19359b84e01be149491b800d3bc/SUBMISSION.md)
and [security policy](https://github.com/omacom/omarchy-plugin-marketplace/blob/3942261b4943d19359b84e01be149491b800d3bc/SECURITY.md).

No live customer portal, real credentials or active VM was used. Dependency auditing
is advisory-database matching, not a binary audit of embedded Chromium/Qt or Citrix
Workspace. The two reproduced findings show why passing automated checks alone does
not establish that the application is ready for release.

## 0.4.0 follow-up — theme and app lock

Local review and Bandit scan on 2026-09-12: no medium/high findings; the same two
low subprocess findings described above remain. All 93 local tests pass, including
lock gating for startup/IPC, rejected changes without the old secret, persisted retry
delays, malformed configuration, browser disposal and live theme replacement.

App lock uses random salts, constant-time digest comparison and scrypt
(`N=2**17`, `r=8`, `p=1`, 128 MiB), following the
[OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Only the hash and retry state are written to a private, atomic configuration file.
It is an optional UI gate: a process with access to the same Linux account can
modify that file or access the keyring independently. Short PINs remain weaker than
long passwords. Native Workspace sessions are outside the lock's scope.

Theme files are size-limited TOML data with validated hex colors, never executed.
Polling the logical path handles atomic theme/symlink replacement without restarting
portal sessions. This follow-up is not an Omarchy maintainer approval.

## 0.4.1 follow-up — unlock from the bar

The bar now asks the running app for its actual lock state. Unlock input travels
through stdin and a user-only local socket, never argv, environment or a saved
unlocked flag. PIN/password values temporarily pass through Quickshell memory;
the field is cleared after submission. Verification and retry limits remain in the
app, and site launch still checks the lock even if a bar entry is stale.

All 97 tests pass locally, including real IPC requests, rejected guesses, re-locking,
background startup and conservative state after the app exits. An isolated Quickshell
run also verified masked-input submission and the resulting demo site list. Bandit
reports the same two low subprocess findings and no medium/high findings. No real
portal or user credentials were used. This remains a local review, not Marketplace approval.

## 0.4.3 follow-up — authenticated local IPC and serialized operations

The final review reproduced two high-priority issues in 0.4.2: a substituted socket
at the predictable shared temporary path could receive the unlock secret, and a
site request during a modal edit could overlap keyring jobs and start a session
after locking. Both are addressed in 0.4.3.

Bar and launcher sockets now live in a checked, user-owned directory with mode
`0700` under the runtime directory. Unsafe directory/socket ownership, permissions
and symlinks are rejected. Both clients and servers verify Linux `SO_PEERCRED`
before processing application data; clients verify it before writing any secret.
There is no connection fallback to the old shared socket paths. Fully quit and
reopen an older running app after upgrading. Same-Linux-user processes remain
outside the app lock's protection boundary.

Site requests wait until modal dialogs and background operations finish. Keyring
operations are serialized, locking checks outstanding jobs, and session callbacks
must still belong to the current unlocked generation before creating a browser.

Validation on 2026-09-12: all 107 local tests passed, including rejection of public
socket endpoints, no secret bytes sent to a simulated wrong-UID peer, real same-user
CLI IPC, deferred site launches during edits/saves, and stale callbacks after lock
and subsequent unlock. Bandit reported no medium/high findings and the two existing
low subprocess findings, with no scan errors. The Omarchy manifest validated and
source/wheel builds passed. No live customer portal or real credentials were used.

The root MIT LICENSE has since been added; the Marketplace's manual review is still outstanding. This
follow-up documents local fixes and validation, not official maintainer approval.
