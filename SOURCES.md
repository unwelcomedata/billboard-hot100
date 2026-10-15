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
  Hot 100 and serialized to one JSON array. It is taken verbatim and only flattened — the
  nested weekly lists become long rows (one row per date × song × artist).
- **How the source defines the data:** "chart presence" = a song appearing in that
  week's Hot 100 at the given rank. `this_week` is the rank that week (1 = top);
  `peak_position` and `weeks_on_chart` are Billboard's running fields.
- **How the source defines the data (ranking inputs):** the Hot 100 ranks a song on a
  **blended** metric — physical/digital **sales + radio airplay + online streaming
  combined**. The weights of those three inputs have changed over time (see the series
  break below), so "chart presence" is a moving measure, not a fixed one.
- **Methodology changes / series breaks:** Billboard's Hot 100 ranking methodology
  shifted over the decades — historically sales + radio airplay; **digital downloads**
  incorporated from ~2005; **online streaming** from ~2007. The load-bearing break for a
  genre-over-time read is **2013: on-demand streaming was folded directly into the Hot 100
  formula** (YouTube video streams added that year), and the streaming/video weighting +
  bundle rules shifted again **~2018–2020** (paid vs ad-supported stream weighting, the
  2020 end of merchandise/ticket bundles counting as sales). Chart presence is therefore
  **not measured the same way across eras.** Interpretive consequence for this project:
  the post-2013 surge of **Hip-Hop/Rap and Pop** (and the rise of long-running streaming-era
  hits) is **partly real listening and partly an artifact of streaming favoring those
  genres and rewarding long chart runs** — so cross-era genre comparisons, and the
  pre-/post-2013 "longest-charting songs" split, carry this caveat. The 2013 break is
  annotated directly on the year-axis charts (a dashed "2013: streaming added" marker) and
  the pre-/post-song charts carry a short streaming-ramp caveat line; the categorical
  decade share chart notes it in its subtitle.
- **Known controversies / debates:** ongoing debate over streaming/airplay weighting and
  chart-rule changes (e.g. the 2013 streaming inclusion, the 2018–2020 video/bundle
  adjustments). Load-bearing here: the streaming era both reshaped the genre mix and let
  songs stay on the chart far longer (pre-2013 max ~87 weeks vs ~112 in the streaming era).
- **Notes:** `last_week` is null for a song's first chart week. The full raw JSON is
  retained verbatim.
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
  open music encyclopedia. We take the **top artist match** per Billboard credit.
- **How the source defines the data:** a "tag" is a free-text label editors attach to an
  artist (e.g. `pop`, `country`, `synth-pop`), with a `count` = how many editors applied
  it. Tags are **artist-level and whole-catalog**, not per-song or point-in-time. They
  are retained raw and messy as collected; a separate cleaning pass buckets them to the
  twelve aggregate genres (top-tag-wins).
- **Artist-name normalization (matching method, documented):** Billboard credit strings
  carry featuring / backing-band / collaboration formatting ("Elvis Presley With The
  Jordanaires", "Prince And The Revolution", "Drake & 21 Savage", "Paul McCartney And
  Wings") that does not match a MusicBrainz **canonical** artist name, so a first pass
  querying the raw credit with an exact-quoted search left ~1,281 of 4,427 artists
  unmatched. A normalization step derives the
  **primary artist** for lookup: it cuts featuring/with/duet/vs credits, strips
  orchestra/session-band and parenthetical tails, and splits a true co-bill to the FIRST
  (primary) artist — while deliberately KEEPING Motown-style "<Lead> & The <Group>" names
  whole ("Diana Ross & The Supremes", "Martha & The Vandellas"). For a genuine two-artist
  co-bill ("Drake & 21 Savage") taking the primary ("Drake") is a conscious choice for an
  **artist-level** genre. The unmatched set is then re-queried with the normalized name and
  a **forgiving (unquoted) Lucene query** that returns a score-ranked match. A small
  **curated alias map** handles stubborn names cleaning alone
  can't fix (e.g. `Daryl Hall John Oates`→`Daryl Hall & John Oates`, `'N Sync`→`*NSYNC`,
  `Jackson 5`→`The Jackson 5`, `The 4 Seasons`→`The Four Seasons`, `Dixie Chicks`→`The
  Chicks`); each alias was verified to resolve to the intended artist on MB before adding.
  Records stay keyed by the **original Billboard spelling** (so the downstream join is
  unaffected) and record the normalized `query_name` for auditability.
- **Methodology changes / series breaks:** crowd-sourced tags change as editors add/remove
  them; a genre assigned to an artist's early-career Hot 100 hit is approximate (reflects
  the artist's whole career as currently tagged). Only artists above the appearance
  threshold are enriched — lower-appearance artists are left ungenred (treated as
  Other/Unknown downstream). This is a deliberate ingest-scope decision, not a data gap in
  the source.
- **Honest residual (Other/Unknown):** after name-normalization + the Latin/Metal buckets,
  the remaining Other/Unknown is dominated by the **genuine long tail of artists with
  < 20 Hot 100 appearances**, which are below the enrichment threshold and never queried.
  This tail is left as honest Other/Unknown rather than chased — it is the lowest-value,
  hardest-to-recover slice, and the chart carries the disclosure. A smaller residual is
  artists MusicBrainz matched but whose tags carry no usable genre signal.
- **Known controversies / debates:** tag quality varies by artist popularity; obscure
  artists may have few or no tags. Fun-tier crowd source — acceptable and cited plainly.
- **Notes:** descriptive `User-Agent` required (else 403); rate-limited to ~1 req/sec
  (1.1–1.3s used, with backoff on 503/429). Every lookup is cached (resumable); the
  unmatched set was re-queried into the same cache. Unmatched artists kept with empty tags.
- **Retrieved:** 2026-10-14 (unmatched re-queried with normalized names 2026-10-14)

---

## Notes on Data Quality

- All source files are retained verbatim as downloaded and never modified.
- Discrepancies between sources should be noted here and resolved explicitly.
- **Series breaks:** whenever a source changed its definition or method mid-series,
  document the break date under that source and treat pre/post as separate series —
  never chart or aggregate across a break without a visible caveat.
- **Definitions drive comparisons:** before comparing two numbers (across years,
  places, or sources), confirm they are defined the same way. If not, say so in the
  chart, the codebook, and any social copy.
