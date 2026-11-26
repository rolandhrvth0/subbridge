// Game View on the graphics card (Qt Quick: Vulkan on Linux, Direct3D 11 on Windows), so the GPU
// makers' frame generation (lsfg-vk, AMD Fluid Motion Frames, NVIDIA Smooth Motion) can work on it.
import QtQuick
import QtMultimedia

Rectangle {
    id: root
    color: "black"
    focus: true
    property real srcW: 1920
    property real srcH: 1080
    property var boxes: []          // [{x0, y0, x1, y1, px, html, bg, maxw}] in picture pixels
    property var phone: null        // {header, items: [{text, name, mine, kind}], x0, y0, x1, y1} or null
    property string hint: ""
    property string badge: ""
    property real scaleText: 1.0
    readonly property real padX: 22
    readonly property real padY: 6

    // Upscaler: when the window is bigger than the card's picture (1440p card on a 4K TV) the picture is scaled
    // on the GPU with Catmull-Rom bicubic + contrast-adaptive sharpening instead of plain bilinear. Frame
    // generation (lsfg-vk / AFMF / Smooth Motion / Lossless Scaling) works on the result.
    property bool upscale: true
    property real sharpness: 0.45
    readonly property real fitK: Math.min(width / Math.max(1, srcW), height / Math.max(1, srcH))
    readonly property rect fit: Qt.rect((width - srcW * fitK) / 2, (height - srcH * fitK) / 2, srcW * fitK, srcH * fitK)
    readonly property bool scaling: upscale && fitK > 1.05

    VideoOutput {
        id: video
        objectName: "video"
        x: root.fit.x; y: root.fit.y; width: root.fit.width; height: root.fit.height
        fillMode: VideoOutput.Stretch
    }
    ShaderEffectSource {
        id: srcTex
        sourceItem: video
        hideSource: root.scaling
        live: root.scaling
        smooth: true
        textureSize: Qt.size(root.srcW, root.srcH)
        visible: false
    }
    ShaderEffect {
        id: up
        x: root.fit.x; y: root.fit.y; width: root.fit.width; height: root.fit.height
        visible: root.scaling
        property variant source: srcTex
        property size texSize: Qt.size(root.srcW, root.srcH)
        fragmentShader: "shaders/upscale.frag.qsb"
        layer.enabled: root.scaling
        layer.effect: ShaderEffect {
            property size outSize: Qt.size(up.width, up.height)
            property real sharpness: root.sharpness
            fragmentShader: "shaders/sharpen.frag.qsb"
        }
    }

    // picture area inside the window (letterboxed): subtitle boxes are placed in picture pixels * k
    Item {
        id: pic
        x: root.fit.x
        y: root.fit.y
        width: root.fit.width
        height: root.fit.height
        readonly property real k: width / Math.max(1, root.srcW)

        Repeater {
            model: root.boxes
            delegate: Rectangle {
                id: box
                required property var modelData
                readonly property real bx0: modelData.x0 * pic.k
                readonly property real bx1: modelData.x1 * pic.k
                readonly property real by1: modelData.y1 * pic.k
                readonly property real minH: (modelData.y1 - modelData.y0) * pic.k
                color: modelData.bg
                width: Math.max(bx1 - bx0, label.width + 2 * root.padX * pic.k)
                height: Math.max(minH, label.height + 2 * root.padY * pic.k)
                x: (bx0 + bx1) / 2 - width / 2
                y: by1 - height
                z: 10
                Text {
                    id: label
                    anchors.centerIn: parent
                    textFormat: Text.RichText
                    text: box.modelData.html
                    color: "white"
                    font.family: "Inter Variable"
                    font.pixelSize: Math.max(11, box.modelData.px * pic.k * root.scaleText)
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    lineHeight: 1.12
                    width: Math.min(implicitWidth, box.modelData.maxw * pic.k - 2 * root.padX * pic.k)
                }
            }
        }

        // translated in-game phone: a chat card next to the phone in the picture
        Rectangle {
            id: card
            visible: !!root.phone
            z: 20
            radius: 14
            color: "#fafafc"
            readonly property real px: Math.max(13, Math.min(26, pic.height / 34))
            width: Math.min(pic.width * 0.34, 440)
            height: col.implicitHeight + 2 * px
            x: root.phone ? Math.min(pic.width - width - 12, root.phone.x1 * pic.k + 16) : 0
            y: root.phone ? Math.max(12, Math.min(pic.height - height - 12, root.phone.y0 * pic.k)) : 0
            Column {
                id: col
                x: card.px; y: card.px
                width: card.width - 2 * card.px
                spacing: card.px / 2
                Text { text: qsTr("PHONE"); color: "#6b7280"; font.pixelSize: card.px * 0.72; font.bold: true; font.letterSpacing: 1 }
                Text { text: root.phone ? (root.phone.header || "") : ""; color: "#15171c"; font.pixelSize: card.px * 1.12; font.bold: true; width: parent.width; wrapMode: Text.WordWrap }
                Repeater {
                    model: root.phone ? root.phone.items : []
                    delegate: Item {
                        required property var modelData
                        width: col.width
                        height: bubble.height
                        Rectangle {
                            id: bubble
                            readonly property bool mine: modelData.mine
                            readonly property bool reply: modelData.kind === "reply"
                            radius: card.px
                            color: reply ? "transparent" : (mine ? "#2f6df6" : "#eceef2")
                            border.width: reply ? 2 : 0
                            border.color: "#2f6df6"
                            width: Math.min(t.implicitWidth + card.px * 1.6, col.width * 0.86)
                            height: t.height + card.px
                            anchors.right: mine ? parent.right : undefined
                            Text {
                                id: t
                                x: card.px * 0.8; y: card.px / 2
                                width: Math.min(implicitWidth, col.width * 0.86 - card.px * 1.6)
                                wrapMode: Text.WordWrap
                                text: (modelData.name ? modelData.name + ": " : "") + modelData.text
                                color: bubble.reply ? "#2f6df6" : (bubble.mine ? "white" : "#15171c")
                                font.pixelSize: card.px
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        visible: root.hint !== ""
        z: 30
        anchors.horizontalCenter: parent.horizontalCenter
        y: 24
        radius: 8
        color: "#b0000000"
        width: hintText.implicitWidth + 28
        height: hintText.implicitHeight + 16
        Text { id: hintText; anchors.centerIn: parent; text: root.hint; color: "#dddddd"; font.pixelSize: 14 }
    }
    Rectangle {
        visible: root.badge !== ""
        z: 30
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16
        radius: 6
        color: "#96000000"
        width: badgeText.implicitWidth + 20
        height: badgeText.implicitHeight + 8
        Text { id: badgeText; anchors.centerIn: parent; text: root.badge; color: "#cfd6e4"; font.pixelSize: 12 }
    }
}
