"""One-off maintenance script: regenerates the inline <xsd:enumeration> lists in
fresh-schema_v2.xsd to match the ground-truth controlled-vocabulary CSVs in
mappings/vocabularies/, writing the result to fresh-schema_v3.xsd.

Only touches fields that (a) have a matching vocab CSV and (b) already carry a
hardcoded XSD enumeration. Fields with no CSV (FundingAgentType,
ObservationalStudyDesign, VersionLang) are left untouched. PIDSchema is
context-scoped: only the OrganisationPIDType occurrence is synced (ROR/RNSR/
SIREN); PersonPIDType.PIDSchema (ORCID/IdRef) has no ground-truth CSV and is
left alone.
"""
import csv
import os
from lxml import etree

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_XSD = os.path.join(BASE, "mappings", "fresh-schema_v2.xsd")
DST_XSD = os.path.join(BASE, "mappings", "fresh-schema_v3.xsd")
VOCAB_DIR = os.path.join(BASE, "mappings", "vocabularies")

XSD_NS = "http://www.w3.org/2001/XMLSchema"
QN = lambda tag: f"{{{XSD_NS}}}{tag}"

# field_name -> required ancestor xsd:complexType name, for tag names reused
# across unrelated sub-vocabularies.
CONTEXT_SCOPE = {
    "PIDSchema": "OrganisationPIDType",
}

# field_name -> {old default value: new default value}, for xsd:element
# `default="..."` attributes whose value is itself an old enum term that no
# longer exists after the sync (found: Provenance, OriginLang).
DEFAULT_ATTR_REMAP = {
    "Provenance": {"PEF": "PEF (Portail Epidémiologie France)"},
    "OriginLang": {"fr": "Français", "en": "Anglais"},
}


def load_csv_terms(field_name):
    path = os.path.join(VOCAB_DIR, f"{field_name}.csv")
    if not os.path.exists(path):
        return None
    terms = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            term = (row.get("Terme français") or "").strip()
            if term:
                terms.append(term)
    return terms


def ancestor_complex_type_name(element):
    parent = element.getparent()
    while parent is not None:
        if parent.tag == QN("complexType"):
            return parent.get("name")
        parent = parent.getparent()
    return None


def find_enum_elements(root, field_name):
    required_ancestor = CONTEXT_SCOPE.get(field_name)
    matches = []
    for el in root.iter(QN("element")):
        if el.get("name") != field_name:
            continue
        restriction = el.find(f"{QN('simpleType')}/{QN('restriction')}")
        if restriction is None:
            continue
        if required_ancestor is not None and ancestor_complex_type_name(el) != required_ancestor:
            continue
        matches.append(restriction)
    return matches


def sync_restriction(restriction, new_terms):
    old_enums = restriction.findall(QN("enumeration"))
    old_values = [e.get("value") for e in old_enums]

    if old_values == new_terms:
        return False, old_values, new_terms

    tail = old_enums[0].tail if old_enums else "\n"
    for e in old_enums:
        restriction.remove(e)
    for term in new_terms:
        new_el = etree.SubElement(restriction, QN("enumeration"))
        new_el.set("value", term)
        new_el.tail = tail
    return True, old_values, new_terms


def main():
    tree = etree.parse(SRC_XSD)
    root = tree.getroot()

    fields_with_enum = set()
    for el in root.iter(QN("element")):
        name = el.get("name")
        if name and el.find(f"{QN('simpleType')}/{QN('restriction')}/{QN('enumeration')}") is not None:
            fields_with_enum.add(name)

    changed_fields = []
    unchanged_fields = []
    no_csv_fields = []

    for field_name in sorted(fields_with_enum):
        new_terms = load_csv_terms(field_name)
        if new_terms is None:
            no_csv_fields.append(field_name)
            continue

        restrictions = find_enum_elements(root, field_name)
        for restriction in restrictions:
            changed, old_values, new_values = sync_restriction(restriction, new_terms)
            if changed:
                changed_fields.append((field_name, old_values, new_values))
            else:
                unchanged_fields.append(field_name)

    print(f"Fields with an inline XSD enumeration: {len(fields_with_enum)}")
    print(f"No matching vocab CSV (left untouched): {sorted(no_csv_fields)}")
    print(f"Already matched the CSV (no change): {sorted(set(unchanged_fields))}")
    print(f"Synced ({len(changed_fields)} occurrence(s) changed):")
    for field_name, old_values, new_values in changed_fields:
        added = [v for v in new_values if v not in old_values]
        removed = [v for v in old_values if v not in new_values]
        print(f"  --- {field_name} ---")
        if added:
            print(f"    + added:   {added}")
        if removed:
            print(f"    - removed: {removed}")

    print("Fixing up 'default' attributes left pointing at removed enum values:")
    for field_name, remap in DEFAULT_ATTR_REMAP.items():
        for el in root.iter(QN("element")):
            if el.get("name") != field_name:
                continue
            current_default = el.get("default")
            if current_default in remap:
                new_default = remap[current_default]
                el.set("default", new_default)
                print(f"  {field_name}: default {current_default!r} -> {new_default!r}")

    tree.write(DST_XSD, encoding="utf-8", xml_declaration=True)
    print(f"\nWritten: {DST_XSD}")

    # Sanity check: the regenerated file must still parse as a valid XSD.
    check_tree = etree.parse(DST_XSD)
    etree.XMLSchema(check_tree)
    print("Sanity check passed: fresh-schema_v3.xsd parses as a valid XSD schema.")


if __name__ == "__main__":
    main()
