from pathlib import Path
import xml.etree.ElementTree as ET


def resolve_path(filename):
    """Find a data file whether the notebook runs from the repo root or FReSH-model."""
    path = Path(filename)

    # Jupyter's working directory can change depending on how the notebook was opened.
    # These two candidates cover both common cases:
    # 1. running from inside FReSH-model: FReSH-43597-fr_fromAPI.xml
    # 2. running from the project root: FReSH-model/FReSH-43597-fr_fromAPI.xml
    candidates = [path, Path("FReSH-model") / path]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Fail loudly with the attempted paths so the missing-file problem is easy to diagnose.
    raise FileNotFoundError(f"Could not find {filename!r}. Tried: {candidates}")


def iter_xml_records(xml_file):
    # Parse the XML document and get its root element, for example: <xml>...</xml>.
    tree = ET.parse(resolve_path(xml_file))
    root = tree.getroot()

    def walk(elem, current_path):
        # Capture the current XML element before visiting its children.
        # Empty/whitespace-only text is normalized to an empty string.
        text = (elem.text or "").strip()
        yield {
            "xpath": current_path,
            "tag": elem.tag,
            "text": text,
            "attributes": dict(elem.attrib),
        }

        # Count child tags so repeated sibling elements can get XPath indexes.
        # Example: two <item> children become /item[1] and /item[2].
        child_tags = [child.tag for child in elem]
        tag_totals = {tag: child_tags.count(tag) for tag in set(child_tags)}
        tag_seen = {}

        for child in elem:
            # Track how many children with this tag we have already visited.
            tag_seen[child.tag] = tag_seen.get(child.tag, 0) + 1

            # Use a shorter path for unique children and an indexed path for repeated children.
            if tag_totals[child.tag] == 1:
                child_path = f"{current_path}/{child.tag}"
            else:
                child_path = f"{current_path}/{child.tag}[{tag_seen[child.tag]}]"

            # Recursively visit the child and all descendants.
            yield from walk(child, child_path)

    # Start the recursive traversal at the document root.
    yield from walk(root, f"/{root.tag}")


def get_all_xpaths(xml_file):
    # Convenience function when we only need the XPath strings, not text or attributes.
    return [record["xpath"] for record in iter_xml_records(xml_file)]



##################################################################
import xml.etree.ElementTree as ET
# Assuming resolve_path is available from your xml_process_tools

def get_xsd_xpaths(xsd_file):
    """
    Parses the FReSH XSD file and returns a list of dictionaries representing the expected target XML XPaths,
    ignoring XSD-specific tags like annotations.
    
    Outputs:
    list_dicts: A list of dictionaries, each containing:
        - 'xpath': The XPath string for the element.
        - 'element_name': The name of the element.
        - 'data_type': The data type of the element (if specified).
        - 'min_occurs': The minimum occurrences of the element (default is 1).
        - 'max_occurs': The maximum occurrences of the element (default is 1).
    
    list_xpaths: A list of XPath strings for all elements in the XSD, ignoring annotations and documentation.
    
    """
    tree = ET.parse(resolve_path(xsd_file))
    root = tree.getroot()
    
    # The XSD namespace defined in the FReSH schema header
    ns = 'http://www.w3.org/2001/XMLSchema'
    
    list_dicts = []
    list_xpaths = []
    
    def walk_xsd(elem, current_path):
        # 1. If we find an <xsd:element>, it translates to a node in the final XML structure
        if elem.tag == f"{{{ns}}}element":
            name = elem.attrib.get("name")
            
            if name:
                # Append the current element's name to the XPath
                new_path = f"{current_path}/{name}"
                
                # Save structural properties that might be useful for your correspondence table
                list_dicts.append({
                    "xpath": new_path,
                    "element_name": name,
                    "data_type": elem.attrib.get("type", "nested_complex_type"),
                    "min_occurs": elem.attrib.get("minOccurs", "1"),
                    "max_occurs": elem.attrib.get("maxOccurs", "1")
                })
                list_xpaths.append(new_path)
                
                # Continue deeper into this element's structure (e.g., exploring its complexType)
                for child in elem:
                    walk_xsd(child, new_path)
                    
        # 2. Skip annotations and documentation completely
        elif elem.tag in [f"{{{ns}}}annotation", f"{{{ns}}}documentation"]:
            pass
            
        # 3. For structural XSD tags (complexType, sequence), just pass the current path along
        else:
            for child in elem:
                walk_xsd(child, current_path)

    # Start walking from the children of the <xsd:schema> root
    for child in root:
        walk_xsd(child, "")
        
    return list_dicts, list_xpaths

