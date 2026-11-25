"""Help texts (HTML). The app is tuned for GTA VI (named descriptively only: no logos, artwork or official look)."""

HELP = {
"hu": [
("start", "Első lépések", """
<p>A {app} a képernyőn megjelenő feliratot kiolvassa, lefordítja, és élőben elküldi a telefonodra.</p>
<ol>
<li><b>Képforrás:</b> válaszd ki a Remote Play ablakot (vagy a teljes képernyőt).</li>
<li><b>Feliratterület:</b> a játékban várd meg, hogy látsszon egy felirat, kattints a <i>Feliratterület kijelölése</i> gombra, és húzz egy téglalapot köré. Hagyj helyet a kétsoros feliratnak is.</li>
<li><b>Telefon:</b> olvasd be a QR-kódot a telefon kamerájával. A telefonnak ugyanazon a Wi-Fi-hálózaton kell lennie, mint a számítógépnek.</li>
<li>Nyomd meg az <b>Indítás</b> gombot.</li>
</ol>
<p><b>Ajánlott beállítás a játékban</b> (Beállítások › UI › Subtitles &amp; Captions, vagy hasonló menü):</p><ul><li><b>Subtitles (Felirat):</b> On – a legteljesebb fokozat (3/3): így a járókelők és NPC-k beszéde is feliratot kap, és azt is fordítja</li><li><b>Closed Captions:</b> Off</li><li><b>Size (Méret):</b> Medium</li><li><b>Speaker Names (Beszélőnevek):</b> On</li><li><b>Background (Háttér):</b> Solid – egyszínű doboz, ezt takarja le pontosan</li></ul>
"""),
("gta", "GTA VI-hoz hangolva", """
<p>A {app} kifejezetten a <b>GTA VI</b>-hoz készült: a felismerés a játék feliratdobozaihoz és betűtípusához van hangolva, a fordító pedig ismeri a játék szereplőit, helyszíneit és szlengjét.</p>
<ul>
<li><b>Fordítási memória:</b> a játék több ezer párbeszédsorát előre, egyenként fordítottuk le. Ha egy ilyen sor jelenik meg, azonnal és internet nélkül a kész magyar mondatot látod – egységes nevekkel és tegezéssel.</li>
<li><b>Szleng és nevek:</b> a frissítések között is bővül (a program magától letölti), nem kell hozzá új verzió.</li>
<li><b>Ami nincs a memóriában</b> (járókelők, rádió, ritka sorok), azt a választott fordító fordítja élőben.</li>
</ul>
<p style="color:#8a8f9a"><small>A SubBridge független, nem hivatalos program; nem áll kapcsolatban a Rockstar Games-szel és a Take-Two Interactive-val, és nem is támogatják. A „Grand Theft Auto” és a „GTA” a Take-Two Interactive védjegyei, itt csak a játék megnevezésére szolgálnak.</small></p>
"""),
("v1", "Pontos fordító, Feliratnapló, Tanuló mód", """
<p><b>Pontos fordító:</b> a Fordító kártyán a <i>Pontos fordító letöltése</i> gomb egy sokkal jobb offline modellt tölt le (kb. 200 MB, egyszer). Utána magától ezt használja.</p>
<p><b>Feliratnapló:</b> az Utolsó felirat kártyán. Itt visszaolvashatsz mindent, kereshetsz, elmentheted fájlba. Dupla kattintással kijavíthatod a fordítást – onnantól az a mondat mindig így jelenik meg.</p>
<p><b>Tanuló mód:</b> a magyar felirat alatt kicsiben az angol eredeti is látszik a játék képén.</p>
<p><b>Hibajelentés:</b> felül a zászló gomb – egy kattintással elküldi a fejlesztőnek, ami a javításhoz kell.</p>
"""),
("chiaki", "PS5 Remote Play beállítása (chiaki-ng)", """
<p><b>Windowson:</b> a chiaki-ng-t F11-es teljes képernyőn használd. Ultrawide monitoron hagyd a képet 16:9-ben (fekete sáv két oldalt), ne nyújtsd ki (Stretch/Zoom).</p>
<p>A {app} nem tartalmaz Remote Play klienst – a képet egy külön program adja. PS5-höz a nyílt forráskódú <b>chiaki-ng</b> ajánlott (külön telepítendő, AGPL licenc).</p>
<ol>
<li>Telepítés: Linuxon Flatpakkal (<code>flatpak install flathub io.github.streetpea.Chiaki4deck</code>), Windowson a projekt GitHub-oldaláról: <code>github.com/streetpea/chiaki-ng</code>.</li>
<li>A PS5-ön: <i>Beállítások › Rendszer › Távoli lejátszás</i> – kapcsold be. Hagyd a konzolt pihenő módban is elérhetőnek (<i>Energiatakarékosság › Pihenő módban elérhető funkciók › Internetkapcsolat</i>).</li>
<li>A chiaki-ng-ben jelentkezz be a PSN-fiókoddal, válaszd ki a konzolt, és párosítsd a PS5 által mutatott kóddal.</li>
<li>Felbontás: 1080p elég. Nagyobb felbontás jobb felismerést ad, de több hálózati sávszélesség kell.</li>
<li>A chiaki-ng ablaka maradhat más ablakok mögött, de <b>ne kicsinyítsd le</b>.</li>
</ol>
"""),
("capture_card", "Capture card (HDMI-rögzítő) használata", """
<p>Remote Play helyett a konzol képét egy <b>capture carddal</b> (HDMI→USB rögzítő, például Elgato vagy olcsó UVC-kártya) is beolvashatod. Bármilyen konzollal működik.</p>
<ol>
<li>Kösd be: konzol HDMI-kimenet → kártya HDMI-bemenet, kártya USB → számítógép. Ha a kártyán van <b>HDMI-kimenet (passthrough)</b>, onnan menjen a tévére vagy a monitorra: így késés nélkül játszol, a {app} pedig a háttérben olvas.</li>
<li><b>PS5-ön kapcsold ki a HDCP-t</b>, különben a kártya fekete képet kap: <i>Beállítások › Rendszer › HDMI › HDCP engedélyezése</i> – ki.</li>
<li>A {app}-ban a Képforrásnál válaszd a <i>Capture card / videóeszköz</i> sort, és jelöld ki a feliratterületet.</li>
<li>Ha nincs passthrough, nyisd meg a <b>Játéknézetet</b>: teljes képernyőn mutatja a játékot hanggal, és a magyar felirat közvetlenül az angol helyén jelenik meg.</li>
</ol>
<p><b>Passthrough nélküli kártya (például kis 4K HDMI→USB adapter):</b></p>
<ul>
<li>Dugd <b>USB 3-as</b> (kék vagy USB-C) portba – USB 2-n csak 720p megy, a program szól, ha ez a helyzet.</li>
<li>PS5: <i>Képernyő és videó › Videókimenet › Felbontás</i> = <b>1440p</b> (ha nincs ilyen: 1080p), <i>HDR</i> = <b>ki</b>, <i>Rendszer › HDMI › HDCP</i> = <b>ki</b>. Az ilyen adapterek a 4K 60 Hz-es és a HDR-jelet gyakran nem fogadják (fekete kép).</li>
<li>Játék a gépen: nyisd meg a <b>Játéknézetet</b> (dupla kattintás = teljes képernyő), a hang is ott szól.</li>
<li>Játék a tévén: tegyél a konzol és a kártya közé egy olcsó <b>HDMI-elosztót</b> (1 be, 2 ki): az egyik kimenet a tévére, a másik a kártyába megy. A SubBridge így a háttérben olvas, a fordítás a telefonodon jelenik meg.</li>
</ul>
<p>Tipp: az automatikus képformátum (1440p vagy 1080p, 60 fps) a legjobb; a <i>Beállítások › Capture card</i> alatt kézzel is választhatsz.</p>
"""),
("minimized", "Az ablak le van kicsinyítve", """
<p>Kicsinyített ablakot az operációs rendszer nem rajzol ki, így nincs mit kiolvasni. Állítsd vissza az ablakot – más ablakok mögött nyugodtan maradhat.</p>
<p>Ha a chiaki-ng teljes képernyőn fut egy másik monitoron, az is jó.</p>
"""),
("black", "Fekete a kép / a monitor másik bemenetre váltott", """
<p>Ha a játékot a monitoron közvetlenül a konzolról nézed (HDMI), és a számítógép ugyanerre a monitorra van kötve, akkor a monitor bemenetváltásakor a számítógép „elveszíti” a kijelzőt, és a Remote Play kép nem frissül.</p>
<p><b>Megoldás:</b></p>
<ul>
<li><b>HDMI dummy plug</b> (pár ezer forintos „kijelzőemulátor”): bedugod a videókártya egy szabad portjára, a számítógép azt hiszi, van egy második monitor, és oda teszed a Remote Play ablakot.</li>
<li><b>Virtuális kijelző</b> szoftverrel (Windowson például egy virtuális kijelző-illesztő, Linuxon xrandr virtuális kimenet), ha a videókártya támogatja.</li>
<li>Ha két monitorod van, tedd a Remote Play ablakot arra, amelyik a számítógépen marad.</li>
</ul>
"""),
("window_gone", "Nem találom az ablakot", """
<p>A Remote Play program valószínűleg bezárult vagy újraindult. Indítsd el, majd a képforrásnál nyomd meg a frissítés gombot, és válaszd ki újra.</p>
"""),
("phone", "Telefon csatlakoztatása", """
<p><b>Android és iPhone:</b> olvasd be a QR-kódot a kamera alkalmazással, és nyisd meg a linket. Ha nem megy a QR, írd be a böngészőbe a címet, és add meg a PIN-kódot.</p>
<p><b>Kezdőképernyőre tétel:</b> Androidon a Chrome menüjében „Hozzáadás a kezdőképernyőhöz”, iPhone-on a Safari Megosztás gombjával „Főképernyőhöz adás”. Ezután alkalmazásként indul.</p>
<p><b>A képernyő ne aludjon el:</b> Androidon a Chrome ébren tartja a képernyőt. <b>iPhone-on</b> sima (HTTP) kapcsolaton ez nem lehetséges: állítsd a <i>Beállítások › Kijelző és fényerő › Automatikus zárolás</i> opciót <b>„Soha”</b>-ra, amíg játszol.</p>
<p><b>Nem csatlakozik?</b> Ellenőrizd, hogy a telefon ugyanazon a Wi-Fin van-e (nem vendéghálózaton), és hogy a számítógép tűzfala engedi-e a megadott portot.</p>
<p><b>HTTPS (titkosított kapcsolat):</b> a <i>Beállítások › Telefon és hálózat</i> alatt bekapcsolható. A program saját tanúsítványt készít, ezért a telefon első alkalommal figyelmeztet: Chrome-ban <i>Speciális › Tovább</i>, Safariban <i>Részletek megjelenítése › weboldal meglátogatása</i>. Utána újra kell olvasni a QR-kódot.</p>
"""),
("network", "A port foglalt / nem indul a webszerver", """
<p>Egy másik program (vagy egy másik {app} példány) már használja ezt a portot. Zárd be a másik példányt, vagy a <i>Beállítások › Telefon és hálózat</i> alatt válassz másik portot (például 8766), majd olvasd be újra a QR-kódot.</p>
"""),
("profiles", "Profilok (játékonként külön beállítás)", """
<p>Fent a <b>Profil</b> listában játékonként külön beállítást tarthatsz: feliratterület, felismerés, fordítómotor, szószedet. A „…” gombbal új profilt hozhatsz létre, lemásolhatod vagy átnevezheted a meglévőt.</p>
<p><b>Szószedet:</b> a <i>Beállítások › Szószedet</i> alatt megadhatod a neveket, amiket nem kell lefordítani, és a rendszeresen rosszul fordított kifejezések javítását.</p>
"""),
("translator", "Fordítás és adatvédelem", """
<p><b>Offline (alapértelmezett):</b> ingyenes, internet nélkül is működik, semmilyen adat nem hagyja el a gépet. Első használatkor le kell tölteni a nyelvi modellt (kb. 100 MB).</p>
<p><b>DeepL:</b> a legjobb minőség. Regisztrálj egy ingyenes DeepL API-fiókot (havi 500&nbsp;000 karakter ingyenes), és másold be a kulcsot. Ha a DeepL lassú vagy nem elérhető, az offline fordító azonnal beugrik.</p>
<p><b>Google Cloud:</b> a hivatalos Google Cloud Translation API, saját kulccsal (Google Cloud Console › API-k › Cloud Translation API). A {app} soha nem használja a nem hivatalos, ingyenes Google-végpontot.</p>
<p><b>LibreTranslate:</b> nyílt forrású fordítószerver. Futtathatod a saját gépeden (például Dockerrel), ilyenkor a szöveg nem hagyja el a hálózatodat.</p>
<p>A {app} nem gyűjt adatot, nem küld statisztikát. A képernyőképek soha nem hagyják el a gépet; online fordító választásakor <b>csak a felirat szövege</b> megy el a választott szolgáltatásnak.</p>
"""),
],
"en": [
("start", "Getting started", """
<p>{app} reads the subtitles on your screen, translates them and sends them live to your phone.</p>
<ol>
<li><b>Source:</b> pick the Remote Play window (or the whole screen).</li>
<li><b>Subtitle area:</b> wait for a subtitle in the game, click <i>Select subtitle area</i> and drag a rectangle around it. Leave room for two-line subtitles.</li>
<li><b>Phone:</b> scan the QR code with the phone camera. Phone and computer must be on the same Wi-Fi.</li>
<li>Press <b>Start</b>.</li>
</ol>
<p><b>Recommended in-game settings</b> (Settings › UI › Subtitles &amp; Captions, or similar):</p><ul><li><b>Subtitles:</b> On – the fullest level (3/3): ambient and NPC speech get subtitles too, so they are translated as well</li><li><b>Closed Captions:</b> Off</li><li><b>Size:</b> Medium</li><li><b>Speaker Names:</b> On</li><li><b>Background:</b> Solid – a plain box, covered exactly</li></ul>
"""),
("gta", "Tuned for GTA VI", """
<p>{app} is built specifically for <b>GTA VI</b>: recognition is tuned to the game's subtitle boxes and font, and the translator knows the game's characters, places and slang.</p>
<ul>
<li><b>Translation memory:</b> more than 15,000 of the game's dialogue lines are translated one by one in advance. When such a line appears you see the finished translation instantly and offline, with consistent names and tone.</li>
<li><b>Slang and names</b> keep growing between releases (downloaded automatically, no new version needed).</li>
<li><b>Anything not in the memory</b> (passers-by, radio, rare lines) is translated live by the translator you chose.</li>
</ul>
<p style="color:#8a8f9a"><small>SubBridge is an independent, unofficial program; it is not affiliated with or endorsed by Rockstar Games or Take-Two Interactive. "Grand Theft Auto" and "GTA" are trademarks of Take-Two Interactive and are used here only to name the game.</small></p>
"""),
("v1", "Precise translator, Subtitle history, Learning mode", """
<p><b>Precise translator:</b> <i>Get precise translator</i> in the Translator card downloads a much better offline model (about 200 MB, once). It is used automatically afterwards.</p>
<p><b>Subtitle history:</b> in the Last subtitle card. Read everything back, search, save to a file. Double-click a line to fix the translation – that sentence always shows your way from then on.</p>
<p><b>Learning mode:</b> the original shows small under the translation on the game picture.</p>
<p><b>Bug report:</b> the flag button at the top sends the developer what's needed to fix a problem.</p>
"""),
("chiaki", "PS5 Remote Play setup (chiaki-ng)", """
<p><b>On Windows:</b> use chiaki-ng in F11 fullscreen. On an ultrawide monitor keep the picture 16:9 (black bars at the sides) – don't stretch or zoom it.</p>
<p>{app} does not include a Remote Play client. For PS5 we recommend the open-source <b>chiaki-ng</b> (installed separately, AGPL licence).</p>
<ol>
<li>Install: on Linux via Flatpak (<code>flatpak install flathub io.github.streetpea.Chiaki4deck</code>), on Windows from <code>github.com/streetpea/chiaki-ng</code>.</li>
<li>On the PS5: <i>Settings › System › Remote Play</i> – enable it. Keep it reachable in rest mode (<i>Power Saving › Features Available in Rest Mode › Stay Connected to the Internet</i>).</li>
<li>In chiaki-ng sign in with PSN, pick the console and pair using the code shown on the PS5.</li>
<li>Resolution: 1080p is enough. Higher resolution improves recognition but needs more bandwidth.</li>
<li>The chiaki-ng window may stay behind other windows, but <b>don't minimise it</b>.</li>
</ol>
"""),
("capture_card", "Using a capture card", """
<p>Instead of Remote Play you can read the console's picture through a <b>capture card</b> (HDMI→USB, e.g. Elgato or any UVC card). Works with any console.</p>
<ol>
<li>Connect console HDMI out → card HDMI in, card USB → computer. If the card has an <b>HDMI out (passthrough)</b>, connect it to your TV or monitor: you play without delay while {app} reads in the background.</li>
<li><b>On PS5 turn HDCP off</b> or the card gets a black picture: <i>Settings › System › HDMI › Enable HDCP</i> – off.</li>
<li>In {app} pick the <i>Capture card / video device</i> source and mark the subtitle area.</li>
<li>Without passthrough open the <b>Game View</b>: the game full screen with sound, translated subtitles drawn right over the originals.</li>
</ol>
<p><b>Cards without passthrough (e.g. a small 4K HDMI→USB adapter):</b></p>
<ul>
<li>Use a <b>USB 3</b> (blue or USB-C) port – USB 2 only gives 720p; the app warns you.</li>
<li>PS5: <i>Screen and Video › Video Output › Resolution</i> = <b>1440p</b> (if missing: 1080p), <i>HDR</i> = <b>off</b>, <i>System › HDMI › HDCP</i> = <b>off</b>. Such adapters often reject 4K 60 Hz and HDR signals (black picture).</li>
<li>Play on the PC: open the <b>Game View</b> (double-click = full screen); the sound plays there too.</li>
<li>Play on the TV: put a cheap <b>HDMI splitter</b> (1 in, 2 out) between console and card: one output to the TV, the other to the card. SubBridge reads in the background and the translation shows on your phone.</li>
</ul>
<p>Tip: automatic format (1440p or 1080p, 60 fps) is best; you can pick one under <i>Settings › Capture card</i>.</p>
"""),
("minimized", "The window is minimised", """
<p>The operating system doesn't draw minimised windows, so there's nothing to read. Restore it – it can stay behind other windows.</p>
"""),
("black", "Black image / monitor switched input", """
<p>If you watch the console directly on a monitor that the computer also uses, switching the monitor input makes the computer lose that display and the Remote Play picture stops updating.</p>
<ul>
<li>A <b>HDMI dummy plug</b> (display emulator) in a free GPU port makes the PC believe a second monitor exists – put the Remote Play window there.</li>
<li>A <b>virtual display</b> driver does the same in software.</li>
<li>With two monitors, keep the Remote Play window on the one that stays on the PC.</li>
</ul>
"""),
("window_gone", "Window not found", """
<p>The Remote Play app was probably closed or restarted. Start it, press refresh next to the source and select it again.</p>
"""),
("phone", "Connecting your phone", """
<p><b>Android and iPhone:</b> scan the QR code with the camera app and open the link. If that fails, type the address into the browser and enter the PIN.</p>
<p><b>Home screen:</b> Chrome menu › “Add to Home screen” on Android, Safari Share › “Add to Home Screen” on iPhone.</p>
<p><b>Keep the screen on:</b> Android Chrome keeps it awake. <b>On iPhone</b> this isn't possible over plain HTTP – set <i>Settings › Display &amp; Brightness › Auto-Lock</i> to <b>Never</b> while playing.</p>
<p><b>Can't connect?</b> Make sure the phone is on the same Wi-Fi (not a guest network) and the computer firewall allows the port.</p>
<p><b>HTTPS (encrypted):</b> enable it under <i>Settings › Phone &amp; network</i>. The certificate is self-made, so the phone warns the first time: in Chrome tap <i>Advanced › Proceed</i>, in Safari <i>Show details › visit this website</i>. Then scan the QR code again.</p>
"""),
("network", "Port in use / web server won't start", """
<p>Another program (or another {app} instance) already uses this port. Close the other instance or pick another port under <i>Settings › Phone &amp; network</i> (e.g. 8766), then scan the QR code again.</p>
"""),
("profiles", "Profiles (settings per game)", """
<p>The <b>Profile</b> list at the top keeps separate settings per game: subtitle area, recognition, translator, glossary. Use the “…” button to create, duplicate or rename profiles.</p>
<p><b>Glossary:</b> under <i>Settings › Glossary</i> list names that must not be translated and fixes for terms that keep coming out wrong.</p>
"""),
("translator", "Translation and privacy", """
<p><b>Offline (default):</b> free, works without internet, nothing leaves your computer. The language model (~100 MB) is downloaded on first use.</p>
<p><b>DeepL:</b> best quality. Create a free DeepL API account and paste the key. If DeepL is slow or unavailable, the offline translator steps in instantly.</p>
<p><b>Google Cloud:</b> the official Google Cloud Translation API with your own key. {app} never uses the unofficial free Google endpoint.</p>
<p><b>LibreTranslate:</b> an open-source translation server. Run it on your own PC (e.g. with Docker) and the text never leaves your network.</p>
<p>{app} collects no data and sends no telemetry. Screenshots never leave your computer; with an online translator <b>only the subtitle text</b> is sent to the chosen service.</p>
"""),
],
}
