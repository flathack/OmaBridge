import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui as Ui
import qs.Commons

Ui.BarWidget {
    id: root
    moduleName: "local.omabridge"
    implicitWidth: vertical ? barSize : title.implicitWidth + Style.space(20)
    implicitHeight: barSize

    property bool popupOpen: false
    property var sites: []
    property string loadError: ""
    property string unlockError: ""
    property bool locked: false
    property bool stateLoaded: false
    property string language: "en"
    readonly property string launcher: Quickshell.env("HOME") + "/.local/bin/omabridge"
    function t(english, german) { return root.language === "de" ? german : english }
    Component.onCompleted: refreshSites()

    onPopupOpenChanged: {
        passwordInput.clear()
        unlockError = ""
        sites = []
        if (popupOpen) refreshSites()
    }
    function close() { popupOpen = false }
    function applyState(parsed) {
        if (!Array.isArray(parsed.sites) || typeof parsed.locked !== "boolean") throw new Error("Invalid state")
        stateLoaded = true
        language = parsed.language === "de" ? "de" : "en"
        locked = parsed.locked
        const nextSites = locked ? [] : parsed.sites
        if (JSON.stringify(sites) !== JSON.stringify(nextSites)) sites = nextSites
        loadError = ""
        if (!locked) unlockError = ""
    }
    function unlock() {
        if (unlocker.running || passwordInput.text.length === 0) return
        unlockError = ""
        unlocker.running = true
    }
    Timer {
        interval: 1000
        repeat: true
        running: root.popupOpen && !unlocker.running
        onTriggered: root.refreshSites()
    }
    function launch(siteId) {
        const args = [launcher]
        if (siteId) args.push("--site", siteId)
        Quickshell.execDetached(args)
        close()
    }
    function refreshSites() {
        if (!reader.running && !unlocker.running) {
            reader.running = true
        }
    }

    Text {
        id: title
        anchors.centerIn: parent
        text: root.vertical ? "󰢹" : "󰢹  Citrix"
        textFormat: Text.PlainText
        color: root.bar ? root.bar.barForeground : "white"
        font.family: root.bar ? root.bar.fontFamily : "monospace"
        font.pixelSize: Style.font.body
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: function(mouse) {
            if (mouse.button === Qt.RightButton) root.launch("")
            else {
                root.popupOpen = !root.popupOpen
                if (root.popupOpen) root.refreshSites()
            }
        }
        onEntered: {
            root.refreshSites()
            if (root.bar) root.bar.showTooltip(root, root.t("OmaBridge · Citrix sites\nRight-click: Manage sites", "OmaBridge · Citrix-Sites\nRechtsklick: Site-Verwaltung"))
        }
        onExited: if (root.bar) root.bar.hideTooltip(root)
    }
    Process {
        id: reader
        command: [root.launcher, "--bar-state"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const parsed = JSON.parse(text)
                    root.applyState(parsed)
                } catch (_) {
                    root.sites = []
                    root.loadError = root.t("Could not load sites. Open OmaBridge and check the configuration.", "Sites konnten nicht geladen werden. OmaBridge öffnen und Konfiguration prüfen.")
                }
            }
        }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0) {
                root.sites = []
                root.loadError = root.t("OmaBridge is unavailable. Open the app to check its configuration.", "OmaBridge nicht verfügbar. Öffne die App, um ihre Konfiguration zu prüfen.")
            }
        }
    }
    Process {
        id: unlocker
        command: [root.launcher, "--unlock-stdin"]
        stdinEnabled: true
        onStarted: {
            write(JSON.stringify({secret: passwordInput.text}) + "\n")
            passwordInput.clear()
        }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const parsed = JSON.parse(text)
                    root.applyState(parsed)
                    root.unlockError = parsed.error || ""
                } catch (_) {
                    root.unlockError = root.t("Unlock failed. Reopen OmaBridge and try again.", "Entsperren fehlgeschlagen. OmaBridge neu öffnen und erneut versuchen.")
                }
            }
        }
        onExited: function(exitCode, exitStatus) {
            passwordInput.clear()
            if (exitCode !== 0 && root.unlockError === "")
                root.unlockError = root.t("Unlock failed. Reopen OmaBridge and try again.", "Entsperren fehlgeschlagen. OmaBridge neu öffnen und erneut versuchen.")
        }
    }
    Ui.PopupCard {
        id: popup
        anchorItem: root
        bar: root.bar
        owner: root
        open: root.popupOpen
        contentWidth: popup.fittedContentWidth(Style.space(320))
        contentHeight: popup.fittedContentHeight(column.implicitHeight)

        Column {
            id: column
            anchors.fill: parent
            spacing: Style.space(12)
            Text {
                text: root.t("Citrix sites", "Citrix-Sites")
                color: root.bar ? root.bar.foreground : "white"
                font.family: root.bar ? root.bar.fontFamily : "monospace"
                font.pixelSize: Style.font.subtitle
                font.bold: true
            }
            Text {
                id: stateHint
                width: parent.width
                visible: root.loadError !== "" || root.sites.length === 0
                text: root.loadError || (!root.stateLoaded ? root.t("Loading sites …", "Sites laden …") : root.locked ? root.t("Unlock OmaBridge to view your sites.", "Entsperre OmaBridge, um deine Sites zu sehen.") : root.t("No saved sites yet. Add your StoreFront connection in OmaBridge.", "Noch keine Site gespeichert. Füge deinen StoreFront-Zugang in OmaBridge hinzu."))
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.bar ? root.bar.foreground : "white"
                font.family: root.bar ? root.bar.fontFamily : "monospace"
                font.pixelSize: Style.font.body
            }
            Ui.TextField {
                id: passwordInput
                width: parent.width
                visible: root.locked
                enabled: !unlocker.running
                password: true
                placeholderText: root.t("PIN or password", "PIN oder Passwort")
                Accessible.name: placeholderText
                foreground: root.bar ? root.bar.foreground : "white"
                onAccepted: root.unlock()
            }
            Ui.Button {
                visible: root.locked
                enabled: !unlocker.running && passwordInput.text.length > 0
                text: unlocker.running ? root.t("Unlocking …", "Entsperren …") : root.t("Unlock", "Entsperren")
                foreground: root.bar ? root.bar.foreground : "white"
                onClicked: root.unlock()
            }
            Text {
                width: parent.width
                visible: root.unlockError !== ""
                text: root.unlockError
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.bar ? root.bar.foreground : "white"
                font.family: root.bar ? root.bar.fontFamily : "monospace"
                font.pixelSize: Style.font.body
            }
            Flickable {
                width: parent.width
                height: Math.min(siteRows.implicitHeight, Style.space(360))
                contentHeight: siteRows.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: siteRows
                    width: parent.width
                    spacing: Style.space(6)
                    Repeater {
                        model: root.sites
                        Rectangle {
                            id: siteRow
                            required property var modelData
                            width: siteRows.width
                            height: Style.space(62)
                            radius: Style.space(4)
                            readonly property color highlight: root.bar ? root.bar.foreground : "white"
                            color: siteMouse.containsMouse ? Qt.rgba(highlight.r, highlight.g, highlight.b, 0.12) : "transparent"
                            activeFocusOnTab: true
                            Accessible.role: Accessible.Button
                            Accessible.name: modelData.name
                            Keys.onReturnPressed: root.launch(modelData.id)
                            Keys.onSpacePressed: root.launch(modelData.id)
                            border.width: activeFocus ? 1 : 0
                            border.color: root.bar ? root.bar.foreground : "white"
                            Column {
                                anchors.fill: parent
                                anchors.margins: Style.space(8)
                                spacing: Style.space(4)
                                Text {
                                    width: parent.width
                                    text: siteRow.modelData.name
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    color: root.bar ? root.bar.foreground : "white"
                                    font.family: root.bar ? root.bar.fontFamily : "monospace"
                                    font.pixelSize: Style.font.body
                                }
                                Text {
                                    text: siteRow.modelData.mode === "browser" ? "Browser · HTML5" : "Citrix Workspace"
                                    color: root.bar ? root.bar.foreground : "white"
                                    opacity: 0.7
                                    font.family: root.bar ? root.bar.fontFamily : "monospace"
                                    font.pixelSize: Style.font.caption
                                }
                            }
                            MouseArea {
                                id: siteMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.launch(siteRow.modelData.id)
                            }
                        }
                    }
                }
            }
            Ui.Button {
                text: root.locked ? root.t("Open OmaBridge", "OmaBridge öffnen") : root.t("Manage sites", "Sites verwalten")
                foreground: root.bar ? root.bar.foreground : "white"
                onClicked: root.launch("")
            }
        }
    }
}
