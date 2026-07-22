# %%
import os
from src.mapper import load_mapping_table
from src.extractor import APIExtractor
from src.builder import FReSHXMLBuilder
from src.validator import validate_xml_against_xsd

# Liste des nœuds de type complexe (Unbounded) issus du XSD
ARRAY_NODES = {
    "Keyword", "HealthTheme", "HealthDeterminant", "Pathology", "PopulationType",
    "Sex", "Age", "InclusionCriterion", "ExclusionCriterion", "Nation", "FranceRegion",
    "PrimaryInvestigator", "TeamMember", "ContactPoint", "FundingAgent", "RelatedDocument",
    "DataInformationContact", "BiobankContent", "ThirdPartySource", "ResearchPurpose",
    "TrialPhase", "InclusionGroup", "Intervention", "CollectionMode", "RecruitmentSource",
    "FollowUpMode", "DataType", "UsedStandards", "QualityProcedure", "ObtainedAuthorization",
    "Sponsor", "OrganisationPID", "FundingAgentPID", "SponsorPID"
}

def clean_extracted_data(flat_data):
    """
    Nettoie les données brutes extraites de l'API pour s'assurer qu'elles 
    respectent strictement les types de base attendus par le schéma XSD.
    """
    cleaned = {}
    for xpath, value in flat_data.items():
        # 1. Nettoyage des champs booléens (transforme "Oui/Non/Non renseigné" en "1/0")
        bool_fields = [
            "RareDiseases", "IsHealthTheme", "IsContributorPI", "AddTeamMember", 
            "IsClinicalTrial", "IsInclusionGroups", "IsActiveFollowUp", 
            "IsDataIntegration", "IsPIContact", "Committee", "NetworkConsortium"
        ]
        if any(b in xpath for b in bool_fields):
            if isinstance(value, str):
                cleaned[xpath] = "1" if value.strip().lower() in ["oui", "1", "true"] else "0"
            else:
                cleaned[xpath] = "0"
            continue

        # 2. Nettoyage des champs Date (transforme "2026-02-18T18:23..." en "2026-02-18")
        date_fields = ["CreationDate", "LastUpdatedAuto", "LastUpdatedManual", "CollectionStart", "CollectionEnd"]
        if any(d in xpath for d in date_fields) and isinstance(value, str):
            cleaned[xpath] = value.split("T")[0] if "T" in value else value
            continue
            
        # Si ce n'est ni une date ni un booléen, on garde la valeur intacte
        cleaned[xpath] = value
    return cleaned

def unflatten_dict(flat_dict):
    """Convertit un dictionnaire plat en dictionnaire imbriqué (Safe Padding)."""
    nested = {}
    for path, value in flat_dict.items():
        if value is None or value == "":
            continue
        parts = path.strip('/').split('/')
        current_level = nested
        for i, part in enumerate(parts[:-1]):
            if part in ARRAY_NODES:
                target_length = len(value) if isinstance(value, list) else 1
                if part in current_level and isinstance(current_level[part], list):
                    target_length = max(target_length, len(current_level[part]))
                if part not in current_level or not isinstance(current_level[part], list):
                    current_level[part] = [{} for _ in range(target_length)]
                if not isinstance(value, list):
                    val_list = [value] + [""] * (target_length - 1)
                elif len(value) < target_length:
                    val_list = value + [""] * (target_length - len(value))
                else:
                    val_list = value
                leaf_node = parts[-1]
                for index, item in enumerate(val_list):
                    try:
                        target_dict = current_level[part][index]
                    except IndexError:
                        target_dict = {}
                        current_level[part].append(target_dict)
                    temp_level = target_dict
                    for sub_part in parts[i+1:-1]:
                        if sub_part not in temp_level:
                            temp_level[sub_part] = {}
                        temp_level = temp_level[sub_part]
                    temp_level[leaf_node] = item
                break
            else:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
        else:
            leaf_node = parts[-1]
            current_level[leaf_node] = value
    return nested

def run_transformation(api_xml_path, mapping_csv_path, xsd_schema_path, output_xml_path):
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

    print("4. Cleaning Data Types (Dates & Booleans)...")
    cleaned_data = clean_extracted_data(flat_extracted_data)

    print("5. Grouping Data into Nested Dictionary...")
    nested_data = unflatten_dict(cleaned_data)
    
    print("6. Building and Saving Target XML...")
    builder = FReSHXMLBuilder()
    xml_root = builder.build_tree(nested_data)
    
    os.makedirs(os.path.dirname(output_xml_path), exist_ok=True)
    builder.save_xml(xml_root, output_xml_path)
    
    print("\n7. Validating Generated XML against XSD Schema...")
    is_valid, error_log = validate_xml_against_xsd(output_xml_path, xsd_schema_path)
    
    if is_valid:
        print("   [SUCCESS] Le fichier XML généré est 100% conforme au schéma XSD !")
    else:
        print("   [CRITICAL] Échec de la validation XSD. Le fichier généré n'est pas conforme.")
        print(error_log)
    print("\nPipeline Execution Ended.")

if __name__ == "__main__":
    data_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_tests\\xml_files_from_API"
    output_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_tests\\xml_files_out_IH_to_FRESH"
    
    run_transformation(
        api_xml_path=os.path.join(data_dir, "FReSH-43597-fr.xml"), 
        mapping_csv_path=os.path.join("mappings", "exhaustive_correspondance_v1.csv"),
        xsd_schema_path=os.path.join("mappings", "fresh-schema_v1.xsd"),
        output_xml_path=os.path.join(output_dir, "FReSH-43597-fr_fresh_schema.xml")
    )
# %%
