# Kiadási terv és munkalista / Release plan

Sok felhasználó van, ezért **minden kiadás ugyanígy megy**, kihagyás nélkül:

1. Javítás + regressziós teszt (`tests/`), `pytest` zöld.
2. Élő próba a saját gépen valódi játékkal (`python -m subbridge --start`), felvétel `build/recN/record.py`-jal,
   átnézés: angol nem látszik, nem ugrál.
3. Verziószám emelése: `pyproject.toml`, `subbridge/branding.py`, `packaging/windows/subbridge.iss`,
   `android/app/build.gradle*`, `site/index.html` (dl map).
4. `git tag vX.Y.Z && git push origin vX.Y.Z` → a GitHub CI mindhárom rendszeren buildel és **önteszteli**
   (`--selftest`); csak zöld build kerül a Releases-be.
5. Feltöltés `rolandhrvth.hu/subbridge/dl/` alá, `SHA256SUMS.txt` újragenerálása. **Az előző verzió fájljai
   maradnak** (vissza lehet lépni).
6. Csak ezután: `site/feed/index.json` → `latest` + hír. Ettől látja minden felhasználó a frissítés-értesítést.
   Hibás kiadásnál: a `latest` visszaállítása az előzőre azonnal leállítja a frissítés-ajánlást.

Szleng- és szerepfordítás javítása **appfrissítés nélkül**: `site/feed/packs/*.json` → `version` +1 → deploy.

## Nyitott feladatok (prioritás szerint)

1. **[javítva a main ágon, élő próbára vár → 0.1.1]** Ha a feliratdoboz megnő (közbeszólás, hosszabb sor),
   a takarás azonnal a teljes új dobozra nő – az angol nem látszik ki. Teszt: `tests/test_classic_overlay.py`.
2. Több beszélőnél néha ugrál a szöveg (sorok helycseréje). Felvétel kell róla, utána `classic_overlay.py`
   „claimed”/slot logika.
3. Fordítási hibák (szleng, pl. „X-ass … type shit”): `feed/packs/slang-en.json` bővítése – app-frissítés nélkül.
4. Windows: valódi gépen még nem próbálta senki (csak a CI önteszt) – első visszajelzéseket figyelni.
