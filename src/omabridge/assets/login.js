/* Executed in Qt's isolated ApplicationWorld; no bridge to Python is exposed. */
(function (options) {
    if (location.origin !== options.origin || window !== window.top) return {state: "untrusted"};
    const visible = e => e && !e.disabled && !e.readOnly && e.getClientRects().length > 0
        && getComputedStyle(e).visibility !== "hidden";
    const defaults = {
        username: '#username, #user, #login, input[name="username"], input[name="UserName"], input[autocomplete="username"]',
        password: '#password, #passwd, input[name="password"], input[name="Password"], input[autocomplete="current-password"]',
        otp: '#otp, #totp, #passwd1, #passcode, #verificationCode, #otpCode, input[name="otp" i], input[name="totp" i], input[name="passwd1" i], input[name="passcode" i], input[name="verificationCode" i], input[name="otpCode" i], input[autocomplete="one-time-code"]'
    };
    const inputs = [...document.querySelectorAll('input')].filter(e =>
        visible(e) && ['text', 'password', 'tel', 'number', 'email', 'search'].includes(e.type));
    const otpText = text => /\b(totp|otp|passcode|token|one[ -]?time(?:[ -]?(?:password|code))?|verification[ -]?code|security[ -]?code|authentication[ -]?code|authenticator(?:[ -]?code)?|einmal(?:passwort|kennwort|code)|bestätigungscode|bestatigungscode|sicherheitscode|authentifizierungscode|verifizierungscode)\b/i.test(text);
    const fieldText = e => [
        e.id, e.name, e.placeholder, e.getAttribute('aria-label'),
        ...[...(e.labels || [])].map(label => label.textContent),
        ...['aria-labelledby', 'aria-describedby'].flatMap(attribute =>
            (e.getAttribute(attribute) || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || ''))
    ].filter(Boolean).join(' ');
    const fields = {};
    try {
        // A second-step token may reuse #password. Identify OTP first so the
        // account password can never be inserted into a recognised token field.
        let otp = inputs.filter(e => e.matches(options.selectors.otp || defaults.otp));
        if (!options.selectors.otp) {
            otp = [...new Set([...otp, ...inputs.filter(e =>
                e.autocomplete !== 'new-password' && otpText(fieldText(e)))])];
            if (!otp.length && inputs.length === 1 && inputs[0].autocomplete !== 'new-password') {
                const container = inputs[0].closest('form, .credentialform, [role="form"]');
                // Citrix nFactor uses a generic password input #response and
                // renders the challenge in a sibling div inside credentialform.
                // innerText includes the visible prompt, not hidden previous steps.
                const prompt = container?.innerText || '';
                if ((options.passwordSubmitted || container?.matches('.credentialform')) && otpText(prompt))
                    otp = [inputs[0]];
            }
        }
        if (otp.length > 1) return {state: "ambiguous"};
        if (otp.length) fields.otp = otp[0];
        for (const role of ['username', 'password']) {
            const matches = inputs.filter(e => e !== fields.otp && e.matches(options.selectors[role] || defaults[role]));
            if (matches.length > 1) return {state: "ambiguous"};
            if (matches.length) fields[role] = matches[0];
        }
    } catch (_) { return {state: "selector-error"}; }
    const roles = Object.keys(fields).sort();
    if (!roles.length) return {state: "waiting"};
    if (new Set(Object.values(fields)).size !== roles.length) return {state: "ambiguous"};
    const forms = [...new Set(Object.values(fields).map(e => e.form))];
    if (forms.length !== 1) return {state: "ambiguous"};
    const form = forms[0];
    if (form && new URL(form.action || location.href, location.href).origin !== options.origin)
        return {state: "untrusted-action"};
    if (form && [...form.querySelectorAll('input[type="password"]')].some(e => visible(e) && !Object.values(fields).includes(e)))
        return {state: "ambiguous"}; // Never fill password-change forms.
    const stage = roles.join("+");
    if (!options.fill) return {state: "ready", stage, roles};
    if (options.stage !== stage) return {state: "changed"};
    if (roles.some(role => !options.values[role])) return {state: "missing"};
    let submit;
    try {
        const matches = [...(form || document).querySelectorAll(options.selectors.submit ||
            'button[type="submit"], input[type="submit"], #loginBtn, #Log_On, #login-button, .credentialform .button')]
            .filter(visible);
        if (matches.length === 1) submit = matches[0];
    } catch (_) { return {state: "selector-error"}; }
    if (submit && submit.formAction && new URL(submit.formAction, location.href).origin !== options.origin)
        return {state: "untrusted-action"};
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    for (const role of roles) {
        setter.call(fields[role], options.values[role]);
        fields[role].dispatchEvent(new Event("input", {bubbles: true}));
        fields[role].dispatchEvent(new Event("change", {bubbles: true}));
    }
    // AJAX portals sometimes render the button after the input. Fill the code
    // now and wait for a unique button without spending the submission budget.
    if (options.submit && !submit) return {state: "awaiting-submit", stage};
    if (options.submit) submit.click();
    return {state: options.submit ? "submitted" : "filled", stage};
})
