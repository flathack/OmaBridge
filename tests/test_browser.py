import json
import time

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript

from omabridge.browser import LOGIN_SCRIPT, MODE_SCRIPT, PortalSession
from omabridge.models import Credentials, Site


def wait_for(app, predicate, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Qt callback timed out")


def js(app, page, code, world=QWebEngineScript.ScriptWorldId.ApplicationWorld):
    results = []
    page.runJavaScript(f"JSON.stringify({code})", world, results.append)
    wait_for(app, lambda: bool(results))
    return json.loads(results[0]) if results[0] else None


@pytest.fixture
def page(app):
    profile = QWebEngineProfile()
    page = QWebEnginePage(profile)
    yield page
    page.deleteLater()
    app.processEvents()
    # Process DeferredDelete before deleting the profile.
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    profile.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def html(app, page, content, url="https://citrix.test/Citrix/StoreWeb/"):
    loaded = []
    callback = loaded.append
    page.loadFinished.connect(callback)
    # setHtml internally uses a data: URL; production deliberately blocks that
    # navigation. Permit only the test loader, then restore the real policy.
    navigation = page.acceptNavigationRequest
    page.acceptNavigationRequest = lambda *args: True
    page.setHtml(content, QUrl(url))
    wait_for(app, lambda: bool(loaded))
    page.loadFinished.disconnect(callback)
    page.acceptNavigationRequest = navigation
    assert loaded[-1]


FORM = '''<form onsubmit="event.preventDefault(); document.body.dataset.submits = String(Number(document.body.dataset.submits || 0) + 1)">
<input id="username"><input id="password" type="password"><input id="otp">
<button type="submit">Anmelden</button></form>'''


def options(**extra):
    return {"origin": "https://citrix.test", "selectors": {}, "fill": True, "submit": True,
            "stage": "otp+password+username", "values": {"username": "demo", "password": "p\"'\\word", "otp": "123456"}, **extra}


def evaluate(app, page, **kwargs):
    return js(app, page, f"{LOGIN_SCRIPT}({json.dumps(options(**kwargs))})")


def test_login_fills_three_fields_and_submits_once(app, page):
    html(app, page, FORM)
    assert evaluate(app, page, fill=False)["roles"] == ["otp", "password", "username"]
    assert evaluate(app, page)["state"] == "submitted"
    values = js(app, page, '[username.value, password.value, otp.value, document.body.dataset.submits]')
    assert values == ["demo", "p\"'\\word", "123456", "1"]


def test_no_credentials_for_redirect_domain(app, page):
    html(app, page, FORM, "https://other.test/")
    assert evaluate(app, page)["state"] == "untrusted"
    assert js(app, page, "password.value") == ""


def test_cross_origin_form_action_rejected(app, page):
    html(app, page, FORM.replace("<form ", '<form action="https://other.test/steal" '))
    assert evaluate(app, page)["state"] == "untrusted-action"
    assert js(app, page, "password.value") == ""


def test_cross_origin_submit_action_rejected(app, page):
    html(app, page, FORM.replace('type="submit"', 'type="submit" formaction="https://other.test/steal"'))
    assert evaluate(app, page)["state"] == "untrusted-action"


def test_password_change_and_ambiguous_inputs_rejected(app, page):
    html(app, page, FORM.replace('<button', '<input type="password" id="new-password"><button'))
    assert evaluate(app, page)["state"] == "ambiguous"


def test_hidden_fields_ignored(app, page):
    html(app, page, FORM.replace('<button', '<input name="username" style="display:none"><button'))
    assert evaluate(app, page)["state"] == "submitted"


def test_missing_otp_never_submits(app, page):
    html(app, page, FORM)
    assert evaluate(app, page, values={"username": "demo", "password": "pw", "otp": ""})["state"] == "missing"
    assert js(app, page, "password.value") == ""


def test_bad_selector_is_actionable(app, page):
    html(app, page, FORM)
    assert evaluate(app, page, selectors={"otp": "input["})["state"] == "selector-error"


def test_custom_selector_for_totp(app, page):
    html(app, page, FORM.replace('id="otp"', 'id="verification"'))
    assert evaluate(app, page, selectors={"otp": "#verification"})["state"] == "submitted"


def test_mode_switch_matches_exact_choice_once(app, page):
    html(app, page, '<button onclick="document.body.dataset.clicks=String(Number(document.body.dataset.clicks||0)+1)">Use web browser</button>')
    code = f'{MODE_SCRIPT}({json.dumps({"origin": "https://citrix.test", "mode": "browser", "selector": ""})})'
    assert js(app, page, code) == "selected"
    assert js(app, page, code) == "selected"
    assert js(app, page, "document.body.dataset.clicks") == "1"


def test_session_retry_budget_survives_reload_and_profiles_isolated(app):
    site = Site("Test", "https://citrix.test/Citrix/StoreWeb/")
    session = PortalSession(site, Credentials("demo", "password", "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"))
    other = PortalSession(Site("Other", "https://other.test"), Credentials())
    session.timer.stop()
    other.timer.stop()
    assert session.profile.isOffTheRecord()
    assert other.profile != session.profile
    # Deterministic code period, avoiding the deliberate near-expiry wait.
    class FixedTotp:
        def remaining(self): return 20
        def code(self): return "123456"
    session.totp = FixedTotp()
    html(app, session.page, FORM)
    session.tick()
    wait_for(app, lambda: not session.busy)
    assert session.used_stages == {"otp+password+username"}
    html(app, session.page, FORM)
    session.tick()
    wait_for(app, lambda: not session.busy)
    assert js(app, session.page, "password.value") == ""
    session.retry()
    session.tick()
    wait_for(app, lambda: not session.busy)
    assert js(app, session.page, "password.value") == "password"
    session.dispose()
    other.dispose()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    session.deleteLater()
    other.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def session(app):
    portal = PortalSession(Site("Test", "https://citrix.test/Citrix/StoreWeb/"),
                           Credentials("demo", "account-password", "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"))
    portal.timer.stop()
    class FixedTotp:
        current = "123456"
        def remaining(self): return 20
        def code(self): return self.current
    portal.totp = FixedTotp()
    yield portal
    portal.dispose()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    portal.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def tick(app, session):
    session.tick()
    wait_for(app, lambda: not session.busy)


CHALLENGE = '''<form class="form insertPoint credentialform" action="/nf/auth/doDialogue.do" method="POST"
onsubmit="event.preventDefault(); document.body.dataset.submits = String(Number(document.body.dataset.submits || 0) + 1)">
<div class="field CredentialTypeinformation"><div>Enter Your Microsoft verification code</div></div>
<div class="field CredentialTypepassword"><div class="left"><label for="response">Kennwort</label></div>
<div class="right"><input id="response" name="response" type="password" autocomplete="off" spellcheck="false"></div></div>
<div class="field buttonsrow"><button type="submit">Senden</button></div>
</form>'''


@pytest.mark.parametrize("field", ['id="response" name="response"', 'id="password" name="password"'])
def test_delayed_citrix_challenge_after_password(app, session, field):
    html(app, session.page, FORM.replace('<input id="otp">', ''))
    session.deadline = time.monotonic() + 5
    tick(app, session)
    assert session.used_stages == {"password+username"}
    assert session.deadline > time.monotonic() + 80
    assert js(app, session.page, "password.value") == "account-password"
    # The original form disappears; the challenge arrives on a later DOM update.
    js(app, session.page, "document.body.replaceChildren()")
    tick(app, session)
    assert session.used_stages == {"password+username"}
    challenge = CHALLENGE.replace('id="response" name="response"', field)
    js(app, session.page, f"document.body.innerHTML = {json.dumps(challenge)}")
    session.totp.current = "654321"
    tick(app, session)
    assert session.used_stages == {"password+username", "otp"}
    assert js(app, session.page, "document.querySelector('input').value") == "654321"
    assert js(app, session.page, "document.body.dataset.submits") == "2"
    tick(app, session)
    assert js(app, session.page, "document.body.dataset.submits") == "2"


def test_citrix_challenge_after_full_navigation(app, session):
    html(app, session.page, FORM.replace('<input id="otp">', ''))
    tick(app, session)
    html(app, session.page, CHALLENGE, "https://citrix.test/logon/LogonPoint/tmindex.html")
    tick(app, session)
    assert js(app, session.page, "document.querySelector('#response').value") == "123456"
    assert session.used_stages == {"password+username", "otp"}


def test_direct_citrix_challenge_uses_prompt_not_password_type(app, page):
    html(app, page, CHALLENGE)
    probe = evaluate(app, page, fill=False)
    assert probe["roles"] == ["otp"]
    assert evaluate(app, page, stage="otp")["state"] == "submitted"
    assert js(app, page, "document.querySelector('#response').value") == "123456"


def test_portal_address_strips_tickets_and_credentials(app, session):
    addresses = []
    session.address.connect(addresses.append)
    session.url_changed(QUrl("https://user:password@citrix.test/portal?ticket=secret#token"))
    assert addresses == ["https://citrix.test/portal"]


def test_delayed_submit_button_does_not_consume_attempt(app, session):
    html(app, session.page, CHALLENGE.replace('<button type="submit">Senden</button>', ''))
    tick(app, session)
    assert js(app, session.page, "document.querySelector('#response').value") == "123456"
    assert not session.used_stages
    js(app, session.page, "document.querySelector('.buttonsrow').innerHTML = '<button type=submit>Senden</button>'")
    session.totp.current = "654321"
    tick(app, session)
    assert js(app, session.page, "document.querySelector('#response').value") == "654321"
    assert js(app, session.page, "document.body.dataset.submits") == "1"
    assert session.used_stages == {"otp"}


def test_second_step_does_not_guess_generic_response_password(app, page):
    html(app, page, CHALLENGE.replace("Enter Your Microsoft verification code", "Geben Sie Ihr Kennwort ein"))
    assert evaluate(app, page, fill=False, passwordSubmitted=True)["state"] == "waiting"
    assert js(app, page, "document.querySelector('#response').value") == ""


def test_hidden_token_prompt_and_new_password_never_become_otp(app, page):
    html(app, page, CHALLENGE.replace('class="field CredentialTypeinformation"',
                                     'class="field CredentialTypeinformation" style="display:none"'))
    assert evaluate(app, page, fill=False, passwordSubmitted=True)["state"] == "waiting"
    html(app, page, CHALLENGE.replace('autocomplete="off"', 'autocomplete="new-password"'))
    assert evaluate(app, page, fill=False, passwordSubmitted=True)["state"] == "waiting"


def test_foreign_citrix_challenge_never_receives_code(app, session):
    html(app, session.page, FORM.replace('<input id="otp">', ''))
    tick(app, session)
    html(app, session.page, CHALLENGE, "https://other.test/logon/LogonPoint/tmindex.html")
    tick(app, session)
    assert js(app, session.page, "document.querySelector('#response').value") == ""
