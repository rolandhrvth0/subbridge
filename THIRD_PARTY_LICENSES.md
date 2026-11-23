# Third-party software / Harmadik féltől származó szoftverek

SubBridge itself is MIT licensed (see `LICENSE`). The packaged desktop builds and the Android app include
or use the components below. Each remains under its own licence; the full texts are available at the
linked projects. Components under the LGPL are used as separate, replaceable dynamic libraries.

## Desktop application

| Component | Use | Licence |
|---|---|---|
| [Qt 6 / PySide6](https://www.qt.io/qt-for-python) | user interface, video capture (Qt Multimedia) | LGPL-3.0 |
| [FFmpeg](https://ffmpeg.org) (bundled with Qt Multimedia) | video decoding | LGPL-2.1+ |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) + `eng.traineddata` ([tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast)) | text recognition | Apache-2.0 |
| [OpenCV](https://opencv.org) (`opencv-python-headless`) | box-less subtitle detection, frame generation (optical flow) | Apache-2.0 |
| [PyWinRT](https://github.com/pywinrt/pywinrt) (`winrt-*`, Windows only) | Windows built-in text recognition | MIT |
| [tesserocr](https://github.com/sirfz/tesserocr) | Tesseract binding | MIT |
| [Leptonica](http://www.leptonica.org) | image library used by Tesseract | BSD-2-Clause |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | offline translation runtime | MIT |
| [SentencePiece](https://github.com/google/sentencepiece) | tokenizer | Apache-2.0 |
| [sacremoses](https://github.com/hplt-project/sacremoses) | tokenizer | MIT |
| [subword-nmt](https://github.com/rsennrich/subword-nmt) | tokenizer | MIT |
| [Argos Translate](https://github.com/argosopentech/argos-translate) language packages (downloaded on demand) | offline translation models | model-specific, e.g. OPUS-MT derived models: CC-BY-4.0 |
| [aiohttp](https://github.com/aio-libs/aiohttp) | local web server | Apache-2.0 |
| [NumPy](https://numpy.org) | image processing | BSD-3-Clause |
| [Pillow](https://python-pillow.org) | image processing | MIT-CMU (HPND) |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | pairing QR code | BSD |
| [cryptography](https://github.com/pyca/cryptography) | optional HTTPS certificate | Apache-2.0 OR BSD-3-Clause |
| [python-zeroconf](https://github.com/python-zeroconf/python-zeroconf) | announcing the PC to the Android app | LGPL-2.1+ |
| [python-xlib](https://github.com/python-xlib/python-xlib) (Linux) | window capture | LGPL-2.1+ |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (optional) | alternative OCR engine | Apache-2.0 |
| [Inter](https://rsms.me/inter/) font | user interface | SIL OFL 1.1 (`subbridge/assets/fonts/OFL.txt`) |
| [Figtree](https://github.com/erikdkennedy/figtree) font | in-game overlay subtitles | SIL OFL 1.1 |
| [SCOWL](http://wordlist.aspell.net) word list | filtering HUD text | SCOWL licence (`subbridge/assets/wordlist/COPYRIGHT-SCOWL.txt`) |
| Python | runtime (PyInstaller builds) | PSF-2.0 |

Online translators (DeepL, Google Cloud Translation, LibreTranslate) are separate services used only with
your own key or server and under their own terms.

## Android application

| Component | Licence |
|---|---|
| [AndroidX / Jetpack Compose](https://developer.android.com/jetpack/androidx) | Apache-2.0 |
| [Kotlin standard library and coroutines](https://kotlinlang.org) | Apache-2.0 |
| [OkHttp](https://square.github.io/okhttp/) | Apache-2.0 |
| [ZXing Android Embedded](https://github.com/journeyapps/zxing-android-embedded) / [ZXing](https://github.com/zxing/zxing) | Apache-2.0 |

## Not included

The Remote Play client (for example chiaki-ng, AGPL-3.0) is **not** part of SubBridge and is not
distributed with it; install it separately if you use it.
