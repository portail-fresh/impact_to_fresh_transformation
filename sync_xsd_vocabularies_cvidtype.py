"""Regenerates the FReSH schema so every controlled-vocabulary field carries
a ground-truth exactMatch URI, not just the 8 that already used CvIdType.

Reads fresh-schema_v5.xsd and the current mappings/vocabularies/*.csv files
(prefLabel_fr/prefLabel_en/exactMatch/identifier columns -- see
src/vocabularies.py and get_CVs_from_fresh_technical_documentation_git.ipynb),
and writes fresh-schema_v6.xsd.

Replaces sync_xsd_vocabularies.py (v2->v3, enum sync) and
sync_xsd_vocabularies_bilingual.py (v3->v4, CTA wrap): both scripts locate a
field's vocabulary by "the enum/CTA sits directly on <xsd:element name=Field>"
-- once every field is wrapped in a value/URI structure, that shape no longer
exists to find, so this script does the whole regeneration in one pass instead
of two, straight off the current v5 baseline. Both old scripts are retired to
old_scripts/.

Two groups of fields are touched:

- "CTA fields" (BUCKET_A below): today the FR/EN enum sits directly on the
  field's own element via XSD 1.1 Conditional Type Assignment. Each gets a new
  named {Field}Type complexType: a `value` child carrying the same CTA (now
  regenerated fresh from the current CSV -- this also fixes any field whose
  enum had drifted out of sync with a renamed/edited CSV, e.g.
  ObservationalStudyDesign) plus a `URI` child (xsd:anyURI, repeatable). The
  field's own element is retargeted to type="{Field}Type".
- "plain-string fields" (BUCKET_C below): today unconstrained xsd:string, no
  schema-level enum. Simply retargeted to the existing generic CvIdType
  complexType (value: xsd:string, URI: xsd:anyURI) -- already used by Sex,
  Age, Nation, HealthTheme, CollectionMode, SamplingMode, IndividualDataAccess.

ArmType is a special case within BUCKET_A: today it's not text at all -- the
element decomposes into 5 required xsd:boolean flags (ExperimentalArm,
ActiveComparatorArm, PlaceboComparatorArm, SharmComparatorArm,
NoInterventionArm). That structure is deleted outright and replaced with the
normal CTA value/URI shape like every other BUCKET_A field.

Fields intentionally left untouched: Pathology (CvIdType already, but no
ground-truth CSV to source a value/URI-refresh from), PersonPIDType's own
PIDSchema (ORCID/IdRef -- no CSV, and the wrong context besides), and
Provenance's own instance data (no mapping-CSV row populates it, so it stays
declared but empty in every real output file even though its schema shape is
converted like the rest of BUCKET_A).
"""
import csv
import os
from lxml import etree  # type: ignore
import xmlschema

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_XSD = os.path.join(BASE, "mappings", "fresh-schema_v5.xsd")
DST_XSD = os.path.join(BASE, "mappings", "fresh-schema_v6.xsd")
VOCAB_DIR = os.path.join(BASE, "mappings", "vocabularies")

XSD_NS = "http://www.w3.org/2001/XMLSchema"
QN = lambda tag: f"{{{XSD_NS}}}{tag}"

# field_name -> required ancestor xsd:complexType name, for tag names reused
# across unrelated sub-vocabularies. Same convention as the old scripts.
CONTEXT_SCOPE = {
    "PIDSchema": "OrganisationPIDType",
}

# field_name -> the CSV it actually reads terms/URIs from, for fields with no
# CSV of their own. Mirrors src/vocabularies.py's FIELD_CSV_ALIAS.
CSV_ALIAS = {
    "SponsorType": "FundingAgentType",
}

# Fields whose FR/EN enum is today CTA'd directly on their own element
# (<xsd:alternative>), destined to become a {Field}Type complexType with a
# `value` (still CTA'd) + `URI` child. ArmType is included even though it's
# not CTA today -- see module docstring.
BUCKET_A = [
    "Provenance", "OriginLang", "Status", "StudyStatus", "AuthorizingAgency",
    "FundingAgentType", "ResearchType", "TrialPhase", "ResearchPurpose",
    "InterventionalStudyModel", "AllocationMode", "AllocationUnit", "MaskingType",
    "BlindedMaskingDetails", "ObservationalStudyDesign", "ConformityDeclaration",
    "SourceType", "SourcePurpose", "InterventionType", "PIDSchema",
    "ArmType", "SponsorType",
]

# Fields that are plain, unconstrained xsd:string today, destined to just
# retarget to the existing generic CvIdType complexType.
BUCKET_C = [
    "DataType", "DatasetPIDSchema", "DocumentType", "FollowUpMode", "FranceRegion",
    "HealthDeterminant", "PlannedSampleSize", "PopulationType", "RecruitmentSource",
    "BiobankContent", "TimePerspective",
]


def load_csv_terms(field_name):
    csv_name = CSV_ALIAS.get(field_name, field_name)
    path = os.path.join(VOCAB_DIR, f"{csv_name}.csv")
    if not os.path.exists(path):
        return None
    fr_terms, en_terms = [], []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            fr = (row.get("prefLabel_fr") or "").strip()
            en = (row.get("prefLabel_en") or "").strip()
            if fr:
                fr_terms.append(fr)
            if en:
                en_terms.append(en)
    return fr_terms, en_terms


def ancestor_complex_type_name(element):
    parent = element.getparent()
    while parent is not None:
        if parent.tag == QN("complexType"):
            return parent.get("name")
        parent = parent.getparent()
    return None


def find_field_element(root, field_name):
    """The single <xsd:element name=field_name> this script should touch,
    honoring CONTEXT_SCOPE. Raises if it finds anything other than one."""
    required_ancestor = CONTEXT_SCOPE.get(field_name)
    matches = []
    for el in root.iter(QN("element")):
        if el.get("name") != field_name:
            continue
        if required_ancestor is not None and ancestor_complex_type_name(el) != required_ancestor:
            continue
        matches.append(el)
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one <xsd:element name='{field_name}'> "
            f"(scope={required_ancestor}), found {len(matches)}"
        )
    return matches[0]


def find_named_simple_type(root, type_name):
    for el in root.iter(QN("simpleType")):
        if el.get("name") == type_name:
            return el
    return None


def build_enumeration_type(type_name, terms):
    simple_type = etree.Element(QN("simpleType"), name=type_name)
    restriction = etree.SubElement(simple_type, QN("restriction"), base="xsd:string")
    for term in terms:
        etree.SubElement(restriction, QN("enumeration"), value=term)
    return simple_type


def refresh_enumeration_type(simple_type_el, terms):
    restriction = simple_type_el.find(QN("restriction"))
    for old_enum in restriction.findall(QN("enumeration")):
        restriction.remove(old_enum)
    for term in terms:
        etree.SubElement(restriction, QN("enumeration"), value=term)


def ensure_fr_en_types(root, field_name, fr_terms, en_terms, new_types):
    """Creates or refreshes {field_name}FrType/EnType in place; returns their names."""
    fr_type_name, en_type_name = f"{field_name}FrType", f"{field_name}EnType"
    for type_name, terms in ((fr_type_name, fr_terms), (en_type_name, en_terms)):
        existing = find_named_simple_type(root, type_name)
        if existing is not None:
            refresh_enumeration_type(existing, terms)
        else:
            new_types.append(build_enumeration_type(type_name, terms))
    return fr_type_name, en_type_name


def convert_bucket_a_field(root, field_name, new_types):
    csv_terms = load_csv_terms(field_name)
    if csv_terms is None:
        print(f"  [SKIP] {field_name}: no vocab CSV found")
        return
    fr_terms, en_terms = csv_terms
    fr_type_name, en_type_name = ensure_fr_en_types(root, field_name, fr_terms, en_terms, new_types)

    element = find_field_element(root, field_name)

    # Remove whatever currently defines the element's content: two
    # <xsd:alternative> (already-CTA fields) or a nested <xsd:complexType>
    # (ArmType's boolean decomposition). <xsd:annotation> is kept as-is.
    for child in element.findall(QN("alternative")):
        element.remove(child)
    for child in element.findall(QN("complexType")):
        element.remove(child)
    for child in element.findall(QN("simpleType")):
        element.remove(child)

    default = element.attrib.pop("default", None)
    element.attrib.pop("type", None)

    field_type_name = f"{field_name}Type"
    element.set("type", field_type_name)

    value_el = etree.Element(QN("element"), name="value")
    if default is not None:
        value_el.set("default", default)
    etree.SubElement(value_el, QN("alternative"), test="@xml:lang='en'", type=en_type_name)
    etree.SubElement(value_el, QN("alternative"), type=fr_type_name)

    uri_el = etree.Element(QN("element"), name="URI", type="xsd:anyURI", minOccurs="0", maxOccurs="unbounded")

    complex_type = etree.Element(QN("complexType"), name=field_type_name)
    sequence = etree.SubElement(complex_type, QN("sequence"))
    sequence.append(value_el)
    sequence.append(uri_el)
    new_types.append(complex_type)

    print(f"  [OK] {field_name}: {len(fr_terms)} FR / {len(en_terms)} EN term(s) -> type=\"{field_type_name}\"")


def convert_bucket_c_field(root, field_name):
    csv_name = CSV_ALIAS.get(field_name, field_name)
    csv_path = os.path.join(VOCAB_DIR, f"{csv_name}.csv")
    if not os.path.exists(csv_path):
        print(f"  [SKIP] {field_name}: no vocab CSV found")
        return
    element = find_field_element(root, field_name)
    element.attrib.pop("type", None)
    element.set("type", "CvIdType")
    print(f"  [OK] {field_name}: retargeted to CvIdType")


def main():
    tree = etree.parse(SRC_XSD)
    root = tree.getroot()
    new_types = []

    print(f"Bucket A ({len(BUCKET_A)} field(s)) -- CTA fields becoming {{Field}}Type (value CTA'd + URI):")
    for field_name in BUCKET_A:
        convert_bucket_a_field(root, field_name, new_types)

    print(f"\nBucket C ({len(BUCKET_C)} field(s)) -- plain-string fields becoming CvIdType:")
    for field_name in BUCKET_C:
        convert_bucket_c_field(root, field_name)

    for new_type in new_types:
        root.append(new_type)

    tree.write(DST_XSD, encoding="utf-8", xml_declaration=True)
    print(f"\nWritten: {DST_XSD}")

    xmlschema.XMLSchema11(DST_XSD)
    print("Sanity check passed: fresh-schema_v6.xsd builds as a valid XSD 1.1 schema.")


if __name__ == "__main__":
    main()
