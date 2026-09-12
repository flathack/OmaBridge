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
    property string language: "en"
    readonly property string launcher: Quickshell.env("HOME") + "/.local/bin/omabridge"
    function t(english, german) { return root.language === "de" ? german : english }
    Component.onCompleted: refreshSites()

    function close() { popupOpen = false }
    function launch(siteId) {
        const args = [launcher]
        if (siteId) args.push("--site", siteId)
        Quickshell.execDetached(args)
        close()
    }
    function refreshSites() {
        if (!reader.running) {
            loadError = ""
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
                    if (!Array.isArray(parsed.sites)) throw new Error("Invalid sites")
                    root.language = parsed.language === "de" ? "de" : "en"
                    root.sites = parsed.sites
                } catch (_) {
                    root.sites = []
                    root.loadError = root.t("Could not load sites. Open OmaBridge and check the configuration.", "Sites konnten nicht geladen werden. OmaBridge öffnen und Konfiguration prüfen.")
                }
            }
        }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0) root.loadError = root.t("OmaBridge is unavailable. Run scripts/install.sh first.", "OmaBridge nicht verfügbar. Zuerst scripts/install.sh ausführen.")
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
                width: parent.width
                visible: root.loadError !== "" || root.sites.length === 0
                text: root.loadError || (reader.running ? root.t("Loading sites …", "Sites laden …") : root.t("No saved sites yet. Add your StoreFront connection in OmaBridge.", "Noch keine Site gespeichert. Füge deinen StoreFront-Zugang in OmaBridge hinzu."))
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
                            color: siteMouse.containsMouse ? Qt.rgba(0.5, 0.6, 0.8, 0.18) : "transparent"
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
                text: root.t("Manage sites", "Sites verwalten")
                foreground: root.bar ? root.bar.foreground : "white"
                onClicked: root.launch("")
            }
        }
    }
}
