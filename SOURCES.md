# Data Sources — billboard-hot100

Source standards are **tiered**:
- **Serious tier** (methodology invites scrutiny): use official government or
  authoritative primary sources only. Crowd-edited references (Wikipedia, etc.)
  are NOT used — credibility is the product.
- **Fun tier** (low-stakes pop-culture): crowd-sourced references (fan wikis,
  SuperSummary, etc.) and owner-as-primary (hand-collected counts from a book or
  broadcast) are fine — just cite them plainly below.

Document every data source here before ingesting it. Include enough detail
that someone else could independently locate and verify the original data.

---

## Source Template

Copy and fill in for each source. The **How the source collects the data**,
**How the source defines the data**, and **Methodology changes / series breaks**
sections are required — they are what keep our analysis honest and prevent
apples-to-oranges comparisons. Do not leave them blank; if something is genuinely
not applicable or unknown, write "N/A" or "unknown" so it's clear it was considered.

### [Source Name]
- **Publisher:** [Agency, organization, or author]
- **URL:** [Direct link to the file or page]
- **Format:** [CSV | JSON | HTML table | ZIP | PDF | hand-curated]
- **License:** [Public domain | CC0 | CC-BY | proprietary | etc.]
- **Fields used:** [Column names or description of what was extracted]
- **Coverage:** [Geographic scope, date range, or other relevant bounds]
- **How the source collects the data:** [How does the publisher actually gather it?
  Survey / administrative records / registration / model estimate / scraped, etc.
  For surveys: sampling frame, sample size, response rate. For counts: the universe
  and denominator. Who is included and who is excluded from the raw collection?]
- **How the source defines the data:** [How is the thing being measured *defined*?
  Spell out the judgment calls in what counts. Example: a "COVID death" can mean died
  *from* COVID (underlying cause) vs. died *with* COVID (contributing/any mention) —
  very different counts. Note the exact definition this source uses.]
- **Methodology changes / series breaks:** [Dates when the definition or collection
  method changed, and which time periods are therefore NOT directly comparable.
  If the whole series is consistent, say so explicitly. This is the flag that stops
  us from charting a pre-change number next to a post-change number as if they match.]
- **Known controversies / debates:** [Any contested measurement choices worth a
  footnote or caveat in a published chart. Optional but encouraged. "None known" is
  a valid answer once you've checked.]
- **Notes:** [Anything else — data-quality quirks, suppression rules, imputation, etc.]
- **Retrieved:** [YYYY-MM-DD]

---

## Sources

**Tier: fun** (pop-culture music). Crowd-sourced genre tags (MusicBrainz) are
acceptable for this tier and cited plainly below.

### Billboard Hot 100 full chart history
- **Publisher:** `mhollingshead/billboard-hot-100` (GitHub) — a daily-updated crawl
  of Billboard.com's Hot 100. Underlying chart © Billboard.
- **URL:** https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/all.json
- **Format:** JSON array (~44 MB), one object per weekly chart.
- **License:** Public GitHub data; underlying chart © Billboard — used for
  non-commercial research only.
- **Fields used:** `date`; and per chart row `song`, `artist`, `this_week` (rank that
  week), `last_week`, `peak_position`, `weeks_on_chart`.
- **Coverage:** every weekly Hot 100 chart, 1958-08-04 → present (3,559 charts /
  355,887 chart appearances at retrieval).
- **How the source collects the data:** scraped/crawled from Billboard.com's published
  Hot 100 and serialized to one JSON array. We land it verbatim and only flatten the
  nested weekly `data` lists into long rows (one row per date × song × artist).
- **How the source defines the data:** "chart presence" = a song appearing in that
  week's Hot 100 at the given rank. `this_week` is the rank that week (1 = top);
  `peak_position` and `weeks_on_chart` are Billboard's running fields.
- **Methodology changes / series breaks:** Billboard's Hot 100 ranking methodology
  shifted over the decades — historically sales + radio airplay; **digital downloads**
  incorporated from ~2005; **online streaming** from ~2007 and progressively weighted
  through the 2010s (on-demand / YouTube-era revisions). Chart presence is therefore
  **not measured the same way across eras**; any genre-over-time comparison must carry
  this caveat.
- **Known controversies / debates:** periodic debate over streaming/airplay weighting
  and chart-rule changes (e.g. bundle/streaming-count adjustments). Not load-bearing
  for a genre-share view, but noted.
- **Notes:** `last_week` is null for a song's first chart week. Raw file cached to
  `data/raw/hot100_all.json`.
- **Retrieved:** 2026-10-14

### MusicBrainz artist tags (genre enrichment)
- **Publisher:** MusicBrainz (keyless Web Service v2).
- **URL:** https://musicbrainz.org/ws/2/artist (query `artist:"<name>"&fmt=json&limit=1`)
- **Format:** JSON per-artist lookup.
- **License:** MusicBrainz data under CC0 / CC-BY-NC-SA; see
  https://musicbrainz.org/doc/About/Data_License
- **Fields used:** per artist — `id` (MB artist id), `name` (MB canonical name), and the
  full `tags` list (each `name` + `count`). Stored RAW as a JSON string.
- **Coverage:** artists with **≥ 20 Hot 100 appearances** (~4,427 artists, ~85% of all
  chart appearances). Billboard carries no genre, so this is the only genre signal.
- **How the source collects the data:** community-contributed tags on the MusicBrainz
  open music encyclopedia. We take the **top artist match** per Billboard-spelling name.
- **How the source defines the data:** a "tag" is a free-text label editors attach to an
  artist (e.g. `pop`, `country`, `synth-pop`), with a `count` = how many editors applied
  it. Tags are **artist-level and whole-catalog**, not per-song or point-in-time. They
  are intentionally stored raw and messy here; bucketing to aggregate genres is `02-clean`.
- **Methodology changes / series breaks:** crowd-sourced tags change as editors add/remove
  them; a genre assigned to an artist's early-career Hot 100 hit is approximate (reflects
  the artist's whole career as currently tagged). Only artists above the appearance
  threshold are enriched — lower-appearance artists are left ungenred (treated as
  Other/unknown downstream). This is a deliberate ingest-scope decision, not a data gap in
  the source.
- **Known controversies / debates:** tag quality varies by artist popularity; obscure
  artists may have few or no tags. Fun-tier crowd source — acceptable and cited plainly.
- **Notes:** descriptive `User-Agent` required (else 403); rate-limited to ~1 req/sec
  (1.1s used, with backoff). Every lookup cached to `data/raw/mb_artist_cache.jsonl`
  (resumable). Unmatched artists kept with `matched=false` + empty tags.
- **Retrieved:** 2026-10-14

---

## Notes on Data Quality

- All source files are saved verbatim to `data/raw/` and never modified.
- Discrepancies between sources should be noted here and resolved explicitly.
- **Series breaks:** whenever a source changed its definition or method mid-series,
  document the break date under that source and treat pre/post as separate series —
  never chart or aggregate across a break without a visible caveat.
- **Definitions drive comparisons:** before comparing two numbers (across years,
  places, or sources), confirm they are defined the same way. If not, say so in the
  chart, the codebook, and any social copy.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT * FROM _sources;
```
