"""Text preparation around machine translation.

* English slang / street talk / texting → plain English before translating (machine translation
  understands "going to" far better than "gonna", "running" than "runnin'");
* Hungarian post-fixes: games talk informally – formal "Ön/kérem/jöjjön" becomes "te/kérlek/gyere";
* generic speaker roles ("Stranger", "Local", "Bartender") get a translated label; real names stay.

Built-in lists below; content packs downloaded from the project site (see remote.py) extend or
override them without an app update."""
from __future__ import annotations

import json
import re
import threading

from ..paths import data_dir

# --------------------------------------------------------------------------- built-in: English slang
_SLANG_BUILTIN: list[tuple[str, str]] = [
    # dropped g: lookin' -> looking (not "in'" itself)
    (r"\b(\w{2,})in'(?=\W|$)", r"\1ing"),
    # contractions and reductions
    (r"\bgonna\b", "going to"), (r"\bwanna\b", "want to"), (r"\bgotta\b", "have to"), (r"\bhafta\b", "have to"),
    (r"\boughta\b", "ought to"), (r"\bkinda\b", "kind of"), (r"\bsorta\b", "sort of"), (r"\bouta\b", "out of"),
    (r"\boutta\b", "out of"), (r"\blotta\b", "lot of"), (r"\blemme\b", "let me"), (r"\bgimme\b", "give me"),
    (r"\bdunno\b", "don't know"), (r"\bdontcha\b", "don't you"), (r"\bdidja\b", "did you"), (r"\bdidya\b", "did you"),
    (r"\bwhatcha\b", "what are you"), (r"\bwhaddaya\b", "what do you"), (r"\bwhaddya\b", "what do you"),
    (r"\bgotcha\b", "got you"), (r"\bbetcha\b", "bet you"), (r"\bya know\b", "you know"), (r"\by'know\b", "you know"),
    (r"\bya\b", "you"), (r"\byer\b", "your"), (r"\by'all\b", "you all"), (r"\byall\b", "you all"),
    (r"\bI'mma\b", "I'm going to"), (r"\bImma\b", "I'm going to"), (r"\bimma\b", "I'm going to"),
    (r"\b'em\b", "them"), (r"\b'cause\b", "because"), (r"\bcuz\b", "because"), (r"\bcos\b", "because"),
    (r"\b'bout\b", "about"), (r"\b'round\b", "around"), (r"\b'til\b", "until"), (r"\btil\b", "until"),
    (r"\bain't nothin(?:g|')?", "there's nothing"), (r"\bain't got\b", "don't have"), (r"\bain't\b", "isn't"),
    (r"\byo'(?=\s)", "your"), (r"\bnothin'?\b", "nothing"), (r"\bsomethin'?\b", "something"),
    (r"\bnah\b", "no"), (r"\bnope\b", "no"), (r"\byep\b", "yes"), (r"\byup\b", "yes"), (r"\bya'?ll\b", "you all"),
    (r"\bwhat's good\b", "what's up"), (r"\bwassup\b", "what's up"), (r"\bsup\b", "what's up"),
    (r"\b'Ey\b", "Hey"), (r"\bayo\b", "hey"), (r"\bAyo\b", "Hey"), (r"\byo\b(?=[,!])", "hey"),
    # street / slang words
    (r"\bhomie\b", "buddy"), (r"\bhomies\b", "buddies"), (r"\bhomeboy\b", "buddy"), (r"\bdawg\b", "dude"),
    (r"\bbruh\b", "bro"), (r"\bbrah\b", "bro"), (r"\bfam\b", "friend"), (r"\bshawty\b", "girl"),
    (r"\bfeds\b", "federal agents"), (r"\bfive-o\b", "police"), (r"\bpopo\b", "police"), (r"\bpigs\b", "cops"),
    (r"\bstrapped\b", "armed"), (r"\bpiece\b(?= on| in)", "gun"), (r"\bheat\b(?= on)", "gun"),
    (r"\bboosting\b", "stealing"), (r"\bboost\b(?= a| the| that)", "steal"), (r"\bjacked\b", "stolen"),
    (r"\bsnitch\b", "informer"), (r"\bsnitching\b", "informing"), (r"\bplug\b(?= )", "dealer"),
    (r"\bstash\b", "hidden supply"), (r"\bscore\b(?= big)", "profit"), (r"\blick\b(?=\W)", "robbery"),
    (r"\bopps\b", "enemies"), (r"\bdough\b", "money"), (r"\bbucks\b", "dollars"), (r"\bstacks\b", "piles of money"),
    (r"\bsus\b", "suspicious"), (r"\bcap\b(?=[.!?,])", "lie"), (r"\bno cap\b", "no lie"), (r"\bdeadass\b", "seriously"),
    (r"\bfr\b", "for real"), (r"\bngl\b", "not going to lie"), (r"\blowkey\b", "kind of"), (r"\bhighkey\b", "really"),
    (r"\blit\b(?=[.!?,])", "great"), (r"\bdope\b(?=[.!?,])", "great"), (r"\bbussin\b", "really good"), (r"\bsalty\b", "bitter"), (r"\bbeef\b(?= with)", "conflict"),
    (r"\bcrib\b", "home"), (r"\bwhip\b(?=\W)", "car"), (r"\bride\b(?=[.!?,])", "car"), (r"\bkicks\b", "shoes"),
    (r"\bbae\b", "babe"), (r"\bboo\b(?=[.!?,])", "babe"), (r"\bsis\b", "sister"), (r"\bOG\b", "veteran"), (r"\bmy G\b", "my friend"),
    (r"\bfuckin'?\b", "fucking"), (r"\bmotherfuckin'?\b", "motherfucking"), (r"\bgoddamn\b", "goddamn"),
    # texting
    (r"(?-i:\bu\b)(?!\.)", "you"), (r"(?-i:\bur\b)", "your"), (r"(?-i:\br\b)(?= u\b| you\b)", "are"), (r"\bthx\b", "thanks"),
    (r"\bthnx\b", "thanks"), (r"\bpls\b", "please"), (r"\bplz\b", "please"), (r"\bidk\b", "I don't know"),
    (r"\bomg\b", "oh my god"), (r"\bOMG\b", "Oh my god"), (r"\btho\b", "though"), (r"\brn\b", "right now"),
    (r"\bppl\b", "people"), (r"\blmk\b", "let me know"), (r"\bLmk\b", "Let me know"), (r"\bcmon\b", "come on"),
    (r"\bdnt\b", "don't"), (r"\bbtw\b", "by the way"), (r"\bBtw\b", "By the way"), (r"\brly\b", "really"),
    (r"\bsry\b", "sorry"), (r"\bnvm\b", "never mind"), (r"\bty\b", "thank you"), (r"\bwyd\b", "what are you doing"),
    (r"\bhbu\b", "how about you"), (r"\bily\b", "I love you"), (r"\btmrw\b", "tomorrow"), (r"\b2nite\b", "tonight"),
    (r"\bgtg\b", "got to go"), (r"\bbrb\b", "be right back"), (r"\bnp\b", "no problem"), (r"\bb4\b", "before"),
    (r"\bvry\b", "very"), (r"\bwtf\b", "what the fuck"), (r"\bWTF\b", "What the fuck"), (r"\blol\b", "haha"),
    (r"\blmao\b", "haha"), (r"\bsmh\b", "shaking my head"), (r"\bimo\b", "in my opinion"), (r"\bjk\b", "just kidding"),
]

# --------------------------------------------------------------------------- built-in: Hungarian fixes
_POST_BUILTIN: dict[str, list[tuple[str, str]]] = {"hu": [
    (r"\bTudassa velem\b", "Szólj"), (r"\btudassa velem\b", "szólj"),
    (r"\bKérem\b", "Kérlek"), (r"\bkérem\b", "kérlek"),
    (r"\bÖnnek\b", "Neked"), (r"\bönnek\b", "neked"), (r"\bÖnért\b", "Érted"), (r"\bönért\b", "érted"),
    (r"\bÖnt\b", "Téged"), (r"\bönt\b", "téged"), (r"\bÖnnel\b", "Veled"), (r"\bönnel\b", "veled"),
    (r"\bÖnről\b", "Rólad"), (r"\bönről\b", "rólad"), (r"\bÖntől\b", "Tőled"), (r"\böntől\b", "tőled"),
    (r"\bÖn\b", "Te"), (r"\bön\b", "te"), (r"\bÖné\b", "A tiéd"), (r"\bMaga\b(?= \w+sz\b)", "Te"),
    (r"\bMit tehetünk önért\b", "Miben segíthetünk"), (r"\bHogy van\b", "Hogy vagy"), (r"\bhogy van\b", "hogy vagy"),
    (r"\bjöjjön\b", "gyere"), (r"\bJöjjön\b", "Gyere"), (r"\bmenjen\b", "menj"), (r"\bMenjen\b", "Menj"),
    (r"\bnézze\b", "nézd"), (r"\bNézze\b", "Nézd"), (r"\bvárjon\b", "várj"), (r"\bVárjon\b", "Várj"),
    (r"\bhallgasson\b", "hallgass"), (r"\bHallgasson\b", "Hallgass"),
    (r"\bmondja\b(?= meg| el)", "mondd"), (r"\bMondja\b(?= meg| el)", "Mondd"),
    (r"\bsegítsen\b", "segíts"), (r"\bSegítsen\b", "Segíts"), (r"\bálljon\b", "állj"), (r"\bÁlljon\b", "Állj"),
    (r"\bÜdvözöljük\b", "Üdv"), (r"\bkérdezze\b", "kérdezd"), (r"\bKérdezze\b", "Kérdezd"),
    (r"\bmaradjon\b", "maradj"), (r"\bMaradjon\b", "Maradj"), (r"\bfigyeljen\b", "figyelj"), (r"\bFigyeljen\b", "Figyelj"),
    (r"\bnyugodjon meg\b", "nyugodj meg"), (r"\bNyugodjon meg\b", "Nyugodj meg"),
    (r"\bvigyázzon\b", "vigyázz"), (r"\bVigyázzon\b", "Vigyázz"), (r"\bsiessen\b", "siess"), (r"\bSiessen\b", "Siess"),
    (r"\btűnjön el\b", "tűnj el"), (r"\bTűnjön el\b", "Tűnj el"), (r"\bfogja be\b", "fogd be"), (r"\bFogja be\b", "Fogd be"),
]}

# --------------------------------------------------------------------------- built-in: speaker roles
_ROLES_BUILTIN: dict[str, dict[str, str]] = {"hu": {
    "local": "Helybeli", "locals": "Helybeliek", "tourist": "Turista", "tourists": "Turisták",
    "taxi": "Taxis", "cop": "Zsaru", "cops": "Zsaruk", "police": "Rendőr", "officer": "Rendőr",
    "man": "Férfi", "woman": "Nő", "guy": "Fickó", "girl": "Lány", "kid": "Kölyök",
    "driver": "Sofőr", "drivers": "Sofőrök", "pedestrian": "Járókelő", "cashier": "Pénztáros", "clerk": "Eladó",
    "bartender": "Pultos", "guard": "Őr", "security": "Biztonsági őr", "security guard": "Biztonsági őr",
    "stranger": "Idegen", "strangers": "Idegenek", "radio": "Rádió", "dj": "DJ", "phone": "Telefon",
    "fan": "Rajongó", "fans": "Rajongók", "biker": "Motoros", "bikers": "Motorosok", "gang member": "Bandatag",
    "dealer": "Díler", "shopkeeper": "Boltos", "customer": "Vásárló", "worker": "Munkás", "workers": "Munkások",
    "crowd": "Tömeg", "passenger": "Utas", "teenager": "Tinédzser", "homeless": "Hajléktalan", "vendor": "Árus",
    "vagrant": "Csavargó", "vagrants": "Csavargók", "neighbor": "Szomszéd", "neighbour": "Szomszéd",
    "bouncer": "Kidobó", "pilot": "Pilóta", "trooper": "Járőr", "deputy": "Seriffhelyettes", "sheriff": "Seriff",
    "inmate": "Rab", "boater": "Hajós", "fisherman": "Horgász", "surfer": "Szörfös", "jogger": "Kocogó",
    "partygoer": "Bulizó", "partygoers": "Bulizók", "influencer": "Influenszer", "hostess": "Hostess",
    "waiter": "Pincér", "waitress": "Pincérnő", "mechanic": "Szerelő", "nurse": "Ápoló", "doctor": "Orvos",
    "gangster": "Gengszter", "gangsters": "Gengszterek", "thug": "Verőember", "thugs": "Verőemberek",
    "announcer": "Bemondó", "host": "Műsorvezető", "caller": "Telefonáló", "reporter": "Riporter",
    "staff member": "Alkalmazott", "staff": "Személyzet", "employee": "Alkalmazott", "manager": "Vezető",
    "owner": "Tulajdonos", "boss": "Főnök", "dispatcher": "Diszpécser", "paramedic": "Mentős",
    "firefighter": "Tűzoltó", "soldier": "Katona", "agent": "Ügynök", "suspect": "Gyanúsított",
    "victim": "Áldozat", "witness": "Szemtanú", "hitchhiker": "Stoppos", "street vendor": "Utcai árus",
    "preacher": "Prédikátor", "hooker": "Prostituált", "dancer": "Táncos", "dancers": "Táncosok",
    "singer": "Énekes", "street performer": "Utcazenész", "photographer": "Fotós", "hunter": "Vadász",
    "hunters": "Vadászok", "farmer": "Farmer", "ranger": "Vadőr", "lifeguard": "Vízimentő", "coach": "Edző",
    "player": "Játékos", "players": "Játékosok", "kids": "Gyerekek", "people": "Emberek", "voice": "Hang",
    "narrator": "Narrátor", "unknown": "Ismeretlen", "everyone": "Mindenki", "group": "Csoport",
}}


class TextPrep:
    """Merged built-in + downloaded rules, compiled once (reloaded when a pack updates)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reload()

    @staticmethod
    def _packs() -> dict:
        out = {}
        d = data_dir() / "packs"
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return out

    def reload(self):
        packs = self._packs()
        slang = list(_SLANG_BUILTIN) + [tuple(x) for x in packs.get("slang-en", {}).get("rules", [])]
        post = {k: list(v) for k, v in _POST_BUILTIN.items()}
        for lang, rules in packs.get("post", {}).get("rules", {}).items():
            post.setdefault(lang, []).extend(tuple(r) for r in rules)
        roles = {k: dict(v) for k, v in _ROLES_BUILTIN.items()}
        for lang, m in packs.get("roles", {}).get("roles", {}).items():
            roles.setdefault(lang, {}).update({k.lower(): v for k, v in m.items()})

        def comp(rules, fold=False):
            out = []
            for pat, rep in rules:
                try:
                    # lower-case slang also matches at the start of a sentence ("Bruh", "Ain't nothin'")
                    flags = re.IGNORECASE if fold and not re.search(r"[A-Z]", re.sub(r"\\[A-Za-z]", "", pat)) else 0
                    out.append((re.compile(pat, flags), rep))
                except re.error:
                    continue
            return out
        with self._lock:
            self.slang = comp(slang, fold=True)
            self.post = {k: comp(v) for k, v in post.items()}
            self.roles = roles
            self.versions = {k: v.get("version", 0) for k, v in packs.items()}

    def prep(self, text: str, src: str) -> str:
        if src != "en":
            return text
        for pat, rep in self.slang:
            text = pat.sub(rep, text)
        return re.sub(r"\s{2,}", " ", text)

    def post_fix(self, text: str, tgt: str) -> str:
        for pat, rep in self.post.get(tgt, []):
            text = pat.sub(rep, text)
        return text

    def speaker(self, name: str | None, tgt: str) -> str | None:
        """Generic roles get translated ("Security Guard" -> "Biztonsági őr"); real names stay."""
        if not name:
            return name
        m = self.roles.get(tgt, {})
        return m.get(name.lower(), name)


_inst: TextPrep | None = None


def textprep() -> TextPrep:
    global _inst
    if _inst is None:
        _inst = TextPrep()
    return _inst
