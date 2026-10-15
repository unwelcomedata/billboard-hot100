# billboard-hot100 — Dataset Codebook
Generated: 2026-10-15

## Columns

### `song`
- **Type**: `str`
- **Non-null**: 10 / 10 (100.0%)
- **Description**: Song title as credited on the Billboard Hot 100.

### `artist`
- **Type**: `str`
- **Non-null**: 10 / 10 (100.0%)
- **Description**: Artist as credited on the Hot 100 (the genre join key).

### `genre`
- **Type**: `str`
- **Non-null**: 10 / 10 (100.0%)
- **Description**: Aggregate genre of the credited artist (top-tag-wins via MusicBrainz; see the main dataset codebook). Null -> Other/Unknown.

### `weeks`
- **Type**: `int32`
- **Non-null**: 10 / 10 (100.0%)
- **Description**: The song's total weeks on the Hot 100 (MAX weeks_on_chart across its run).

## Notes

Top 10 Hot 100 songs by total weeks on chart whose FIRST chart year is 1958-2012 (pre-streaming era). Era = MIN(year) for the (song, artist). CAVEAT: the streaming ramp bled into 2008-2012, so this top is dominated by 2008-2012 songs + perennial Christmas songs. See SOURCES.md (2013 streaming break). PII: none.
