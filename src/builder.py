import os
import xml.etree.ElementTree as ET
from src.vocabularies import resolve_vocab_term

class FReSHXMLBuilder:
    def __init__(self):
        self.unmatched_vocab = []
        self.ns_map = {
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "xmlns:vc": "http://www.w3.org/2007/XMLSchema-versioning"
        }
        
        # --- THE MASTER SORTING DICTIONARY ---
        # Garantit l'ordre strict des balises imposé par le XSD
        self.schema_hierarchy = {
            "FreshSchema": ["TechnicalInfo", "StudyRelatedInfo", "AdministrativeInformation", "StudyMethodology", "DataCollectionAccess"],
            "TechnicalInfo": ["StudyId", "Provenance", "VersionLang", "OriginLang", "CreationDate", "LastUpdatedAuto", "LastUpdatedManual", "RespValidation", "AutoTranslation", "Status", "MetadataContributor"],
            "MetadataContributor": ["ContributorName", "ContributorAffiliation"],
            "StudyRelatedInfo": ["StudyOverview", "Theme", "Population"],
            "StudyOverview": ["Title", "Acronym", "StudyStatus", "Purpose", "Summary", "Keyword"],
            "Theme": ["IsHealthTheme", "HealthTheme", "OtherHealthTheme", "HealthDeterminant", "OtherSocioDemoDeterminant", "OtherEnvironmentalDemoDeterminant", "OtherHealthcarSystemDeterminant", "OtherBehaviouralDeterminant", "OtherBiologicalDeterminant", "OtherDeterminant", "Pathology", "RareDiseases"],
            "Population": ["PopulationType", "OtherPopulationType", "DemographicInfo", "OtherClusion", "GeographicalCoverage"],
            "DemographicInfo": ["Sex", "Age"],
            "GeographicalCoverage": ["Nation", "FranceRegion", "GeoDetail"],
            "AdministrativeInformation": ["RegulatoryRequirements", "IsContributorPI", "PrimaryInvestigator", "AddTeamMember", "TeamMember", "ContactPoint", "FundingAgent", "OrganisationGovernance"],
            "RegulatoryRequirements": ["ObtainedAuthorization"],
            "ObtainedAuthorization": ["AuthorizingAgency", "OtherAuthorizingAgency"],
            "PrimaryInvestigator": ["PIName", "PIMail", "PIORCID", "PIIdRef", "PIAffiliation", "IsPIContact"],
            "PIAffiliation": ["OrganisationName", "OrganisationPID", "PILabo", "PILaboId"],
            "TeamMember": ["TeamMemberName", "TeamMemberORCID", "TeamMemberIdRef", "TeamMemberAffiliation", "TeamMemberLabo", "TeamMemberLaboId", "IsTeamMemberContact"],
            "TeamMemberAffiliation": ["OrganisationName", "OrganisationPID"],
            "ContactPoint": ["ContactName", "EMail", "ContactPointAffiliation"],
            "ContactPointAffiliation": ["OrganisationName", "OrganisationPID", "ContactPointLabo", "ContactPointLaboId"],
            "FundingAgent": ["FundingAgentName", "FundingAgentType", "OtherFundingAgentType", "FundingAgentPID"],
            "OrganisationGovernance": ["Sponsor", "Governance", "Collaborations"],
            "Sponsor": ["SponsorName", "SponsorType", "OtherSponsorType", "SponsorPID"],
            "Governance": ["Committee", "CommitteeDetail", "OtherGovernance"],
            "Collaborations": ["NetworkConsortium", "CollaborationsDetail"],
            "StudyMethodology": ["AnalysisUnit", "ResearchType", "InterventionalStudy", "ObservationalStudy", "TimePerspective"],
            "InterventionalStudy": ["IsClinicalTrial", "TrialPhase", "ResearchPurpose", "OtherResearchPurpose", "IsInclusionGroups", "InclusionGroup", "InterventionalStudyModel", "Allocation", "Masking", "Arm", "Intervention"],
            "InclusionGroup": ["GroupName", "GroupDescription"],
            "Intervention": ["InterventionName", "InterventionType", "InterventionTypeOther", "InterventionDescritption"],
            "DataCollectionAccess": ["DataCollectionIntegration", "DataAccess"],
            "DataCollectionIntegration": ["SampleSize", "CollectionChronology", "DataCollection", "IsDataIntegration", "ConformityDeclaration", "ThirdPartySource", "SourcePurpose", "OtherSourceType"],
            "SampleSize": ["PlannedSampleSize", "FinalSampleSize"],
            "CollectionChronology": ["CollectionStart", "CollectionEnd", "CollectionFrequency"],
            "DataCollection": ["CollectionProcess", "RecruitmentSource", "RecruitmentSourceOther", "ActiveFollowUp", "DataTypes", "InclusionStrategy", "InclusionStrategyOther", "SamplingMode", "SamplingModeOther"],
            "ActiveFollowUp": ["IsActiveFollowUp", "FollowUpMode", "FollowUpModeOther"],
            "DataTypes": ["DataType", "ClinicalDataDetails", "ParaclinicalDataDetails", "BiologicalDataDetails", "isDataInBiobank", "BiobankContent", "BiobankContentOther", "OtherLiquidsDetails"],
            "ThirdPartySource": ["SourceName", "SourceId", "SourceType"],
            "DataAccess": ["DataQuality", "DataAvailability", "UseStatement", "DataInformationContact", "DataCitation", "VariableDictionnary", "MockSample", "OtherDocumentation", "DatasetPID"],
            "DataQuality": ["UsedStandards", "QualityProcedure"],
            "DataAvailability": ["IndividualDataAccess", "AggregatedDataAccess", "DataAccessRequestTool", "DataAccessRequestToolLocation"],
            "UseStatement": ["AccessConditions", "AccessRestrictions", "AdditionalDataAccessLink", "NonDisclosureAgreement"],
            "DataInformationContact": ["DIContactName", "DIContactMail"],
            "DataCitation": ["DataCitationRequirement", "DataCitationStatement"],
            "VariableDictionnary": ["VariableDictionnaryAvailable", "VariableDictionnaryDetails"],
            "MockSample": ["MockSampleAvailable", "MockSampleLocation"],
            "DatasetIDType": ["IDSchema", "Identifier"],
            
            # Formats stricts (Value TOUJOURS avant URI)
            "Pathology": ["value", "URI"],
            "Sex": ["value", "URI"],
            "Age": ["value", "URI"],
            "Status": ["value", "URI"],
            "DataType": ["value", "URI"],
            "OrganisationPID": ["PIDSchema", "value", "URI"],
            "FundingAgentPID": ["PIDSchema", "value", "URI"],
            "SponsorPID": ["PIDSchema", "value", "URI"],
            "Nation": ["value", "URI"]
        }

    def _split_bracket_list(self, raw_text):
        """Transforme un faux tableau Python en texte "['a','b']" en vraie liste de strings."""
        if not raw_text:
            return []
        text = raw_text.strip()
        if text.startswith('[') and text.endswith(']'):
            inner = text[1:-1]
            items = inner.split("','")
            return [i.strip().strip("'").strip('"') for i in items if i.strip().strip("'").strip('"')]
        return [text]

    def _get_sorted_keys(self, parent_tag, keys):
        if parent_tag in self.schema_hierarchy:
            order = self.schema_hierarchy[parent_tag]
            return sorted(keys, key=lambda x: order.index(x) if x in order else 999)
        return keys

    def build_tree(self, data_dict):
        root = ET.Element("FreshSchema", attrib=self.ns_map)
        self._dict_to_xml(root, data_dict, "FreshSchema")
        self._enforce_mandatory_dummy_nodes(root)
        return root

    def _dict_to_xml(self, parent_element, data, parent_tag=None):
        if isinstance(data, dict):
            sorted_keys = self._get_sorted_keys(parent_tag, list(data.keys()))
            for key in sorted_keys:
                value = data[key]
                
                # --- IGNORER LES VALEURS VIDES POUR ÉVITER LES ERREURS XSD ---
                if value == "":
                    continue 
                    
                if isinstance(value, list):
                    for item in value:
                        if item == "": continue
                        child = ET.SubElement(parent_element, key)
                        self._dict_to_xml(child, item, key)
                else:
                    child = ET.SubElement(parent_element, key)
                    self._dict_to_xml(child, value, key)
        elif data is not None:
            if str(data).strip():
                parent_element.text = str(data).strip()

    def _enforce_mandatory_dummy_nodes(self, root):
        """Comble les balises manquantes exigées par le schéma XSD en respectant l'ordre."""
        
        # 1. Validation Responsable par défaut
        for tech in root.iter('TechnicalInfo'):
            if tech.find('RespValidation') is None:
                idx = list(tech).index(tech.find('AutoTranslation')) if tech.find('AutoTranslation') is not None else len(tech)
                el = ET.Element('RespValidation')
                el.text = "0"
                tech.insert(idx, el)
                
        # 2. Contributeur (obligatoire)
        for tech in root.iter('TechnicalInfo'):
            if tech.find('MetadataContributor') is None:
                mc = ET.SubElement(tech, 'MetadataContributor')
                ET.SubElement(mc, 'ContributorName').text = "Inconnu"

        # 3. Type de Financeur (Enumération obligatoire)
        for fa in root.iter('FundingAgent'):
            if fa.find('FundingAgentType') is None:
                ET.SubElement(fa, 'FundingAgentType').text = "Autre"

        # 4. Type de Promoteur (Enumération obligatoire)
        for sp in root.iter('Sponsor'):
            if sp.find('SponsorType') is None:
                ET.SubElement(sp, 'SponsorType').text = "Autre"

        # 5. Mode de suivi (Obligatoire si la balise ActiveFollowUp existe)
        for af in root.iter('ActiveFollowUp'):
            if af.find('FollowUpMode') is None:
                ET.SubElement(af, 'FollowUpMode').text = "Autre"

                
        # 7. Détail Collaborations
        for col in root.iter('Collaborations'):
            if col.find('CollaborationsDetail') is None:
                ET.SubElement(col, 'CollaborationsDetail').text = "Non renseigné"

        # 8. Post-processing des JSON Complexes (CollectionMode et SamplingMode)
        import ast, json
        
        for cp in root.iter('CollectionProcess'):
            # --- Traitement des Modes de Collecte ---
            for raw_node in cp.findall('CollectionModeRaw'):
                raw_text = raw_node.text
                if raw_text:
                    clean_json_str = raw_text.replace('\n', ' ').replace('\r', '')
                    try:
                        j_dict = json.loads(clean_json_str)
                        cm = ET.Element('CollectionMode')
                        if "value" in j_dict:
                            raw_val = ' '.join(j_dict["value"].split())
                            ET.SubElement(cm, 'value').text = resolve_vocab_term('CollectionMode', raw_val, self.unmatched_vocab)
                        if "concept" in j_dict and "vocabURI" in j_dict["concept"]:
                            ET.SubElement(cm, 'URI').text = j_dict["concept"]["vocabURI"]
                        
                        idx = list(cp).index(raw_node)
                        cp.insert(idx, cm)
                    except Exception:
                        pass
                cp.remove(raw_node)
                
            # --- Traitement des Modes d'Échantillonnage ---
            raw_sample = cp.find('SamplingModeRaw')
            if raw_sample is not None:
                raw_text = raw_sample.text
                if raw_text:
                    # 1. On retire les sauts de ligne toxiques
                    clean_str = raw_text.replace('\n', ' ').replace('\r', '')
                    
                    # 2. Le coup de génie : on transforme ['...'] en vrai JSON [...]
                    clean_json_array = clean_str.replace("['", "[").replace("']", "]").replace("','", ",").replace("', '", ",")
                    
                    try:
                        # Maintenant c'est du vrai JSON pur, insensible aux apostrophes !
                        parsed_list = json.loads(clean_json_array)
                        insert_idx = list(cp).index(raw_sample)
                        
                        # parsed_list est déjà une liste de dictionnaires, plus besoin de json.loads sur chaque item
                        if isinstance(parsed_list, list):
                            for j_dict in parsed_list:
                                sm = ET.Element('SamplingMode')
                                if "value" in j_dict:
                                    raw_val = ' '.join(j_dict["value"].split())
                                    ET.SubElement(sm, 'value').text = resolve_vocab_term('SamplingMode', raw_val, self.unmatched_vocab)
                                if "concept" in j_dict and "vocabURI" in j_dict["concept"]:
                                    ET.SubElement(sm, 'URI').text = j_dict["concept"]["vocabURI"]
                                
                                cp.insert(insert_idx, sm)
                                insert_idx += 1
                        else:
                            # Si pour une raison étrange ce n'est pas une liste
                            sm = ET.Element('SamplingMode')
                            ET.SubElement(sm, 'value').text = str(parsed_list)
                            cp.insert(insert_idx, sm)
                    except Exception:
                        pass
                cp.remove(raw_sample)
        
        
        # 9. Coup de balai final : supprimer les OrganisationPID vides
        for parent in root.iter():
            to_remove = []
            for child in parent:
                if child.tag == 'OrganisationPID' and len(child) == 0 and not child.text:
                    to_remove.append(child)
            for child in to_remove:
                parent.remove(child)
        
        # 10. Post-processing pour ObtainedAuthorization (Gestion multiple et tableaux parallèles)
        for req in root.iter('RegulatoryRequirements'):
            agencies = req.findall('AgencyRaw')
            others = req.findall('OtherAgencyRaw')
            
            new_auth_nodes = []
            
            # On boucle avec l'index "i" pour faire correspondre l'agence et sa précision
            for i, agency_node in enumerate(agencies):
                agency_val = agency_node.text.strip() if agency_node.text else None
                
                if agency_val:
                    agency_val = resolve_vocab_term('AuthorizingAgency', agency_val, self.unmatched_vocab)
                    auth_node = ET.Element('ObtainedAuthorization')
                    ET.SubElement(auth_node, 'AuthorizingAgency').text = agency_val

                    # On n'ajoute OtherAuthorizingAgency QUE si c'est "Autre"
                    if agency_val == "Autre":
                        # On récupère la valeur au même index dans la liste "others"
                        if i < len(others) and others[i].text and others[i].text.strip():
                            other_val = ' '.join(others[i].text.split()) # On nettoie les espaces
                            ET.SubElement(auth_node, 'OtherAuthorizingAgency').text = other_val
                            
                    new_auth_nodes.append(auth_node)
            
            # On insère les belles balises construites dans le XML
            for node in reversed(new_auth_nodes):
                req.insert(0, node) # insert(0) pour les mettre au début de RegulatoryRequirements
                
            # Coup de balai : on supprime les balises Raw
            for a in agencies: req.remove(a)
            for o in others: req.remove(o)
        
        
        # 10.5 Post-processing pour IndividualDataAccess (décodage du JSON)
        import json
        for da in root.iter('DataAvailability'):
            raw_node = da.find('IndividualDataAccessRaw')
            if raw_node is not None:
                raw_text = raw_node.text
                if raw_text:
                    clean_json = raw_text.replace('\n', ' ').replace('\r', '')
                    try:
                        j_dict = json.loads(clean_json)
                        ida_node = ET.Element('IndividualDataAccess')
                        
                        # Extraction de la valeur
                        if "value" in j_dict:
                            raw_val = ' '.join(j_dict["value"].split())
                            ET.SubElement(ida_node, 'value').text = resolve_vocab_term('IndividualDataAccess', raw_val, self.unmatched_vocab)
                            
                        # Extraction de l'URI (prise en compte de 'extLink' ou 'ext Link')
                        ext_link = j_dict.get("extLink") or j_dict.get("ext Link")
                        if ext_link and "uri" in ext_link:
                            ET.SubElement(ida_node, 'URI').text = ext_link["uri"].strip()
                            
                        # On insère à la place du Raw
                        idx = list(da).index(raw_node)
                        da.insert(idx, ida_node)
                    except Exception:
                        # Fallback de sécurité si ce n'est pas un JSON valide (juste du texte)
                        ida_node = ET.Element('IndividualDataAccess')
                        ET.SubElement(ida_node, 'value').text = resolve_vocab_term('IndividualDataAccess', raw_text.strip(), self.unmatched_vocab)
                        idx = list(da).index(raw_node)
                        da.insert(idx, ida_node)
                        
                da.remove(raw_node)
        
        # 10.6 Conversion booléenne pour DataAccessRequestToolAvailable ("Oui" -> "1", "Non" -> "0")
        for tool_avail in root.iter('DataAccessRequestToolAvailable'):
            if tool_avail.text:
                val = tool_avail.text.strip().lower()
                if val in ['oui', 'yes', 'true', '1']:
                    tool_avail.text = '1'
                elif val in ['non', 'no', 'false', '0']:
                    tool_avail.text = '0'
        
        # 10.7 Nettoyage automatique des valeurs textuelles (Enums XSD)
        
        # -1. Nettoyage de ResearchType (détection par mot-clé dans un texte parfois bruité,
        #     puis passage par le vocabulaire contrôlé pour l'orthographe exacte)
        for rt in root.iter('ResearchType'):
            if rt.text:
                val = rt.text.lower()
                if "observationnelle" in val:
                    rt.text = resolve_vocab_term('ResearchType', 'Etude observationnelle', self.unmatched_vocab)
                elif "interventionnelle" in val:
                    rt.text = resolve_vocab_term('ResearchType', 'Etude interventionnelle (expérimentale)', self.unmatched_vocab)

        # -2. ConformityDeclaration est déjà normalisé via le vocabulaire contrôlé à l'extraction
        #     (HierarchicalExtractor._clean_value) ; pas de retraitement ici.

        # -3. Si c'est observationnel, on détruit les résidus interventionnels envoyés par erreur par l'API
        for sm in root.iter('StudyMethodology'):
            rt = sm.find('ResearchType')
            if rt is not None and rt.text == 'Etude observationnelle':
                interv = sm.find('InterventionalStudy')
                if interv is not None:
                    sm.remove(interv)
        
        # 10.8 Traitement du "faux tableau" pour DataTypeRaw
        for dt_container in root.iter('DataTypes'):
            raw_node = dt_container.find('DataTypeRaw')
            if raw_node is not None and raw_node.text:
                raw_text = raw_node.text.strip()
                # On vérifie s'il y a des crochets
                if raw_text.startswith('[') and raw_text.endswith(']'):
                    # On enlève les crochets au début et à la fin
                    clean_str = raw_text[1:-1]
                    # On découpe en utilisant "','", ce qui évite de casser sur les apostrophes normales comme "l'étude"
                    items = clean_str.split("','")
                    for item in items:
                        # On nettoie les guillemets et apostrophes restants sur les bords
                        clean_item = item.strip().strip("'").strip('"')
                        if clean_item:
                            new_node = ET.Element('DataType')
                            new_node.text = resolve_vocab_term('DataType', clean_item, self.unmatched_vocab)
                            dt_container.append(new_node)
                else:
                    # Cas classique : pas de crochets, on garde le texte tel quel
                    new_node = ET.Element('DataType')
                    new_node.text = resolve_vocab_term('DataType', raw_text, self.unmatched_vocab)
                    dt_container.append(new_node)
                
                # On supprime la balise Raw
                dt_container.remove(raw_node)
                
        
        # 10.9 Traitement des faux tableaux : UsedStandards, QualityProcedure, RecruitmentSource
        for dq in root.iter('DataQuality'):
            raw = dq.find('UsedStandardsRaw')
            if raw is not None:
                for val in self._split_bracket_list(raw.text):
                    new_node = ET.Element('UsedStandards')
                    new_node.text = val
                    dq.append(new_node)
                dq.remove(raw)

            raw = dq.find('QualityProcedureRaw')
            if raw is not None:
                for val in self._split_bracket_list(raw.text):
                    new_node = ET.Element('QualityProcedure')
                    new_node.text = val
                    dq.append(new_node)
                dq.remove(raw)

        for dc in root.iter('DataCollection'):
            raw = dc.find('RecruitmentSourceRaw')
            if raw is not None:
                for val in self._split_bracket_list(raw.text):
                    new_node = ET.Element('RecruitmentSource')
                    new_node.text = resolve_vocab_term('RecruitmentSource', val, self.unmatched_vocab)
                    dc.append(new_node)
                dc.remove(raw)
                                    
        # 11. Réorganisation stricte (XSD Sorter) globale
        
        # Ordre TechnicalInfo
        ti_order = ['StudyId', 'VersionLang', 'OriginLang', 'CreationDate', 'LastUpdatedAuto', 'LastUpdatedManual', 'RespValidation', 'AutoTranslation', 'Status', 'DatasetPersistentID', 'MetadataContributor']
        for ti in root.iter('TechnicalInfo'):
            children = list(ti)
            children.sort(key=lambda x: ti_order.index(x.tag) if x.tag in ti_order else 999)
            ti[:] = children

        # Ordre StudyOverview
        so_order = ['Title', 'Acronym', 'StudyStatus', 'Purpose', 'Summary', 'Keyword', 'RelatedDocument']
        for so in root.iter('StudyOverview'):
            children = list(so)
            children.sort(key=lambda x: so_order.index(x.tag) if x.tag in so_order else 999)
            so[:] = children

        # Ordre DataTypes (avec correction de la majuscule "isDataInBiobank")
        dt_order = [
            'DataType', 'DataTypeOther', 'ClinicalDataDetails', 'BiologicalDataDetails', 
            'isDataInBiobank', 'BiobankContent', 'BiobankContentOther', 
            'OtherLiquidsDetails', 'ParaclinicalDataOther'
        ]
        for dt in root.iter('DataTypes'):
            children = list(dt)
            children.sort(key=lambda x: dt_order.index(x.tag) if x.tag in dt_order else 999)
            dt[:] = children

        # Ordre DataQuality
        dq_order = ['UsedStandards', 'QualityProcedure']
        for dq in root.iter('DataQuality'):
            children = list(dq)
            children.sort(key=lambda x: dq_order.index(x.tag) if x.tag in dq_order else 999)
            dq[:] = children

        # Ordre DataCollection (RecruitmentSource est reconstruit après ActiveFollowUp/DataTypes, il faut le replacer)
        dc_order = self.schema_hierarchy["DataCollection"]
        for dc_el in root.iter('DataCollection'):
            children = list(dc_el)
            children.sort(key=lambda x: dc_order.index(x.tag) if x.tag in dc_order else 999)
            dc_el[:] = children

        # Ordre DataAvailability
        dav_order = ['IndividualDataAccess', 'AggregatedDataAccess', 'DataAccessRequestTool', 'DataFileCompleteness', 'DataLocation']
        for dav in root.iter('DataAvailability'):
            children = list(dav)
            children.sort(key=lambda x: dav_order.index(x.tag) if x.tag in dav_order else 999)
            dav[:] = children

        # Ordre UseStatement (avec AdditionalDataAccessLink)
        us_order = ['AccessConditions', 'AccessRestrictions', 'AdditionalDataAccessLink', 'NonDisclosureAgreement', 'DataInformationContact']
        for us in root.iter('UseStatement'):
            children = list(us)
            children.sort(key=lambda x: us_order.index(x.tag) if x.tag in us_order else 999)
            us[:] = children

        # Ordre DataAccess (avec DataCitation correctement placé)
        da_order = ['DataQuality', 'DataAvailability', 'UseStatement', 'DataCitation', 'VariableDictionary', 'MockSample', 'OtherDocumentation', 'DatasetPID']
        for da in root.iter('DataAccess'):
            children = list(da)
            children.sort(key=lambda x: da_order.index(x.tag) if x.tag in da_order else 999)
            da[:] = children

        # Ordre RelatedDocument (Le XSD veut le Titre, puis le Lien, puis le Type)
        rd_order = ['DocumentType', 'DocumentTitle', 'DocumentLink']
        for rd in root.iter('RelatedDocument'):
            children = list(rd)
            children.sort(key=lambda x: rd_order.index(x.tag) if x.tag in rd_order else 999)
            rd[:] = children
                


    def save_xml(self, root_element, output_path):
        # Utilise le formateur natif de Python au lieu de minidom (plus rapide et robuste)
        if hasattr(ET, 'indent'):
            ET.indent(root_element, space="    ", level=0)
            
        tree = ET.ElementTree(root_element)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        # print(f"Successfully saved FReSH XML to: {output_path}") # Ligne optionnelle