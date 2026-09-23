# IMPACT to FReSH transformation

Converts source study records (IMPACT/API export XML, one file per language per
study) into FReSH-schema XML, validated against `mappings/fresh-schema_v6.xsd`.

## 1. Requirements

A Python environment with:

- `lxml`
- `pandas`
- `xmlschema` (needs XSD 1.1 support — the schema uses Conditional Type
  Assignment for bilingual FR/EN validation; tested with 4.x)
- `requests` (only needed for the download notebook, see below)

```bash
pip install lxml pandas xmlschema requests
```

(or install the same packages into a conda env — any recent Python 3 works,
no specific version pinning required).

## 2. Get the source data

The pipeline reads from `data/input/`. This folder is not versioned (each
study file is in `.gitignore`), so it needs to be populated before running
anything.

**Option A — manually**: drop the source XML files directly into
`data/input/`. Each study needs its own file, named `<idno>.xml`
(e.g. `FRESH-PEF100-fr.xml`); the pipeline pairs the `-fr`/`-en` variants of
the same study by this filename suffix, not by the `<id>` inside the XML.

**Option B — `download_files_from_FReSH_API.ipynb`**: fetches source files
directly from the FReSH API.

- **All studies**: run the notebook's first cells in order — they call the
  catalog search endpoint, collect every study id, then loop over all of them
  and save each one to `data/input/<id>.xml`.
- **A specific subset**: skip straight to the "Get a fixed list of studies"
  cell near the bottom, fill in `ids_list` with just the ids you want
  (e.g. `['FRESH-PEF73274-en', 'FRESH-PEF8214-en']`), and run that cell —
  it downloads only those.

## 3. Run the pipeline

**Single study** (useful for debugging one file): `run_pipeline.py` — edit
`fresh_id`/`lang` near the bottom of the file, then run it.

**Batch, all studies or a chosen subset**: `run_pipeline_batch.py`. It takes
its paths on the command line and defaults to this repo's own folders, so a
fresh checkout runs as-is:

```bash
python run_pipeline_batch.py
python run_pipeline_batch.py --data-dir data/input --output-dir data/output --logs-dir data/logs
python run_pipeline_batch.py --study-ids 43597 PEF3476 PEF60139
```

Without `--study-ids` every study in `--data-dir` is processed, in both
languages. With it, only the studies whose id appears in the filename (bare
numeric or `PEF...`, matched case-insensitively) are — both their `-fr` and
`-en` files.

Each study's converted XML lands in the output folder, and three per-file
reports are written to the logs folder:

| file | what it holds |
|---|---|
| `<name>_validation_report.txt` | XSD-conformant, or the first error |
| `<name>_unmatched_vocab.csv` | values with no controlled-vocabulary match |
| `<name>_quality_report.csv` | what the pipeline had to repair for lack of anything better |

The batch run prints a final summary of how many studies succeeded vs failed.

## 4. Checking your work: the tools in `tests/`

None of these change the pipeline. They tell you what it currently does, so a
change shows up as an explicit list instead of a guess.

### `run_regression.py` — the safety net

Runs the pipeline on 21 real studies kept in `tests/fixtures/` and compares
every output against a frozen copy in `tests/expected/`.

```bash
python tests/run_regression.py            # compare, list the differences
python tests/run_regression.py --update   # (re)freeze the reference
python tests/run_regression.py --quick    # skip XSD validation, much faster
```

The reference is not "the correct output" — it is "the output as of the moment
you froze it". That is what makes it usable on a pipeline that still has
defects: you do not need the output to be right, only to know what moved. Run
it before and after any change to `builder.py`, `run_pipeline.py` or the
mapping; a change that reports `0 modifié` did not touch the conversion.

The 21 fixtures were picked by `select_fixtures.py`, which greedily covers 17
structural traits (parallel lists, multiple funders, third-party sources,
conditional branches…) so a small set exercises the branches that actually
break. The 13 studies that failed XSD validation were added on top, so the
reference carries their failure too — freezing a known failure is what tells
you the day it changes.

Note the reference is OS-independent: the pipeline writes its XML with an
explicit newline setting, so a reference frozen on Windows replays identically
on Linux and macOS. Verified across both.

### `audit_corpus.py` — the state of the whole catalogue

```bash
python tests/audit_corpus.py --data-dir data/input             # structure only
python tests/audit_corpus.py --data-dir data/input --validate  # + XSD conformity
```

Six sections: source structure, paired-list synchronisation, mapping rules that
never fire, XSD conformity with the failure reasons grouped, and the
controlled-vocabulary values that resolve to nothing.

Conformity is measured with `schema.validate()`, **not** `is_valid()`:
`is_valid()` validates in lax mode and accepts invented tags and broken element
order, which silently reports 100% on a corpus that is not conformant.

### `rapport_qualite.py` — what the source did not provide

```bash
python tests/rapport_qualite.py --data-dir data/input > rapport_qualite.txt
```

The pipeline produces conformant XML even when the source record is
incomplete: it invents the missing contributor, drops the nameless team member,
abandons the untyped third-party source. The output is then *valid*, and so
indistinguishable from a healthy record. This report is what makes the
difference visible — grouped by cause, with what happened, what curation can do
about it, and the studies concerned. It is written for curation, not for
developers.

### `inspect_field.py` — what a source field actually contains

```bash
python tests/inspect_field.py --data-dir data/input --xpath "/xml/dataset/..."
```

Lists the distinct values of one source XPath across the corpus, with counts.
Use it before assuming a mapping rule is dead: a rule that never fires because
the case does not occur is not the same thing as a rule looking in the wrong
place, and this is how you tell them apart.

### `detecter_listes_aplaties.py` — free-text fields that are really a closed list

```bash
python tests/detecter_listes_aplaties.py --data-dir data/input
```

A field with a controlled vocabulary comes out carrying its identifier; a plain
text field comes out carrying nothing, and so cannot be aligned to
HealthDCAT-AP — even when its content is, in practice, a term picked from a
dropdown. `PrimaryOutcomes` is the clearest case: free text on the FReSH side,
but only four distinct values across the test corpus.

The script separates them by repetition: real free text produces long, mostly
unique values; a flattened list produces short values that recur verbatim
between records. Booleans, dates, e-mails and identifiers are excluded. It
yields candidates to check, not a verdict — read its docstring for the
thresholds.

### `couverture_source.py` — source data the mapping never reads

```bash
python tests/couverture_source.py --data-dir data/input --exemples 3
```

The existing audit starts from the mapping table and asks whether each rule
finds something. That misses the costliest defect: a rule pointing to a wrong
but *existing* path looks alive, while the right source field is read by
nobody. This tool starts from the source record instead and asks, for every
populated field, whether any rule reads it.

It replays the four branches of `HierarchicalExtractor.process()` and collects
the *nodes* returned — not path strings, which would be wrong as soon as a rule
carries a predicate. Fields whose information leaves by another path
(duplicates, compared on normalised values), fields used as predicate criteria,
and placeholder values ("Non renseigné") are classified apart, so what remains
is data that genuinely never reaches FReSH. Its output is a list of candidates
for `docs/arbitrage_mapping.md`, not a verdict.

### The documents in `docs/`

None is a tool.

- `docs/arbitrage_mapping.md` — mapping defects found by `couverture_source.py`,
  each with its evidence, proposed fix, output impact and a decision box.
- `docs/journal_des_changements.md` — every commit that changes what the pipeline
  *produces*, with what a downstream consumer should check. Read before merging.
- `docs/arbitrage_vocabulaires.md` — the decision document for the ~1,900 values
  that resolve to no controlled-vocabulary term, sorted by what deciding costs
  rather than by volume. Addressed to whoever owns the vocabularies.
- `docs/pistes_ouvertes.md` — open leads, each stating what is measured, what is
  assumed, and the command that settles it. Read this first when picking the
  work back up.

## 5. How the pipeline works (for whoever takes this over)

The rest of this README covers *running* the pipeline. This section covers
what's actually inside it, written for someone who needs to debug or extend
it without having built it.

### The pipeline in one paragraph

For each source file, `run_transformation()` (bottom of `run_pipeline.py`)
does three things: **extract** the source XML into a nested Python dict
(`HierarchicalExtractor`, also in `run_pipeline.py`), **build** a FReSH-shaped
XML tree from that dict (`FReSHXMLBuilder`, in `src/builder.py`), then
**validate** the result against `mappings/fresh-schema_v6.xsd`
(`src/validator.py`). Two logs come out per input file regardless of outcome:
a validation report and an unmatched-controlled-vocabulary report (empty file
if nothing was unmatched).

### File-by-file map

**Live pipeline** (imported by `run_pipeline.py` / `run_pipeline_batch.py` —
if you're tracing a bug, it's in one of these):
- `run_pipeline.py` — `HierarchicalExtractor` (extraction) +
  `run_transformation()` (orchestrates extract → build → validate → write
  logs). Also runnable standalone for one study (edit `fresh_id`/`lang` at
  the bottom).
- `src/builder.py` — `FReSHXMLBuilder`: dict → XML, in strict XSD child
  order (`schema_hierarchy`), plus a long post-processing pass — see below.
- `src/validator.py` — thin wrapper around `xmlschema.XMLSchema11`.
- `src/vocabularies.py` — the controlled-vocabulary resolver, used by both
  of the above. See "Controlled-vocabulary resolution" below.
- `run_pipeline_batch.py` — batch driver, calls `run_transformation()` per
  file found in `data_dir`.
- `mappings/entity_wise_corres_table.csv` — the actual `source_xpath` →
  `target_xpath` table `HierarchicalExtractor` walks row by row. This file
  *is* the mapping; there's no mapping logic hardcoded in Python beyond
  interpreting its four row "modes" (see next section).
- `mappings/fresh-schema_v6.xsd` — current target schema.
- `mappings/vocabularies/*.csv` — 39 controlled-vocabulary tables
  (`prefLabel_fr`, `prefLabel_en`, `exactMatch`, `identifier`), one per
  FReSH field. These are the ground truth `resolve_vocab_term()` checks
  every value against.

**Checking tools** (never imported by the pipeline — they observe it, they
don't change it; see section 4 for how to use them):
- `tests/run_regression.py` — runs the 21 fixtures and diffs every output
  against the frozen reference in `tests/expected/`.
- `tests/select_fixtures.py` — how those fixtures were chosen (greedy cover
  of 17 structural traits).
- `tests/audit_corpus.py` — six-section audit of a whole corpus.
- `tests/rapport_qualite.py` — aggregates what the pipeline had to repair,
  for curation.
- `tests/inspect_field.py` — distinct values of one source XPath, with counts.
- `tests/detecter_listes_aplaties.py` — text fields that in fact carry a
  closed list.
- `tests/couverture_source.py` — populated source fields no mapping rule reads.

**Not live — leftover from an earlier, flatter version of the pipeline.**
Nothing in `run_pipeline*.py` or `src/builder.py` imports these; don't lose
time tracing into them:
- `src/extractor.py` (`APIExtractor`) and `src/mapper.py`
  (`load_mapping_table`) — only used by `old_scripts/run_pipeline_v0.py` and
  `old_scripts/run_pipeline_mock.py`, the non-hierarchical predecessor.
- `src/xml_utils.py` — not imported anywhere (not even the notebooks).
  Looks like ad hoc XPath-discovery tooling from when
  `entity_wise_corres_table.csv` was first being built by hand; even
  references a `FReSH-model/` folder that doesn't exist in the current
  layout.

**One-off / maintenance scripts:**
- `download_files_from_FReSH_API.ipynb` — pulls source XML straight from the
  live portal (`nada.portail-fresh.fr/index.php/api/catalog/...`).
- `get_CVs_from_fresh_technical_documentation_git.ipynb` — regenerates
  `mappings/vocabularies/*.csv` from SKOS `.ttl` files in the **sibling**
  `technical-documentation` repo (`../technical-documentation/docs/ttl/`,
  hardcoded absolute path in the notebook). This is a real cross-repo
  dependency: if the controlled vocabularies ever need updating, that repo
  has to exist alongside this one and be up to date first.
- `sync_xsd_vocabularies_cvidtype.py` — regenerates the XSD's enum/CTA
  blocks from whatever is currently in `mappings/vocabularies/*.csv`
  (v5 → v6). Its own docstring explains the two schema-history steps it
  replaced (`old_scripts/sync_xsd_vocabularies*.py`, v2→v3 and v3→v4) — read
  it before touching schema versioning again.

### The extract → build split, and why post-processing is so heavy

`HierarchicalExtractor.process()` isn't a flat XPath-to-XPath copy: the
mapping CSV has four row "modes" (`ABSOLUTE` source paths, `ROOT:`/`ARRAY:`
for repeatable nested groups, and `./`-relative rows for a group's own
fields) so it can reconstruct loops-within-loops (e.g. funding agencies,
each with its own PID list) into a nested dict. Every scalar value passes
through `_clean_value()` on the way in — bool coercion, date reformatting,
and controlled-vocabulary resolution all happen here, *before* the dict ever
reaches the builder.

`FReSHXMLBuilder` then does more than serialize the dict. A large chunk of
`_enforce_mandatory_dummy_nodes()` exists because the source API embeds
several fields as raw text that isn't really text: JSON blobs
(`CollectionModeRaw`, `SamplingModeRaw`, `IndividualDataAccessRaw`) and
Python-repr-style fake arrays (`DataTypeRaw`, `UsedStandardsRaw`,
`RecruitmentSourceRaw`, `ArmTypeRaw` fan-out for `ThirdPartySource`) that get
decoded and expanded into real repeated XSD elements here, each value
re-resolved against the controlled vocabulary again (some of these values
never pass through the extractor's own `_clean_value` at all, so this is the
*first* vocabulary check they get). This step also inserts XSD-mandatory
nodes the source doesn't always provide (e.g. `MetadataContributor`,
`OtherClusion`), drops junk the source produces incidentally (empty
`TeamMember` ghosts from `"firstname;lastname"` fields that are both blank,
empty `OrganisationPID`s), and — last, so it overrides anything set earlier —
injects the ground-truth `exactMatch` URI next to every resolved `<value>`
via `_inject_vocab_uris()`.

### Controlled-vocabulary resolution

This is the mechanism behind every `*_unmatched_vocab.csv` log file. In
`src/vocabularies.py`:

1. `_normalize()` strips accents, lowercases, and removes separators
   (spaces/hyphens/slashes/quotes/colons) from both the raw value and every
   CSV term, so formatting drift (accents, case, `MR-001` vs `MR 001`)
   resolves silently.
2. `resolve_vocab_term(field, raw_value, lang, report)` looks up the
   normalized value in `mappings/vocabularies/{field}.csv`'s matching-
   language column.
3. If that fails, it falls through to `VOCAB_ALIASES` — a small, hand-
   maintained dict of known wording gaps the CSV can't cover by
   normalization alone (e.g. source sends the ISO code `"fr"` for
   `OriginLang` where the vocabulary expects the word `"Français"`).
4. If *that* still fails, the raw value passes through **unchanged** and
   `(field, raw_value)` is appended to the `report` list passed in — which
   is exactly what `run_transformation()` writes out as
   `{file}_unmatched_vocab.csv`.

`FIELD_CSV_ALIAS` handles the one case where two FReSH fields share one
vocabulary file (`SponsorType` borrows `FundingAgentType.csv`, since the
source only asks the underlying "organisation type" question once).

### Bilingual handling

Each study is two independent files (`-fr.xml` / `-en.xml`), paired by
**filename suffix**, not by any `<id>` inside the XML. `HierarchicalExtractor`
detects its own record's language once, up front, from
`/xml/dataset/metadata/additional/originLang`, and everything downstream
(vocab lookup, boolean/date field lists, the output's own `xml:lang`
attribute) keys off that. The target XSD uses XSD 1.1 Conditional Type
Assignment to pick the right-language enum during validation based on that
same `xml:lang` — this is *why* `src/validator.py` uses the `xmlschema`
package specifically: `lxml`/libxml2 only implement XSD 1.0 and silently
can't check this.

### Where the real data actually lives

This repo's own `data/input` / `data/output` / `data/logs` (all
`.gitignore`d) are for local single-file debugging via `run_pipeline.py`.
The real batch runs — the ones behind the review work in
`impact_to_fresh_review/` — read and write a **sibling** folder instead:
`xml_processing_home/data/{xml_files_from_IH_API, xml_files_out_IH_to_FRESH,
IH_to_FRESH_logs}`, pointed to by the hardcoded paths at the bottom of
`run_pipeline_batch.py`. Don't go looking for the full ~2,150-study dataset
inside this repo — it isn't here.

### Rough edges worth knowing about before they surprise you

- **`run_pipeline.py` still needs editing to pick a study.** Its `__main__`
  sets `fresh_id`/`lang` in the source. That is fine for a debug script —
  use `run_pipeline_batch.py --study-ids ...` when you want a real run — but
  it does mean the single-file entry point is not usable as-is.
- **`mappings/vocabularies/*.csv` are generated, not hand-authored** (from
  `get_CVs_from_fresh_technical_documentation_git.ipynb`) — if a term looks
  wrong, check whether the fix belongs upstream in `technical-documentation`
  or as a `VOCAB_ALIASES` entry, rather than hand-editing the CSV, or the
  fix will be silently lost next time the CSVs are regenerated.
