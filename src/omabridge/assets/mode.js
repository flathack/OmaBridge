(function (options) {
    if (location.origin !== options.origin) return "untrusted";
    if (window.__omabridgeModeSelected === options.mode) return "selected";
    const visible = e => e && !e.disabled && e.getClientRects().length > 0
        && getComputedStyle(e).visibility !== "hidden";
    const labels = options.mode === "browser"
        ? ["use web browser", "use light version", "use the light version", "webbrowser verwenden", "light-version verwenden", "lightversion verwenden"]
        : ["already installed", "bereits installiert", "detect workspace", "workspace-app erkennen", "detect citrix workspace app", "citrix workspace-app erkennen"];
    let matches;
    try {
        matches = options.selector
            ? [...document.querySelectorAll(options.selector)].filter(visible)
            : [...document.querySelectorAll('a, button, [role="button"]')].filter(e =>
                visible(e) && labels.includes(e.textContent.trim().toLowerCase()));
    } catch (_) { return "selector-error"; }
    if (matches.length !== 1) return "waiting";
    window.__omabridgeModeSelected = options.mode;
    matches[0].click();
    return "selected";
})
