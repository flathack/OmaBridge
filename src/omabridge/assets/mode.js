(function (options) {
    if (location.origin !== options.origin) return "untrusted";
    if (window.__omabridgeModeSelected === options.mode) return "selected";
    const visible = e => e && !e.disabled && e.getClientRects().length > 0
        && getComputedStyle(e).visibility !== "hidden";
    const browserLabels = ["use web browser", "use light version", "use the light version", "webbrowser verwenden", "light-version verwenden", "lightversion verwenden"];
    const installedLabels = ["already installed", "bereits installiert"];
    const detectLabels = ["detect workspace", "workspace-app erkennen", "detect citrix workspace app", "citrix workspace-app erkennen", "citrix workspace-app ermitteln"];
    let matches;
    try {
        matches = options.selector
            ? [...document.querySelectorAll(options.selector)].filter(visible)
            : [...document.querySelectorAll('a, button, [role="button"]')].filter(visible);
    } catch (_) { return "selector-error"; }
    if (!options.selector) {
        const label = e => e.textContent.trim().toLowerCase();
        if (options.mode === "browser") {
            matches = matches.filter(e => browserLabels.includes(label(e)));
        } else {
            const installed = matches.filter(e => installedLabels.includes(label(e)));
            if (installed.length) matches = installed;
            else {
                if (Date.now() - (window.__omabridgeDetectClickedAt || 0) < 15000) return "waiting";
                matches = matches.filter(e => detectLabels.includes(label(e)));
            }
        }
    }
    if (matches.length !== 1) return "waiting";
    const detecting = options.mode === "workspace" && !options.selector
        && detectLabels.includes(matches[0].textContent.trim().toLowerCase());
    if (detecting) window.__omabridgeDetectClickedAt = Date.now();
    else window.__omabridgeModeSelected = options.mode;
    matches[0].click();
    return detecting ? "detecting" : "selected";
})
