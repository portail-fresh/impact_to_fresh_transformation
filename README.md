# IMPACT to FReSH transformation

Converts source study records (IMPACT/API export XML, one file per language per
study) into FReSH-schema XML, validated against `mappings/fresh-schema_v5.xsd`.

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

**Batch, all studies or a chosen subset**: `run_pipeline_batch.py`. At the
bottom of the file, `data_dir`/`output_dir`/`logs_dir` are hardcoded paths —
marked `/!\ MODIFY PATHS HERE AS NEEDED /!\` — update them to match your own
machine first (e.g. point `data_dir` at this repo's own `data/input` if
that's where your source files are).

```python
# Leave as None to process every study (both '-fr' and '-en') found in
# data_dir. To run only a subset, list the ids to include instead, e.g.:
# study_ids = ["43597", "PEF3476", "PEF60139", "PEF73375", "PEF74055"]
study_ids = None
```

Leave `study_ids = None` to process every study in `data_dir`, in both
languages, or set it to a list of ids (bare numeric or `PEF...`, matched
case-insensitively against the filename) to run just those — both their
`-fr` and `-en` files. Then:

```bash
python run_pipeline_batch.py
```

Each study's converted XML lands in `output_dir`, and a per-file validation
report + unmatched-vocabulary report is written to `logs_dir`. The batch run
prints a final summary of how many studies succeeded vs failed.
