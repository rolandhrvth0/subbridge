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

## Bug reports (since 0.1.8)
- Users send reports from the app (flag button) -> POST https://rolandhrvth.hu/subbridge/api/report ->
  VPS service `subbridge-report` (/opt/subbridge-report/report_server.py, port 3310, nginx location in
  /etc/nginx/sites-enabled/rolandhrvth) -> /var/lib/subbridge-reports/<time>-<id>/ (report.json, strip.jpg, frame.jpg).
- `tools/reports.sh` pulls them to build/reports/ (private, never commit) and lists the new ones.
  Check at the start of every session; fix what is real, answer via the contact the user left.

## Staged rollout / rollback (apps 0.1.8+)
- publish_release.sh writes `rollout: {start, hours: 24, from: 20}`: 20 % of installs get the auto-update at
  once, everyone by 24 h. `ROLLOUT_HOURS=0 tools/publish_release.sh …` = everyone now (urgent fixes).
- `tools/rollout.sh status|pause|resume|full|rollback <ver>`. Rollback puts the old version in `latest`
  with `replaces: [bad]` -> installs of the bad version go back immediately (old files stay on the server).
- Before 0.1.8 apps ignore these fields (they update to anything newer at once).

## 1.0 additions
- Precise offline model: OPUS-MT tc-big en-hu (CC-BY 4.0) converted with build/conv/run.sh (ct2 int8), zipped and
  hosted at https://rolandhrvth.hu/subbridge/models/opus-big-en_hu-1.zip; sha256 pinned in translate/argos.py PRECISE.
  A new model version = new file name + new sha in the app.
- User corrections: <data>/corrections.json (exact sentence). Sent fixes land in /var/lib/subbridge-reports/corrections.jsonl
  (tools/reports.sh lists them) – turn recurring ones into slang/post pack rules.
