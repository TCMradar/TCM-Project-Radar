#!/usr/bin/env python3
import json, re, hashlib
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "radar.json"

QUERIES = [
    # Nederland
    "voedingsmiddelen fabriek uitbreiding Nederland",
    "food factory expansion Netherlands",
    "zuivelfabriek investering Nederland",
    "food processing plant investment Netherlands",
    "nieuwe productielijn voedingsmiddelen Nederland",
    "food grade vloer fabriek uitbreiding Nederland",

    # België
    "voedingsmiddelen fabriek uitbreiding België",
    "food factory expansion Belgium",
    "agrofood productie uitbreiding België",
    "nieuwe productielijn voedingsmiddelen België",

    # Duitsland
    "Lebensmittelindustrie Fabrikerweiterung Deutschland",
    "Lebensmittelwerk Neubau Deutschland",
    "Molkerei Investition Deutschland",
    "Lebensmittel Produktionserweiterung Deutschland",
    "neue Produktionslinie Lebensmittel Deutschland",
    "Lebensmittelfabrik Sanierung Deutschland",
    "Industrieboden Beschichtung Lebensmittel Deutschland",

    # Polen
    "przemysł spożywczy rozbudowa Polska",
    "fabryka żywności inwestycja Polska",
    "zakład produkcyjny rozbudowa Polska",
    "nowa linia produkcyjna żywność Polska",
    "budowa fabryki spożywczej Polska",
    "remont zakładu spożywczego Polska",
    "posadzka przemysłowa żywność Polska",
]

FOOD_WORDS = [
    "food", "food industry", "food processing", "food factory",
    "voeding", "voedingsmiddelen", "zuivel", "dairy",
    "meat", "vlees", "bakker", "bakery", "brewery",
    "drank", "beverage", "chocolate", "potato", "aardappel",
    "snack", "ingredients", "ingrediënten", "agrofood",
    "cold store", "cold storage", "koel", "productielijn",
    "productielocatie",

    # Duits
    "lebensmittel", "lebensmittelindustrie", "lebensmittelwerk",
    "molkerei", "milch", "fleisch", "bäckerei", "getränke",
    "schokolade", "kartoffel", "snack", "lebensmittelproduktion",

    # Pools
    "przemysł spożywczy", "spożywczy", "żywność",
    "fabryka żywności", "zakład produkcyjny", "mleczarnia",
    "mięso", "piekarnia", "napoje", "czekolada",
    "ziemniak", "przetwórstwo spożywcze",
]

PROJECT_WORDS = [
    "investment", "investering", "invest", "expansion",
    "uitbreiding", "bouw", "new build", "nieuwbouw",
    "factory", "fabriek", "plant", "facility", "faciliteit",
    "modernisation", "modernisering", "renovation", "renovatie",
    "production line", "productielijn", "warehouse", "magazijn",
    "logistics", "logistiek", "upgrade", "upgrading",
    "capacity", "masterplan", "construction", "construction started",
    "bouw gestart",

    # Duits
    "investition", "investitionen", "erweiterung", "ausbau",
    "neubau", "fabrik", "werk", "anlage", "produktionsanlage",
    "modernisierung", "sanierung", "produktionslinie",
    "lager", "logistik", "kapazität", "bau gestartet",

    # Pools
    "inwestycja", "inwestycje", "rozbudowa", "budowa",
    "nowa fabryka", "fabryka", "zakład", "modernizacja",
    "remont", "linia produkcyjna", "magazyn", "logistyka",
    "wydajność", "budowa rozpoczęta",
]

NEGATIVE_WORDS = [
    "woning", "woningbouw", "residential",
    "office", "kantoor", "school", "hotel", "retail"
]

def load():
    if DATA.exists():
        return json.loads(DATA.read_text(encoding="utf-8"))
    return {"updated": None, "projects": []}

def rss(q):
    if "Deutschland" in q or "Deutsch" in q:
        locale = "&hl=de&gl=DE&ceid=DE:de"
    elif "Polska" in q or "Poland" in q:
        locale = "&hl=pl&gl=PL&ceid=PL:pl"
    elif "België" in q or "Belgium" in q:
        locale = "&hl=nl&gl=BE&ceid=BE:nl"
    else:
        locale = "&hl=nl&gl=NL&ceid=NL:nl"

    url = "https://news.google.com/rss/search?q=" + quote(q) + locale
    req = Request(url, headers={"User-Agent": "TCMRadar/1.3"})

    with urlopen(req, timeout=20) as r:
        return ET.fromstring(r.read())

def text_score(title, desc):
    s = (title + " " + desc).lower()
    food = sum(1 for w in FOOD_WORDS if w in s)
    proj = sum(1 for w in PROJECT_WORDS if w in s)
    neg = sum(1 for w in NEGATIVE_WORDS if w in s)
    score = min(98, 45 + food*5 + proj*4 - neg*8)
    if food < 1 or proj < 1 or neg >= 2:
        return 0
    return score

def investment(s):
    m = re.search(r'€\s?([0-9]+(?:[.,][0-9]+)?)\s*(miljoen|m|million|mln)', s, re.I)
    if not m: return None
    return int(float(m.group(1).replace(",",".")) * 1_000_000)

def potential(inv, score):
    if not inv: return "Te bepalen"
    low = max(25000, round(inv * 0.0015 / 5000) * 5000)
    high = max(50000, round(inv * 0.005 / 5000) * 5000)
    if score >= 90: high = max(high, low*2)
    def fmt(x):
        return f"€{x//1000}k"
    return f"{fmt(low)}–{fmt(high)}"

def main():
    db = load()
    existing = {p.get("id") for p in db["projects"]}
    found = {}
    for q in QUERIES:
        try:
            root = rss(q)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                try:
                    pub_dt = parsedate_to_datetime(pub)
                    if datetime.now(timezone.utc) - pub_dt.astimezone(timezone.utc) > timedelta(days=180):
                        continue
                except Exception:
                    continue
    
                sc = text_score(title, desc)
                if sc < 65 or not link: continue
                uid = hashlib.sha1(link.encode()).hexdigest()[:12]
                if uid in found: continue
                inv = investment(title + " " + desc)
                status = "HOT" if sc >= 90 else ("WATCH" if sc >= 75 else "EARLY SIGNAL")
                if "Deutschland" in q or "Deutsch" in q:
                    country = "DE"
                    location = "Germany / verify"
                elif "Polska" in q or "Poland" in q:
                    country = "PL"
                    location = "Poland / verify"
                elif "België" in q or "Belgium" in q:
                    country = "BE"
                    location = "Belgium / verify"
                else:
                    country = "NL"
                    location = "Netherlands / verify"

                found[uid] = {
    "id": uid, "title": title, "company": "Nog te bepalen",
    "location": location, "country": country, "sector": "Food industry",
    "phase": "Signaal / te verifiëren", "investment_eur": inv,
    "score": sc, "status": status, "coating_potential": potential(inv, sc),
    "source": "Google News", "url": link, "published": pub,
    "notes": "Automatisch gevonden signaal. Bedrijf, locatie en projectfase moeten nog worden gevalideerd."
}
        except Exception as e:
            print("Feed error:", q, e)

    # Keep curated records first, then add only new signals.
    additions = [p for uid,p in found.items() if uid not in existing]
    db["projects"].extend(additions[:30])
    db["projects"].sort(key=lambda x: x.get("score",0), reverse=True)
    db["updated"] = datetime.now(timezone.utc).isoformat()
    DATA.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TCMRadar updated: {len(additions)} new signals; {len(db['projects'])} total projects.")

if __name__ == "__main__":
    main()
