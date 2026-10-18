#!/usr/bin/env python3
"""Build the ex-YU playlist (exyu.m3u) from a full IPTV playlist export.

Keeps only Croatian (HR), Bosnian (BIH), Serbian (RS) and EXYU channels,
classifies the EXYU channels into Croatian-named groups, and pulls British
(UK) and US sports channels into the "Sport - Strano" group.

Usage:
    python3 build_playlist.py --source tv_channels_XXXX.m3u --out exyu.m3u
"""
import argparse
import collections
import re

TARGET = {"HR", "BIH", "RS", "EXYU"}
COUNTRY_GROUP = {"HR": "Hrvatska", "BIH": "Bosna i Hercegovina", "RS": "Srbija"}

# Note: the provider's "BH" prefix is Bahrain, not Bosnia; Bosnia is "BIH".
SPORTS_PAT = re.compile(
    r"(sport|espn|nba|nfl|mlb|nhl|ncaa|ufc|wwe|dazn|euro ?sport|sky ?sport|tnt ?sport|"
    r"premier sport|racing|la liga|\blfc\b|mutv|celtic tv|rangers|hibs|box nation|pdc darts|"
    r"national league|spfl|matchroom|\bppv\b|at the races|horse and country|betfred|coral tv|"
    r"ladbrokes|tennis|golf|be ?in|willow|cricket|supersport|spectrum sport|fanduel|\bflo\b|"
    r"speed sport|sportsman|tyc sport|monumental|altitude|fubo|ginx esports|fox soccer|"
    r"nbc sports|cbs sports|at&t sportsnet|sportsnet|sports grid|next level)", re.I)

ORDER = ["Hrvatska", "Bosna i Hercegovina", "Srbija", "Sport", "Sport - Strano",
         "Dokumentarci", "Vijesti", "Muzika", "Filmovi", "Serije", "Dječiji", "Ostalo"]


def cat_exyu(name):
    n = name.lower()
    if re.search(r"s\d+ ?e\d+", n) or "serij" in n:
        return "Serije"
    if re.search(r"[- ]\s*(19|20)\d{2}\s*$", name):
        return "Filmovi"
    kw = [
        ("Sport", ["sport", "arena", "eurosport", "fight", "zvezda", "partizan",
                   "premier liga", "sportska", "max sport", "nova sport", "sos"]),
        ("Vijesti", ["info", "news", "n1 ", "al jazeera", "tanjug", "kurir", "blic",
                     "informer", "city tv", "tv istok", "sandzak tv", "novi pazar",
                     "bnv", "rtv bor", "cgtn", "euronews", "cnn"]),
        ("Dječiji", ["kids", "nick", "minimax", "pikaboo", "toon", "disney", "baby",
                     "kockica", "tom & jerry", "masa i medo", "pepa prase", "hayatovci",
                     "tnt", "duck tv", "cartoon", "mini tv", "pedia"]),
        ("Muzika", ["music", "muzika", "muzick", "mtv", "grand", "folk", "sevdah",
                    "jugoton", "cmc", "bravo", "dm sat", "yu planet", "kafanska",
                    "glas drine", "duga", "balkanika", "izvorna", "hits", "n roll",
                    "koncert", "zabava", "bn music"]),
        ("Dokumentarci", ["discovery", "geographic", "nat geo", "history", "viasat",
                          "travel", "animal planet", "tlc", "docu", "doku", "crime investigation",
                          "da vinci", "food network", "kitchen", "lov i ribolov", "agro",
                          "dokubox", "e!"]),
        ("Filmovi", ["hbo", "cinestar", "cinemax", "kino", "film", "fox", "axn",
                     "sci-fi", "star tv", "tv 1000", "m1 ", "klasik", "filmbox",
                     "buena", "maxcro", "cinema", "epic drama", "super star", "o kanal",
                     "movies", "classic", "premium", "action", "comedy", "romance",
                     "thriller", "horror", "western", "crime", "mystery"]),
    ]
    for group, keys in kw:
        for k in keys:
            if k in n:
                return group
    if re.search(r"\bidj\b", n) or "kursadzije" in n or "specijal" in n or "soap" in n:
        return "Serije"
    return "Ostalo"


def build(source, out):
    entries = collections.defaultdict(list)
    with open(source, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"#EXTINF:-1,([A-Za-z0-9]+) \u2605 (.*)$", lines[i])
        if m:
            prefix, name = m.group(1), m.group(2)
            url = lines[i + 1] if i + 1 < len(lines) else ""
            if prefix in TARGET:
                group = COUNTRY_GROUP.get(prefix) or cat_exyu(name)
                entries[group].append((name, url))
            elif prefix in ("UK", "Uk", "US") and SPORTS_PAT.search(name):
                entries["Sport - Strano"].append((name, url))
            i += 2
        else:
            i += 1

    with open(out, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        total = 0
        for g in ORDER:
            for name, url in entries[g]:
                f.write(f'#EXTINF:-1 group-title="{g}",{name}\n{url}\n')
                total += 1
    for g in ORDER:
        print(f"{g:22} {len(entries[g])}")
    print("TOTAL", total)
    print("written", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="full provider playlist .m3u")
    ap.add_argument("--out", default="exyu.m3u")
    a = ap.parse_args()
    build(a.source, a.out)
