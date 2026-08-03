# `fresh-schema_v4.xsd`: bilingual (FR/EN) controlled vocabularies

## Where it came from

- `fresh-schema_v0.xsd` / `v1.xsd` / `v2.xsd` — earlier hand-edited versions of the FReSH schema.
- `fresh-schema_v3.xsd` — generated from `v2.xsd` by `sync_xsd_vocabularies.py`. Every controlled-vocabulary field's `<xsd:enumeration>` list was regenerated from the ground-truth CSVs in `mappings/vocabularies/`, so the schema's enum values match the CSVs' `Terme français` column exactly. Still plain **XSD 1.0**, still **French-only**.
- `fresh-schema_v4.xsd` — generated from `v3.xsd` by `sync_xsd_vocabularies_bilingual.py`. Same vocab fields, but each one can now hold **either** its French **or** its English ground-truth term, depending on the language the record itself is written in.

`v3.xsd`/`v4.xsd` are kept as checkpoints; neither is otherwise used by the pipeline today.

- `fresh-schema_v5.xsd` — hand-edited from `v4.xsd` (minOccurs tweaks, a few structural fixes).
- `fresh-schema_v6.xsd` — generated from `v5.xsd` by `sync_xsd_vocabularies_cvidtype.py`, which retires both `sync_xsd_vocabularies.py` and `sync_xsd_vocabularies_bilingual.py` above (their "the enum/CTA sits directly on the field's element" assumption stops holding once every vocab field is wrapped in a `value`/`URI` structure). `v6.xsd` gives every controlled-vocabulary field a ground-truth `URI` (sourced from the vocab CSVs' `exactMatch` column) alongside its `value`, not just the handful that already used `CvIdType`. `v6.xsd` is what `run_pipeline.py` validates against today.

## The problem v4 solves

Every FReSH study exists as two parallel source files, e.g. `FReSH-43597-fr.xml` and `FReSH-43597-en.xml` — same study, one written in French, one in English. Controlled-vocabulary fields (`Status`, `ResearchType`, `MaskingType`, `SourceType`, ~15 others) arrive as **already-translated text** in each file — the English file literally contains `"Interventional Study"` where the French one has `"Etude interventionnelle (expérimentale)"`.

A schema whose enumerations are French-only (like `v3.xsd`) can only validate the French file. Three ways to make it accept both were considered:

1. **Union the enums** (list both languages' terms as valid for every field). Simplest, but a record could then mix languages field-by-field with the schema none the wiser — `Status` in French next to `ResearchType` in English would validate.
2. **Two schemas, one shared structure** (`xsd:include`), one small vocab file per language. Strict per-language validation, no structural duplication, but you validate against a different file per language and end up with two output artifacts.
3. **XSD 1.1 Conditional Type Assignment (CTA)** — one schema, one document shape; each vocab field's legal type is chosen automatically based on the record's own declared language.

**v4 uses option 3.**

## How CTA works here

One attribute, set once, on the root element:

```xml
<FreshSchema ... xml:lang="fr">
```

(`xml:lang="en"` for the English file.) `run_pipeline.py` detects the record's language from `originLang` once at the start (`HierarchicalExtractor._detect_lang`) and `FReSHXMLBuilder` stamps it onto `xml:lang` when it builds the tree.

For every controlled-vocabulary field, instead of one inline enumeration:

```xml
<!-- v3.xsd -->
<xsd:element name="Status">
  <xsd:simpleType>
    <xsd:restriction base="xsd:string">
      <xsd:enumeration value="Envoyée pour publication"/>
      <xsd:enumeration value="Brouillon"/>
      ...
    </xsd:restriction>
  </xsd:simpleType>
</xsd:element>
```

`v4.xsd` has two named types and a choice between them:

```xml
<!-- v4.xsd -->
<xsd:element name="Status">
  <xsd:alternative test="@xml:lang='en'" type="StatusEnType"/>
  <xsd:alternative type="StatusFrType"/>
</xsd:element>

<xsd:simpleType name="StatusFrType">
  <xsd:restriction base="xsd:string">
    <xsd:enumeration value="Envoyée pour publication"/>
    <xsd:enumeration value="Brouillon"/>
    ...
  </xsd:restriction>
</xsd:simpleType>

<xsd:simpleType name="StatusEnType">
  <xsd:restriction base="xsd:string">
    <xsd:enumeration value="Awaiting validation"/>
    <xsd:enumeration value="Draft"/>
    ...
  </xsd:restriction>
</xsd:simpleType>
```

`@xml:lang='en'` is evaluated once per element, using whichever ancestor declared `xml:lang` — the root's attribute is declared `inheritable="true"`, so every descendant sees it without repeating it. If the test is true, `Status` must be one of the English terms; otherwise (including when `xml:lang` is absent entirely) it falls back to the French list. This means:

- A French record's `Status` must be a valid **French** term.
- An English record's `Status` must be a valid **English** term.
- An English record that accidentally contains a French `Status` value is **rejected** — this was verified directly: taking a valid French output and swapping one field to its English equivalent while leaving `xml:lang="fr"` causes validation to fail with a clear enumeration error. Unlike the "union" option, CTA still catches inconsistent records.

This treatment was applied to every field that already had a hardcoded, French-only `<xsd:enumeration>` list in `v3.xsd` and has a matching CSV in `mappings/vocabularies/` (18 fields as of this writing: `Status`, `StudyStatus`, `ResearchType`, `MaskingType`, `AllocationMode`, `AllocationUnit`, `ConformityDeclaration`, `InterventionType`, `InterventionalStudyModel`, `BlindedMaskingDetails`, `OriginLang`, `PIDSchema` *(only the `OrganisationPIDType` context, see below)*, `Provenance`, `ResearchPurpose`, `SourcePurpose`, `SourceType`, `TrialPhase`, `ObservationalStudyDesign`). Fields without their own hardcoded enum (the `CvIdType` / free-text ones like `Sex`, `Age`, `Nation`, `HealthTheme`, `CollectionMode`, `SamplingMode`, `DataType`...) were never schema-constrained in the first place — they stay free text in both `v3` and `v4`, and their FR/EN normalization is handled entirely by `src/vocabularies.py`, not by the schema.

## One subtlety: `PIDSchema` is context-scoped

The tag `PIDSchema` is reused for two unrelated concepts: a *person's* identifier scheme (`PersonPIDType` — `ORCID`/`IdRef`, no ground-truth CSV, untouched) and an *organisation's* identifier scheme (`OrganisationPIDType` — `ROR`/`RNSR`/`SIREN`, has a CSV). The sync script only converts the `OrganisationPIDType` occurrence to CTA; the `PersonPIDType` one is left exactly as it was.

## Root-level additions in v4

- `<xsd:import namespace="http://www.w3.org/XML/1998/namespace" schemaLocation="https://www.w3.org/2001/xml.xsd"/>` — required so the schema can reference `xml:lang` by its proper namespace. `vc:minVersion="1.1"` was already present on the schema root from `v2`/`v3`.
- `<xsd:attribute ref="xml:lang" inheritable="true"/>` added to the root `FreshSchema` complex type.

Everything else structurally is identical to `v3.xsd` — same elements, same order, same non-vocab types.

## Toolchain impact

**lxml/libxml2 cannot validate `v4.xsd` correctly** — it only implements XSD 1.0. It doesn't recognize `xsd:alternative`/`inheritable` as valid syntax at all (they show up as `SCHEMAP_S4S_ELEM_NOT_ALLOWED` errors if you try), and even where it tolerates the file, it silently ignores the CTA logic. This is also why `redhat.vscode-xml`/LemMinX (whatever's flagging warnings in your editor on this file) shows false-positive errors — it's a 1.0-only validator seeing 1.1-only syntax it has no model for.

`src/validator.py` therefore uses the `xmlschema` package (`xmlschema.XMLSchema11`), which does implement CTA. One implementation detail worth knowing: `xmlschema`'s `iter_errors()` defaults to `validation='lax'`, which — for reasons specific to this library — can silently skip content it can't resolve unambiguously instead of flagging it (this let a real invalid value through undetected during testing). `validate_xml_against_xsd()` uses `schema.validate()` instead, which internally forces `validation='strict'` and is the path that's been verified to actually enforce CTA correctly.

## Regenerating v4

If a vocab CSV in `mappings/vocabularies/` changes (a term added/renamed), or a new field needs the same bilingual treatment:

1. If the change also affects the French-only baseline, run `sync_xsd_vocabularies.py` first (`v2.xsd` → `v3.xsd`).
2. Run `sync_xsd_vocabularies_bilingual.py` (`v3.xsd` → `v4.xsd`). It reports which fields it converted, which were already up to date, and which fields have no matching CSV and were left alone — read that output before trusting the result, especially for any field whose CSV set just changed shape (added/removed terms), since the diff shown is exactly what's about to become the new source of truth.
3. Re-run the pipeline against a sample of both a `-fr` and a `-en` file and confirm both still validate.
