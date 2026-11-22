# Adatvédelem / Privacy

## Magyar

**Röviden: minden a saját gépeden és a saját hálózatodon marad.**

- A SubBridge a képernyőképeket **csak a memóriában** dolgozza fel a gépeden. Képet, videót vagy hangot soha nem
  küld el, és nem ment el (kivéve, ha te kifejezetten hibakereső felvételt kérsz).
- **Offline fordítással** (alapbeállítás) semmilyen adat nem hagyja el a gépet. A nyelvi modell egyszer töltődik le a
  modelltárból.
- **Online fordító** (DeepL, Google Cloud, LibreTranslate) választásakor **kizárólag a felismert felirat szövege**
  megy el a választott szolgáltatásnak, a saját API-kulcsoddal, az ő adatkezelési feltételeik szerint. A program
  nem használja a Google nem hivatalos, ingyenes végpontját.
- A telefon a **helyi hálózaton**, közvetlenül a gépedhez kapcsolódik (PIN vagy QR-kód). Nincs felhő, nincs fiók,
  nincs regisztráció.
- **Hírek és szótárfrissítések:** a program néhány óránként letölti a rolandhrvth.hu/subbridge/feed nyilvános
  fájljait (hírek, szleng- és szerepnév-csomagok, verziószám). Ehhez semmilyen adatot nem küld magadról vagy a
  játékról; a beállításokban kikapcsolható.
- Nincs analitika, telemetria, reklám vagy nyomkövetés – sem az asztali appban, sem a telefonos oldalon, sem az
  Android-appban.
- Helyben tárolt adatok: beállítások (az API-kulcsok csak a te felhasználód által olvasható fájlban), a lefordított
  mondatok gyorsítótára, a letöltött nyelvi modellek. Ezeket bármikor törölheted (Beállítások › Fordítás ›
  Gyorsítótár, illetve a program adatmappája).
- Az Android-app csak a kamerát kéri (QR-kód beolvasásához, a kép nem kerül mentésre) és a helyi hálózat elérését.

## English

**In short: everything stays on your computer and your own network.**

- SubBridge processes screen images **in memory only** on your computer. It never sends or stores pictures, video
  or audio (unless you explicitly record a debug capture).
- With **offline translation** (the default) no data leaves your computer. The language model is downloaded once.
- With an **online translator** (DeepL, Google Cloud, LibreTranslate) **only the recognised subtitle text** is sent to
  the service you chose, with your own API key and under its terms. SubBridge never uses Google's unofficial free
  endpoint.
- Your phone connects **directly to your computer on the local network** (PIN or QR code). No cloud, no account,
  no sign-up.
- **News and dictionary updates:** every few hours the app downloads the public files at rolandhrvth.hu/subbridge/feed
  (news, slang and speaker-role packs, version number). Nothing about you or the game is sent; it can be turned off in
  the settings.
- No analytics, telemetry, ads or tracking – in the desktop app, the phone page or the Android app.
- Stored locally: settings (API keys in a file readable only by your user), a cache of translated sentences, the
  downloaded language models. You can delete them any time (Settings › Translation › Cache, or the app's data folder).
- The Android app only asks for the camera (to scan the QR code; nothing is saved) and local network access.
