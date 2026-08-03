"""One-off maintenance script: makes the FReSH schema bilingual (FR/EN) using
XSD 1.1 Conditional Type Assignment (CTA).

Reads fresh-schema_v3.xsd (the XSD 1.0, French-only, CSV-synced checkpoint
produced by sync_xsd_vocabularies.py, which is left untouched by this script)
and writes fresh-schema_v4.xsd.

For each of the 17 CSV-backed vocab fields, replaces the single inline
<xsd:simpleType><xsd:restriction> enumeration with two named simple types
(FieldFrType / FieldEnType, sourced from the CSV's "Terme français" / "Terme
anglais" columns) plus two <xsd:alternative> children on the element:
  - type=FieldEnType when @xml:lang='en'
  - type=FieldFrType otherwise (the no-test alternative is the default)

This requires one inheritable `xml:lang` attribute on the root FreshSchema
element (added here) -- XSD 1.1 attribute inheritance propagates it to every
descendant automatically, so it does not need to be repeated on each element
in an instance document.

Validated against the `xmlschema` package (XSD 1.1 aware); lxml/libxml2 only
implements XSD 1.0 and cannot check `xsd:alternative`, so src/validator.py
was switched to use `xmlschema` for validation.
"""
import csv
import os
from lxml import etree
import xmlschema

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_XSD = os.path.join(BASE, "mappings", "fresh-schema_v3.xsd")
DST_XSD = os.path.join(BASE, "mappings", "fresh-schema_v4.xsd")
VOCAB_DIR = os.path.join(BASE, "mappings", "vocabularies")

XSD_NS = "http://www.w3.org/2001/XMLSchema"
XML_NS = "http://www.w3.org/XML/1998/namespace"
QN = lambda tag: f"{{{XSD_NS}}}{tag}"

# field_name -> required ancestor xsd:complexType name, for tag names reused
# across unrelated sub-vocabularies. Same as sync_xsd_vocabularies.py.
CONTEXT_SCOPE = {
    "PIDSchema": "OrganisationPIDType",
}

# field_name -> {old default value: new default value}, for xsd:element
# `default="..."` attributes whose value is itself an old enum term that no
# longer exists after the sync. The default always resolves to the French
# term: it is only ever injected when a field is absent from the source data,
# which happens before xml:lang-based CTA has anything to key off, so French
# (the no-test/fallback alternative) is the only choice that's always valid.
DEFAULT_ATTR_REMAP = {
    "Provenance": {"PEF": "PEF (Portail Epidémiologie France)"},
    "OriginLang": {"fr": "Français", "en": "Anglais"},
}


def load_csv_terms(field_name):
    path = os.path.join(VOCAB_DIR, f"{field_name}.csv")
    if not os.path.exists(path):
        return None
    fr_terms, en_terms = [], []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            fr = (row.get("Terme français") or "").strip()
            en = (row.get("Terme anglais") or "").strip()
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


def find_vocab_elements(root, field_name):
    """Elements still carrying an inline single-language enumeration
    (i.e. not yet converted to CTA by a previous run of this script)."""
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
        matches.append(el)
    return matches


def build_named_type(type_name, terms):
    simple_type = etree.Element(QN("simpleType"), name=type_name)
    restriction = etree.SubElement(simple_type, QN("restriction"), base="xsd:string")
    for term in terms:
        enum = etree.SubElement(restriction, QN("enumeration"))
        enum.set("value", term)
    return simple_type


def convert_to_cta(element, field_name, fr_terms, en_terms, new_types):
    fr_type_name = f"{field_name}FrType"
    en_type_name = f"{field_name}EnType"
    new_types.append(build_named_type(fr_type_name, fr_terms))
    new_types.append(build_named_type(en_type_name, en_terms))

    old_simple_type = element.find(QN("simpleType"))
    old_index = list(element).index(old_simple_type)
    element.remove(old_simple_type)

    en_alt = etree.Element(QN("alternative"))
    en_alt.set("test", "@xml:lang='en'")
    en_alt.set("type", en_type_name)
    fr_alt = etree.Element(QN("alternative"))
    fr_alt.set("type", fr_type_name)

    element.insert(old_index, en_alt)
    element.insert(old_index + 1, fr_alt)


def add_xml_namespace_import(root):
    import_el = etree.Element(QN("import"))
    import_el.set("namespace", XML_NS)
    import_el.set("schemaLocation", "https://www.w3.org/2001/xml.xsd")
    import_el.tail = "\n\n    "
    root.insert(0, import_el)


def add_root_lang_attribute(root):
    for element in root.iter(QN("element")):
        if element.get("name") == "FreshSchema":
            complex_type = element.find(QN("complexType"))
            attr = etree.SubElement(complex_type, QN("attribute"))
            attr.set("ref", "xml:lang")
            attr.set("inheritable", "true")
            return
    raise RuntimeError("Could not find root FreshSchema element to attach xml:lang to")


def main():
    tree = etree.parse(SRC_XSD)
    root = tree.getroot()

    fields_with_enum = set()
    for el in root.iter(QN("element")):
        name = el.get("name")
        if name and el.find(f"{QN('simpleType')}/{QN('restriction')}/{QN('enumeration')}") is not None:
            fields_with_enum.add(name)

    converted_fields = []
    no_csv_fields = []
    new_types = []

    for field_name in sorted(fields_with_enum):
        csv_terms = load_csv_terms(field_name)
        if csv_terms is None:
            no_csv_fields.append(field_name)
            continue
        fr_terms, en_terms = csv_terms

        elements = find_vocab_elements(root, field_name)
        for element in elements:
            convert_to_cta(element, field_name, fr_terms, en_terms, new_types)
            converted_fields.append((field_name, len(fr_terms), len(en_terms)))

    print(f"Fields with an inline XSD enumeration: {len(fields_with_enum)}")
    print(f"No matching vocab CSV (left untouched): {sorted(no_csv_fields)}")
    print(f"Converted to XSD 1.1 CTA ({len(converted_fields)} occurrence(s)):")
    for field_name, n_fr, n_en in converted_fields:
        print(f"  {field_name}: {n_fr} FR term(s), {n_en} EN term(s)")

    # Append the newly generated named simple types at the end of the schema.
    for simple_type in new_types:
        root.append(simple_type)

    add_root_lang_attribute(root)
    add_xml_namespace_import(root)
    print("Added inheritable xml:lang attribute to root FreshSchema element (plus the xml namespace import).")

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

    # Sanity check: only xmlschema (XSD 1.1 aware) can validate this file;
    # lxml/libxml2 only implements XSD 1.0 and would silently ignore CTA.
    schema = xmlschema.XMLSchema11(DST_XSD)
    print("Sanity check passed: fresh-schema_v4.xsd builds as a valid XSD 1.1 schema.")


if __name__ == "__main__":
    main()
