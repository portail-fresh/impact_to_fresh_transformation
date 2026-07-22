# %%
import os
from src.mapper import load_mapping_table
from src.extractor import APIExtractor
from src.builder import FReSHXMLBuilder

def unflatten_dict(flat_dict):
    """Converts a flat dictionary with XPath keys into a nested dictionary."""
    nested = {}
    for path, value in flat_dict.items():
        parts = path.strip('/').split('/')
        current_level = nested
        # Traverse/build the nested structure up to the last element
        for part in parts[:-1]:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
        # Set the final value
        current_level[parts[-1]] = value
    return nested

def run_transformation(api_xml_path, mapping_csv_path, output_xml_path):
    print("1. Loading Mapping Table...")
    mapping = load_mapping_table(mapping_csv_path)
    
    print(f"2. Parsing Source XML: {api_xml_path}...")
    extractor = APIExtractor(api_xml_path)
    
    print("3. Extracting Data based on Mapping...")
    flat_extracted_data = {}
    for source_xpath, target_xpath in mapping.items():
        value = extractor.get_value(source_xpath)
        if value is not None:
            flat_extracted_data[target_xpath] = value
            print(f"   [Found] {source_xpath} -> {value}")
        else:
            print(f"   [Missing] {source_xpath}")

    print("\n4. Converting to FReSH Nested Structure...")
    nested_data = unflatten_dict(flat_extracted_data)
    
    print("5. Building and Saving Target XML...")
    builder = FReSHXMLBuilder()
    xml_root = builder.build_tree(nested_data)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_xml_path), exist_ok=True)
    builder.save_xml(xml_root, output_xml_path)

if __name__ == "__main__":
    # Point these to your mock files
    run_transformation(
        api_xml_path="data/input/mock_api.xml", 
        mapping_csv_path="mappings/mock_table.csv",
        output_xml_path="data/output/mock_fresh_output.xml"
    )
# %%
