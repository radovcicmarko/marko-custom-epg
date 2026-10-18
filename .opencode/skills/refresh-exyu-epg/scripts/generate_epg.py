#!/usr/bin/env python3
"""Filter an IPTV-EPG XMLTV file down to the channels in exyu.m3u and rename
each channel to match the playlist exactly.

Rules:
  * Only channels present in the playlist are written.
  * The country prefix on the EPG display-name (HR/RS/BH/US/UK/...) is removed
    by using the playlist name verbatim as the channel id and display-name, so
    the playlist and EPG match by name.
  * EXYU channels map to the RS entry first, unless the playlist name ends in
    "HR" (then HR first); if not found, other countries are tried.
  * A curated ALIAS table covers cases where the EPG uses a different name
    (e.g. "CMC HD" -> "CMC - Croatian Music Channel", "BHT HD" -> "BHT 1").

Usage:
    python3 generate_epg.py --epg /path/epg-source.xml --m3u exyu.m3u --out epg.xml
    python3 generate_epg.py --epg https://iptv-epg.org/files/epg-irnhwjikgu.xml \
        --m3u exyu.m3u --out epg.xml
"""
import argparse
import collections
import html
import os
import re
import sys
import unicodedata
import urllib.request
from xml.sax.saxutils import escape, quoteattr

# ---------- curated aliases (exact playlist name -> EPG channel id) ----------
ALIAS = {
    # HR
    "CMC HD": "CMC-CroatianMusicChannel.hr",
    "PLAVA VINKOVACKA TV": "PLAVAVinkovacka.hr",
    "TREND KARLOVAC HD": "TrendTV.hr",
    # BIH
    "BHT HD": "BHT1.bh",
    "FEDERALNA TV [ FTV ]": "FTV.bh",
    "NOVA BH HD": "NovaBH.bh",
    "AL JAZEERA BALKAN HD": "ALJazeeraBalkans.bh",
    "N1 BOSNA": "N1.bh",
    "BN 1 HD": "BN.bh",
    "ARENA PREMIUM 1 HD": "ArenaSportPremium1.bh",
    "ARENA PREMIUM 2 HD": "ArenaSportPremium2.bh",
    "ARENA PREMIUM 3 HD": "ArenaSportPremium3.bh",
    # RS
    "N1 SRBIJA": "N1.rs",
    "NOVA M": "NovaM.bh",
    "NOVI PAZAR": "RTVNoviPazar.rs",
    "PALMA PLUS": "TVPalmaplus.rs",
    "KCN 1": "TVK::CN1.rs",
    "BELLE AMIE": "TVBelleAmie.rs",
    # EXYU
    "KCN 3 HD": "TVK::CNSvetPlus3.rs",
    # Dokumentarci
    "DISCOVERY": "DiscoveryChannel.rs",
    "DISCOVERY HD": "DiscoveryChannel.rs",
    "DISCOVERY ID": "IDXtra.rs",
    "DISCOVERY ID XTRA  HD": "IDXtra.rs",
    "E!": "EEntertainment.rs",
    "VIASAT EXPLORER": "ViasatExplore.rs",
    "AGRO HD": "AgroTV.rs",
    # Muzika
    "HAYAT  MUSIC": "HayatMusicBox.bh",
    "HAYAT  FOLK": "HayatFolkBox.bh",
    "BALKANIKA TV": "Balkanika.hr",
    "CMC MUSIC": "CMC.bh",
    "IDJ MUSIC": "IDJTV.rs",
    "PINK N ROLL": "PinkAndRoll.bh",
    # Sport - Strano (UK)
    "SKY SPORTS F1 RACING HD": "SkySportsF1.uk",
    "SKY SPORTS F1 RACING SD": "SkySportsF1.uk",
    "SKY SPORT MIX FHD": "SkySportsMix.uk",
    "SKY SPORT MIX SD": "SkySportsMix.uk",
    "SKY SPORTS MIX HD": "SkySportsMix.uk",
    "SKY SPORTS PLUS FHD": "SkySportsPlus.uk",
    "SKY SPORTS PLUS HD": "SkySportsPlus.uk",
    "LFC FHD": "LFCTV.uk",
    "LFC TV SD": "LFCTV.uk",
    "LA LIGA FHD": "LaLigaTV.uk",
    "LA LIGA HD": "LaLigaTV.uk",
    "LA LIGA SD": "LaLigaTV.uk",
    "RACING UK FHD": "RacingTV.uk",
    " RACING UK FHD": "RacingTV.uk",
    " RACING UK HD": "RacingTV.uk",
    " RACING UK SD": "RacingTV.uk",
    "EUROSPORT 1 SD": "UKEurosport1.uk",
    "EUROSPORT 2 SD": "UKEurosport2.uk",
    "HORSE AND COUNTRY SD": "HorseAndCountry.uk",
    " HORSE AND COUNTRY": "HorseAndCountry.uk",
    " PDC DARTS 1  - LIVE EVENTS ONLY": "PDC1.uk",
    " PDC DARTS 2  - LIVE EVENTS ONLY": "PDC2.uk",
    # Sport - Strano (US)
    "BEIN SPORTS HD": "beINSports.us",
    "WILLOW CRICKET HD": "WillowSports.us",
    "CHICAGO SPORTS NETWORK HD (CHSN) HD": "ChicagoSportsNetwork.us",
}


def strip_prefix(name):
    m = re.match(r'^([A-Z]{2}) - (.*)$', name)
    return (m.group(1), m.group(2)) if m else (None, name)


def norm(s):
    s = html.unescape(s)
    s = s.replace('đ', 'd').replace('Đ', 'D').replace('ß', 'ss')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r'\b(FHD|UHD|4K|SD|HD)\b', '', s)
    s = re.sub(r'[-–—\s]*\b(HR|SR|BH|BIH|BA|MNE|SLO)\b\s*$', '', s)
    s = re.sub(r'[^A-Z0-9]+', '', s)
    return s


def prefs(group, name):
    if group == "Hrvatska":
        return ["HR"]
    if group == "Bosna i Hercegovina":
        return ["BH"]
    if group == "Srbija":
        return ["RS"]
    if group == "Sport - Strano":
        return ["UK", "US"]
    n = name.upper()
    if re.search(r'\bHR\s*$', n):
        return ["HR", "RS", "BH"]
    if re.search(r'\b(SR|RS)\s*$', n):
        return ["RS", "HR", "BH"]
    if re.search(r'\b(BH|BIH)\s*$', n):
        return ["BH", "RS", "HR"]
    return ["RS", "HR", "BH", "UK", "US"]


def fetch(epg):
    if epg.startswith("http://") or epg.startswith("https://"):
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "epg-source.xml")
        print("downloading", epg, "->", local, file=sys.stderr)
        urllib.request.urlretrieve(epg, local)
        return local
    return epg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epg", required=True, help="source XMLTV path or URL")
    ap.add_argument("--m3u", default="exyu.m3u")
    ap.add_argument("--out", default="epg.xml")
    ap.add_argument("--report", help="optional path to write unmatched channels")
    args = ap.parse_args()

    src = fetch(args.epg)

    # ---------- load EPG channels (header section only) ----------
    epg_names = collections.defaultdict(list)
    epg_icon = {}
    _cid = None
    with open(src, encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if s.startswith('<programme '):
                break
            if s.startswith('<channel id='):
                _cid = s.split('id="', 1)[1].split('"', 1)[0]
            elif s.startswith('<display-name>') and _cid is not None:
                epg_names[_cid].append(s[len('<display-name>'):].split('</display-name>', 1)[0])
            elif s.startswith('<icon src=') and _cid is not None and _cid not in epg_icon:
                epg_icon[_cid] = s.split('src="', 1)[1].split('"', 1)[0]

    index = collections.defaultdict(lambda: collections.defaultdict(list))
    for cid, names in epg_names.items():
        for nm in names:
            p, base = strip_prefix(nm)
            if p:
                index[p][norm(base)].append(cid)

    # ---------- load playlist channels ----------
    m3u = []
    seen = set()
    with open(args.m3u, encoding='utf-8') as f:
        for line in f:
            m = re.match(r'#EXTINF:-1 group-title="([^"]+)",(.*)', line.rstrip('\n'))
            if not m:
                continue
            g, name = m.group(1), m.group(2)
            if name in seen:
                continue
            seen.add(name)
            m3u.append((g, name))

    name2id = {}
    unmatched = []
    for g, name in m3u:
        eid = ALIAS.get(name)
        if not eid:
            n = norm(name)
            for p in prefs(g, name):
                if n in index[p]:
                    eid = index[p][n][0]
                    break
        if eid:
            name2id[name] = eid
        else:
            unmatched.append((g, name))

    # ---------- keep only EPG ids that actually have programmes ----------
    available = set()
    chpat = re.compile(r'<programme [^>]*channel="([^"]+)"')
    with open(src, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('  <programme '):
                m = chpat.search(line)
                if m:
                    available.add(m.group(1))
    name2id = {n: i for n, i in name2id.items() if i in available}
    id2names = collections.defaultdict(list)
    for n, i in name2id.items():
        id2names[i].append(n)

    # ---------- write output ----------
    tvline = None
    with open(src, encoding='utf-8') as f:
        for line in f:
            if line.lstrip().startswith('<tv '):
                tvline = line.rstrip('\n')
                break

    written = 0
    chpat2 = re.compile(r'^(\s*<programme [^>]*channel=")([^"]+)(".*)$')
    with open(args.out, 'w', encoding='utf-8') as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write((tvline or '<tv>') + '\n')
        for name, eid in name2id.items():
            out.write('  <channel id=%s>\n' % quoteattr(name))
            out.write('    <display-name>%s</display-name>\n' % escape(name))
            if epg_icon.get(eid):
                out.write('    <icon src=%s/>\n' % quoteattr(epg_icon[eid]))
            out.write('  </channel>\n')

        buf = None
        with open(src, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('  <programme '):
                    buf = [line]
                elif buf is not None:
                    buf.append(line)
                    if line.strip().startswith('</programme>'):
                        m = chpat2.match(buf[0].rstrip('\n'))
                        eid = m.group(2)
                        if eid in id2names:
                            for on in id2names[eid]:
                                out.write(m.group(1) + escape(on, {'"': '&quot;'}) + m.group(3) + '\n')
                                for b in buf[1:]:
                                    out.write(b)
                                written += 1
                        buf = None
        out.write('</tv>\n')

    print("playlist channels:", len(m3u))
    print("matched channels:", len(name2id))
    print("distinct epg ids mapped:", len(id2names))
    print("programme entries written:", written)
    print("written", args.out)

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as u:
            for g, n in unmatched:
                u.write(g + '\t' + n + '\n')


if __name__ == "__main__":
    main()
