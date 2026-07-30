# %%
import os
import csv
import pandas as pd
from lxml import etree # type: ignore
import datetime
from src.builder import FReSHXMLBuilder # type: ignore
from src.validator import validate_xml_against_xsd
from src.vocabularies import resolve_vocab_term
import re
import json


# Fields extracted from a separate, parallel flat list elsewhere in the source
# document, matched to a sibling field by *position* (e.g. i-th AgencyRaw <->
# i-th OtherAgencyRaw, paired by enumerate() in builder.py). For these, blank
# entries must be preserved (not dropped) on both sides so the two lists stay
# index-aligned -- see HierarchicalExtractor._extract_text_keep_blanks and the
# matching exception in FReSHXMLBuilder._dict_to_xml.
POSITIONAL_RAW_FIELDS = {"AgencyRaw", "OtherAgencyRaw", "FundingAgentTypeRaw", "SponsorTypeRaw", "OtherSourceTypeRaw"}


def _vocab_field_name(target_xpath):
    """Maps a target_xpath to the FReSH tag its controlled-vocabulary lookup
    should key on: the leaf tag itself, or its parent when the leaf is the
    generic 'value' child of a CvIdType-style field (e.g. Sex/value). The
    sibling 'URI' child holds a code/identifier (ISO code, PID...), never a
    controlled-vocabulary term, so it's left keyed on its own leaf name,
    which has no vocab table and passes through resolve_vocab_term unchanged."""
    parts = target_xpath.strip('/').split('/')
    if parts[-1] == 'value' and len(parts) >= 2:
        return parts[-2]
    return parts[-1]


class HierarchicalExtractor:
    def __init__(self, xml_path, mapping_csv_path):
        self.tree = etree.parse(xml_path)
        self.mapping = pd.read_csv(mapping_csv_path).dropna(subset=['target_xpath'])
        self.namespaces = {}
        self.unmatched_vocab = []
        self.lang = self._detect_lang()

    def _detect_lang(self):
        """Determines the record's own language once, up front, from the
        source XML itself -- rather than relying on mapping-CSV row order to
        already know it by the time other vocab fields are processed."""
        values = self.tree.xpath('/xml/dataset/metadata/additional/originLang/text()')
        raw = values[0].strip().lower() if values else ""
        return "en" if raw == "en" else "fr"

    def _extract_text(self, elements):
        results = []
        for elem in elements:
            if isinstance(elem, str):
                text = elem.strip()
            else:
                text = elem.text.strip() if elem.text else ""
            if text:
                results.append(text)
        return results

    def _extract_text_keep_blanks(self, elements):
        """Like _extract_text, but keeps one entry per matched element (as ""
        when blank) instead of dropping empties -- required for fields paired
        by position with a sibling list (see POSITIONAL_RAW_FIELDS)."""
        results = []
        for elem in elements:
            if isinstance(elem, str):
                text = elem.strip()
            else:
                text = elem.text.strip() if elem.text else ""
            results.append(text)
        return results

    def _clean_value(self, target_xpath, value):
        if not value: return ""
        
        bool_fields = ["RareDiseases", "IsHealthTheme", "IsContributorPI", "AddTeamMember", 
                       "IsClinicalTrial", "IsInclusionGroups", "IsActiveFollowUp", 
                       "IsDataIntegration", "IsPIContact", "Committee", "NetworkConsortium"]
        date_fields = ["CreationDate", "LastUpdatedAuto", "LastUpdatedManual", "CollectionStart", "CollectionEnd"]
        
        def clean_single(v):
            if isinstance(v, str):
                import re, ast
                v_stripped = v.strip()
                
                
                # --- On protège TOUTES les balises "*Raw" pour le post-processing ---
                # (JSON ou faux-tableau ['a','b',...] décodé plus tard dans builder.py).
                # Sans ça, le bloc bracket-unwrap plus bas tronque silencieusement les
                # listes multi-éléments au premier élément dès que ast.literal_eval
                # réussit à parser la chaîne (ce qui dépend juste de la présence ou non
                # d'une apostrophe cassant le parsing -- comportement non déterministe).
                if target_xpath.strip('/').split('/')[-1].endswith('Raw'):
                    return v_stripped
                
                
                v_stripped = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', v_stripped)


                # --- NORMALISATION CONTRE LES VOCABULAIRES CONTRÔLÉS (ground truth CSV) ---
                v_stripped = resolve_vocab_term(_vocab_field_name(target_xpath), v_stripped, self.lang, self.unmatched_vocab)


                if any(b in target_xpath for b in bool_fields):
                    return "1" if v_stripped.lower() in ["oui", "yes", "1", "true"] else "0"
                
                if any(d in target_xpath for d in date_fields):
                    if "T" in v_stripped: return v_stripped.split("T")[0]
                    try: return datetime.datetime.strptime(v_stripped, "%Y-%m-%d").strftime("%Y-%m-%d")
                    except ValueError: 
                        try: return datetime.datetime.strptime(v_stripped, "%d-%m-%Y").strftime("%Y-%m-%d")
                        except: return v_stripped
                
                if v_stripped.startswith("['") and v_stripped.endswith("']"):
                    try: return ast.literal_eval(v_stripped)[0]
                    except: pass
                
                return v_stripped
            return v

        if isinstance(value, list):
            # On nettoie la liste et on retire les éléments vides, SAUF pour les
            # champs positionnels (AgencyRaw/OtherAgencyRaw...) où un élément vide
            # est un espace réservé nécessaire à l'alignement par index avec la
            # liste soeur (voir POSITIONAL_RAW_FIELDS).
            if target_xpath.strip('/').split('/')[-1] in POSITIONAL_RAW_FIELDS:
                cleaned_list = [clean_single(item) for item in value]
            else:
                cleaned_list = [clean_single(item) for item in value if item]
            # On aplatit la liste si le JSON a généré des sous-listes
            flat_list = []
            for item in cleaned_list:
                if isinstance(item, list): flat_list.extend(item)
                else: flat_list.append(item)
            return flat_list
        return clean_single(value)

    def _set_nested(self, dictionary, path, value):
        if value == "" or value == []: return
        parts = path.strip('/').split('/')
        for part in parts[:-1]:
            if part not in dictionary:
                dictionary[part] = {}
            dictionary = dictionary[part]
        dictionary[parts[-1]] = value

    def _set_nested_relative(self, base_dict, base_path, full_target_path, value):
        relative_target = full_target_path[len(base_path):].strip('/')
        self._set_nested(base_dict, relative_target, value)

    def process(self):
        final_dict = {}
        
        current_root_nodes = []
        current_root_dicts = []
        current_root_base_target = ""
        
        current_array_nodes = []
        current_array_dicts = []
        current_array_base_target = ""
        
        mode = "ABSOLUTE" 
        
        for _, row in self.mapping.iterrows():
            source = str(row['source_xpath']).strip()
            target = str(row['target_xpath']).strip()
            
            if source.startswith('/xml/'):
                mode = "ABSOLUTE"
                elements = self.tree.xpath(source, namespaces=self.namespaces)
                target_leaf = target.strip('/').split('/')[-1]
                if target_leaf in POSITIONAL_RAW_FIELDS:
                    extracted = self._extract_text_keep_blanks(elements)
                    if extracted:
                        self._set_nested(final_dict, target, self._clean_value(target, extracted))
                else:
                    extracted = self._extract_text(elements)
                    if extracted:
                        val = extracted[0] if len(extracted) == 1 else extracted
                        self._set_nested(final_dict, target, self._clean_value(target, val))
                    
            elif source.startswith('ROOT:'):
                mode = "ROOT"
                root_xpath = source.split('ROOT:')[1]
                current_root_base_target = target
                current_root_nodes = self.tree.xpath(root_xpath, namespaces=self.namespaces)
                current_root_dicts = [{} for _ in current_root_nodes]
                
                if current_root_dicts:
                    self._set_nested(final_dict, target, current_root_dicts)
                
            elif source.startswith('ARRAY:'):
                mode = "ARRAY"
                array_relative_xpath = source.split('ARRAY:')[1]
                current_array_base_target = target
                current_array_nodes = []
                current_array_dicts = []
                
                for root_node, root_dict in zip(current_root_nodes, current_root_dicts):
                    sub_nodes = root_node.xpath(array_relative_xpath, namespaces=self.namespaces)
                    sub_dicts = [{} for _ in sub_nodes]
                    
                    if sub_dicts:
                        self._set_nested_relative(root_dict, current_root_base_target, target, sub_dicts)
                        
                    current_array_nodes.append(sub_nodes)
                    current_array_dicts.append(sub_dicts)
                    
            elif source.startswith('./'):
                relative_xpath = source
                if mode == "ROOT":
                    for node, d in zip(current_root_nodes, current_root_dicts):
                        elements = node.xpath(relative_xpath, namespaces=self.namespaces)
                        extracted = self._extract_text(elements)
                        if extracted:
                            val = extracted[0] if len(extracted) == 1 else extracted
                            self._set_nested_relative(d, current_root_base_target, target, self._clean_value(target, val))
                            
                elif mode == "ARRAY":
                    for parent_sub_nodes, parent_sub_dicts in zip(current_array_nodes, current_array_dicts):
                        for node, d in zip(parent_sub_nodes, parent_sub_dicts):
                            elements = node.xpath(relative_xpath, namespaces=self.namespaces)
                            extracted = self._extract_text(elements)
                            if extracted:
                                val = extracted[0] if len(extracted) == 1 else extracted
                                self._set_nested_relative(d, current_array_base_target, target, self._clean_value(target, val))

        return self._prune_empty_dicts(final_dict)

    def _prune_empty_dicts(self, data):
        """Removes ROOT-loop dict entries that ended up with zero populated
        fields (e.g. a <metadata_no><item> whose agency/code were both blank).
        A dict is created upfront per matched source node, before any relative
        sub-row gets a chance to fill it in -- if none ever did, it's a hollow
        placeholder that would render as an empty element, which fails
        validation whenever the target's own children are required (e.g.
        OtherStudyId's IDSchema/Identifier)."""
        if isinstance(data, dict):
            for key in list(data.keys()):
                data[key] = self._prune_empty_dicts(data[key])
            return data
        if isinstance(data, list):
            pruned = []
            for item in data:
                if isinstance(item, dict):
                    cleaned = self._prune_empty_dicts(item)
                    if cleaned:
                        pruned.append(cleaned)
                else:
                    pruned.append(item)
            return pruned
        return data

def run_transformation(input_xml_path, mapping_csv_path, xsd_schema_path, output_xml_path, logs_path=None):
    print("1. Parsing and Hierarchical Extraction...")
    extractor = HierarchicalExtractor(input_xml_path, mapping_csv_path)
    nested_data = extractor.process()
    
    print("2. Building and Saving Target XML...")
    builder = FReSHXMLBuilder(lang=extractor.lang)
    xml_root = builder.build_tree(nested_data)
    
    os.makedirs(os.path.dirname(output_xml_path), exist_ok=True)
    builder.save_xml(xml_root, output_xml_path)
    
    print("\n3. Validating Generated XML against XSD Schema...")
    is_valid, error_log = validate_xml_against_xsd(output_xml_path, xsd_schema_path)


    if is_valid:
        print("   [SUCCESS] Le fichier XML généré est 100% conforme au schéma XSD !")
    else:
        print("   [CRITICAL] Échec de la validation XSD.")
        print(error_log)

    # print and save validation results
    # get file name without extension
    file_name = os.path.splitext(os.path.basename(input_xml_path))[0]
    
    if logs_path:
        os.makedirs(logs_path, exist_ok=True)
        validation_report_path = os.path.join(logs_path, f"{file_name}_validation_report.txt")
        with open(validation_report_path, "w", encoding="utf-8") as f:
            if is_valid:
                f.write("Le fichier XML généré est 100% conforme au schéma XSD !\n")
            else:
                f.write("Échec de la validation XSD.\n")
                f.write(error_log) # pyright: ignore[reportArgumentType]
        print(f"   Rapport de validation écrit dans : {validation_report_path}")
    unmatched_vocab = extractor.unmatched_vocab + builder.unmatched_vocab
    
    if unmatched_vocab:
        print(f"\n4. [WARNING] {len(unmatched_vocab)} valeur(s) sans correspondance dans les vocabulaires contrôlés :")
        for field_name, raw_value in unmatched_vocab:
            print(f"   - {field_name}: {raw_value!r}")

    # write logs
    report_path = os.path.join(logs_path, f"{file_name}_unmatched_vocab.csv") # pyright: ignore[reportArgumentType, reportCallIssue]
    with open(report_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["field", "raw_value"])
        writer.writerows(unmatched_vocab)
    print(f"   Rapport de vocabulaires écrit dans : {report_path}")

if __name__ == "__main__":
    data_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\impact_to_fresh_transformation\\data\\input"
    output_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\impact_to_fresh_transformation\\data\\output"
    logs_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\impact_to_fresh_transformation\\data\\logs"
    
    
    
    fresh_id = "43661"
    lang = "fr"
    # lang = "en"
    in_file_path = os.path.join(data_dir, f"FReSH-{fresh_id}-{lang}.xml")
    out_file_path = os.path.join(output_dir, f"FReSH-{fresh_id}-{lang}_clean.xml")
    
    
    # in_file_path = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\FReSH-model-playgroung\\test_files\\fromPreProd-FReSH-69765-fr.xml"
    # out_file_path = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\FReSH-model-playgroung\\test_files\\fromPreProd-FReSH-69765-fr_clean.xml"
    
    
    in_file_path = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\FReSH-model-playgroung\\FReSH-43677-fr.xml"
    out_file_path = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\FReSH-model-playgroung\\FReSH-43677-fr_clean.xml"
       
        
    run_transformation(
        input_xml_path=in_file_path,
        output_xml_path=out_file_path,
        mapping_csv_path=os.path.join("mappings", "entity_wise_corres_table.csv"),
        xsd_schema_path=os.path.join("mappings", "fresh-schema_v4.xsd"),
        logs_path=logs_dir
    )
# %%
