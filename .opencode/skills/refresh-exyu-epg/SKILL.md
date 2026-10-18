---
name: refresh-exyu-epg
description: Refresh the ex-YU IPTV playlist (exyu.m3u) and its filtered XMLTV guide (epg.xml) from the provider playlist and the iptv-epg.org source. Use when the user asks to refresh, regenerate, or update the EPG / m3u / EPG mapping, or when tv_channels_*.m3u or the epg-irnhwjikgu.xml source has changed.
---

# Refresh the ex-YU playlist and EPG

This skill rebuilds two files that must stay in sync:

- `exyu.m3u` — filtered playlist (Croatian, Bosnian, Serbian and EXYU channels +
  British/US sports). **Gitignored** (`*.m3u`), never committed.
- `epg.xml` — XMLTV guide filtered to the playlist's channels, with channel
  names rewritten to match the playlist exactly. **Committed** to git.

## Sources

- Full playlist: the provider export `tv_channels_<TOKEN>.m3u` (e.g.
  `tv_channels_KYNCY9BEJBWJ.m3u`) in the repo root. It is gitignored; if it is
  missing, ask the user to download the current export from the IPTV provider.
- EPG: `https://iptv-epg.org/files/epg-irnhwjikgu.xml` (~670 MB, ~14.6k
  channels, 1.4M programmes).

## Steps

```bash
# 1. Rebuild the playlist (only needed if the provider export changed)
python3 .opencode/skills/refresh-exyu-epg/scripts/build_playlist.py \
    --source tv_channels_KYNCY9BEJBWJ.m3u --out exyu.m3u

# 2. Rebuild the EPG (downloads the source itself if given a URL)
python3 .opencode/skills/refresh-exyu-epg/scripts/generate_epg.py \
    --epg https://iptv-epg.org/files/epg-irnhwjikgu.xml \
    --m3u exyu.m3u --out epg.xml --report /tmp/unmatched.tsv
```

`--report` writes the unmatched `group<TAB>name` list — review it to add new
`ALIAS` entries (see below). Step 2 prints channel/programme counts.

## Playlist groups (`build_playlist.py`)

Groups use Croatian names: `Hrvatska`, `Bosna i Hercegovina`, `Srbija` for the
`HR`/`BIH`/`RS` provider prefixes; EXYU channels are split into `Sport`,
`Dokumentarci`, `Vijesti`, `Muzika`, `Filmovi`, `Serije`, `Dječiji`, `Ostalo`;
British/US sports go to `Sport - Strano`.

Provider prefix notes: Bosnia is `BIH`; `BH` is **Bahrain**; `SLO` (Slovenia) is
excluded.

## EPG mapping rules (`generate_epg.py`)

- Only channels present in `exyu.m3u` are written.
- The channel `id` and `display-name` are set to the exact playlist name, so the
  country prefix in the EPG source is effectively removed and the playlist and
  EPG match by name.
- Names are matched after normalization: unescape entities, transliterate
  diacritics (`č ć š ž đ`), uppercase, drop quality tags (`HD/FHD/4K/SD/UHD`),
  drop a trailing country tag (`- HR`, `- SR`, `- BH`, ...), then strip all
  non-alphanumerics.
- Country preference: `Hrvatska`→HR, `Bosna i Hercegovina`→BH, `Srbija`→RS,
  `Sport - Strano`→UK then US. EXYU channels try **RS first**, unless the
  playlist name ends in `HR` (then HR first); if RS has no match, HR/BH/UK/US
  are tried in order.
- An inline `ALIAS` dict maps playlist names that the EPG labels differently.
  Add entries there, e.g. `"CMC HD": "CMC-CroatianMusicChannel.hr"`. Verify the
  target id exists in the EPG before adding it.
- Only EPG ids that actually have programmes are emitted (channels with no
  programmes are dropped).

## Verify before committing

```bash
python3 - <<'EOF'
import xml.etree.ElementTree as ET
r = ET.parse('epg.xml').getroot()
ch = {c.get('id') for c in r.findall('channel')}
ps = r.findall('programme')
print(len(ch), 'channels', len(ps), 'programmes')
print('unknown channel refs:', len({p.get('channel') for p in ps} - ch))
EOF
```

Expect ~370 channels, ~48k programmes, and 0 unknown channel references. If the
source EPG gains/loses channels the counts will drift — that is fine.

## Gotchas

- The EPG is large; parsing twice takes a few seconds and ~700 MB of reads.
  Prefer a local copy over re-downloading while iterating.
- The `.gitignore` ignores `*.m3u`/`*.m3u8`, so `exyu.m3u` is never committed;
  only `epg.xml` is. Commit `epg.xml` after a refresh and tell the user to push.
- The git remote is `radovcicmarko/marko-custom-epg`; the environment's git
  credentials may belong to a different account, in which case `git push` fails
  with 403. Report this rather than changing the remote.
- Skills are loaded at startup: restart opencode after editing this skill.
