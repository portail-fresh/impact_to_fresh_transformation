import os
import re
import copy
import xml.etree.ElementTree as ET
from src.vocabularies import resolve_vocab_term

# ArmType isn't a string enum: the schema models it as 5 required booleans (one
# per arm-type category), so the CSV's raw ArmType.csv term has to be turned
# into "this one flag is 1, the rest are 0" rather than emitted as text. Values
# with no matching flag (e.g. "Autre") legitimately leave all 5 at "0" --
# ArmTypeOther carries the free-text detail in that case.
ARM_TYPE_BOOL_FIELDS = ["ExperimentalArm", "ActiveComparatorArm", "PlaceboComparatorArm", "SharmComparatorArm", "NoInterventionArm"]
ARM_TYPE_BOOL_MAP = {
    "fr": {
        "Expérimental": "ExperimentalArm",
        "Comparateur actif": "ActiveComparatorArm",
        "Comparateur placebo": "PlaceboComparatorArm",
        "Comparateur fictif": "SharmComparatorArm",
        "Sans intervention": "NoInterventionArm",
    },
    "en": {
        "Experimental": "ExperimentalArm",
        "Active Comparator": "ActiveComparatorArm",
        "Placebo Comparator": "PlaceboComparatorArm",
        "Sham Comparator": "SharmComparatorArm",
        "No intervention": "NoInterventionArm",
    },
}

class FReSHXMLBuilder:
    def __init__(self, lang="fr"):
        self.lang = lang
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
            "AdministrativeInformation": ["RegulatoryRequirements", "IsContributorPI", "PrimaryInvestigator", "AddTeamMember", "TeamMember", "ContactPoint", "FundingAgent", "OrganisationGovernance", "OtherStudyId"],
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
            "StudyMethodology": ["AnalysisUnit", "ResearchType", "InterventionalStudy", "ObservationalStudy"],
            "InterventionalStudy": ["IsClinicalTrial", "TrialPhase", "ResearchPurpose", "OtherResearchPurpose", "IsInclusionGroups", "InclusionGroup", "InterventionalStudyModel", "Allocation", "Masking", "Arm", "Intervention"],
            "Arm": ["ArmName", "ArmType", "ArmTypeOther", "ArmDescription"],
            "ObservationalStudy": ["ObservationalStudyDesign", "OtherResearchTypeDetails", "TimePerspective", "IsInclusionGroups", "InclusionGroup", "Intervention"],
            "InclusionGroup": ["GroupName", "GroupDescription"],
            "Intervention": ["InterventionName", "InterventionType", "InterventionTypeOther", "InterventionDescritption"],
            "DataCollectionAccess": ["DataCollectionIntegration", "DataAccess"],
            "DataCollectionIntegration": ["SampleSize", "CollectionChronology", "DataCollection", "IsDataIntegration", "ConformityDeclaration", "ThirdPartySource"],
            "ThirdPartySource": ["SourceName", "SourceId", "SourceType", "SourcePurpose", "OtherSourceType"],
            "SampleSize": ["PlannedSampleSize", "FinalSampleSize"],
            "CollectionChronology": ["CollectionStart", "CollectionEnd", "CollectionFrequency"],
            "DataCollection": ["CollectionProcess", "RecruitmentSource", "RecruitmentSourceOther", "ActiveFollowUp", "DataTypes", "InclusionStrategy", "InclusionStrategyOther", "SamplingMode", "SamplingModeOther"],
            "ActiveFollowUp": ["IsActiveFollowUp", "FollowUpMode", "FollowUpModeOther"],
            "DataTypes": ["DataType", "ClinicalDataDetails", "ParaclinicalDataOther", "BiologicalDataDetails", "isDataInBiobank", "BiobankContent", "BiobankContentOther", "OtherLiquidsDetails"],
            "ThirdPartySource": ["SourceName", "SourceId", "SourceType"],
            "DataAccess": ["DataQuality", "DataAvailability", "UseStatement", "DataInformationContact", "DataCitation", "VariableDictionary", "MockSample", "OtherDocumentation", "DatasetPID"],
            "DataQuality": ["UsedStandards", "QualityProcedure"],
            "DataAvailability": ["IndividualDataAccess", "AggregatedDataAccess", "DataAccessRequestTool", "DataAccessRequestToolLocation"],
            "UseStatement": ["AccessConditions", "AccessRestrictions", "AdditionalDataAccessLink", "NonDisclosureAgreement"],
            "DataInformationContact": ["DIContactName", "DIContactMail"],
            "DataCitation": ["DataCitationRequirement", "DataCitationStatement"],
            "VariableDictionary": ["VariableDictionaryAvailable", "VariableDictionaryLink"],
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
        # Read by fresh-schema_v4.xsd's XSD 1.1 Conditional Type Assignment to
        # pick the French or English enumeration for every controlled-vocab
        # field (inherited down the whole tree, no need to repeat it).
        root.set("{http://www.w3.org/XML/1998/namespace}lang", self.lang)
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
                        # These "*Raw" fields keep blank placeholders: they're paired
                        # by position (enumerate) further down, so dropping an empty
                        # entry here would desync it from its sibling list.
                        if item == "" and key not in ("AgencyRaw", "OtherAgencyRaw", "FundingAgentTypeRaw", "SponsorTypeRaw", "OtherSourceTypeRaw"):
                            continue
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

        # 0. TeamMember fantôme : l'API source joint firstname+";"+lastname même
        # quand les deux sont vides, ce qui donne un <name>;</name> littéral --
        # non-vide pour notre pipeline, mais sans aucun contenu réel (pas
        # d'affiliation, pas d'ORCID...). On le supprime plutôt que de fabriquer
        # un TeamMemberAffiliation factice juste pour satisfaire le schéma.
        for admin_info in root.iter('AdministrativeInformation'):
            for tm in list(admin_info.findall('TeamMember')):
                name_el = tm.find('TeamMemberName')
                name_text = name_el.text.strip() if name_el is not None and name_el.text else ""
                if re.fullmatch(r'[;,\s]*', name_text) and tm.find('TeamMemberAffiliation') is None:
                    admin_info.remove(tm)

        # 2. Contributeur (obligatoire)
        for tech in root.iter('TechnicalInfo'):
            if tech.find('MetadataContributor') is None:
                mc = ET.SubElement(tech, 'MetadataContributor')
                ET.SubElement(mc, 'ContributorName').text = "Inconnu"

        # 2.1 OtherClusion (obligatoire, même vide -- ses enfants InclusionCriterion/
        # ExclusionCriterion sont optionnels, mais l'élément lui-même ne l'est pas)
        for pop in root.iter('Population'):
            if pop.find('OtherClusion') is None:
                demo_el = pop.find('DemographicInfo')
                idx = list(pop).index(demo_el) + 1 if demo_el is not None else len(pop)
                pop.insert(idx, ET.Element('OtherClusion'))

        # 2.5 FundingAgentType / SponsorType : listes PARALLELES (chemin séparé dans le
        # XML source de l'API, sans lien de parenté avec funding_agency/producer),
        # appariées par position avec FundingAgent / Sponsor respectivement.
        for admin_info in root.iter('AdministrativeInformation'):
            funders = admin_info.findall('FundingAgent')
            type_raws = admin_info.findall('FundingAgentTypeRaw')
            for i, funder in enumerate(funders):
                if i < len(type_raws) and type_raws[i].text and type_raws[i].text.strip():
                    type_val = resolve_vocab_term('FundingAgentType', type_raws[i].text.strip(), self.lang, self.unmatched_vocab)
                    name_el = funder.find('FundingAgentName')
                    idx = list(funder).index(name_el) + 1 if name_el is not None else 0
                    el = ET.Element('FundingAgentType')
                    el.text = type_val
                    funder.insert(idx, el)
            for raw in type_raws:
                admin_info.remove(raw)

            for governance in admin_info.iter('OrganisationGovernance'):
                sponsors = governance.findall('Sponsor')
                sponsor_type_raws = governance.findall('SponsorTypeRaw')
                for i, sponsor in enumerate(sponsors):
                    if i < len(sponsor_type_raws) and sponsor_type_raws[i].text and sponsor_type_raws[i].text.strip():
                        type_val = resolve_vocab_term('SponsorType', sponsor_type_raws[i].text.strip(), self.lang, self.unmatched_vocab)
                        name_el = sponsor.find('SponsorName')
                        idx = list(sponsor).index(name_el) + 1 if name_el is not None else 0
                        el = ET.Element('SponsorType')
                        el.text = type_val
                        sponsor.insert(idx, el)
                for raw in sponsor_type_raws:
                    governance.remove(raw)

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
                            ET.SubElement(cm, 'value').text = resolve_vocab_term('CollectionMode', raw_val, self.lang, self.unmatched_vocab)
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
                                    ET.SubElement(sm, 'value').text = resolve_vocab_term('SamplingMode', raw_val, self.lang, self.unmatched_vocab)
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
                    agency_val = resolve_vocab_term('AuthorizingAgency', agency_val, self.lang, self.unmatched_vocab)
                    auth_node = ET.Element('ObtainedAuthorization')
                    ET.SubElement(auth_node, 'AuthorizingAgency').text = agency_val

                    # On n'ajoute OtherAuthorizingAgency QUE si c'est "Autre"/"Other"
                    if agency_val in ("Autre", "Other"):
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
                            ET.SubElement(ida_node, 'value').text = resolve_vocab_term('IndividualDataAccess', raw_val, self.lang, self.unmatched_vocab)
                            
                        # Extraction de l'URI (prise en compte de 'extLink' ou 'ext Link')
                        ext_link = j_dict.get("extLink") or j_dict.get("ext Link")
                        if ext_link and ext_link.get("uri", "").strip():
                            ET.SubElement(ida_node, 'URI').text = ext_link["uri"].strip()
                            
                        # On insère à la place du Raw
                        idx = list(da).index(raw_node)
                        da.insert(idx, ida_node)
                    except Exception:
                        # Fallback de sécurité si ce n'est pas un JSON valide (juste du texte)
                        ida_node = ET.Element('IndividualDataAccess')
                        ET.SubElement(ida_node, 'value').text = resolve_vocab_term('IndividualDataAccess', raw_text.strip(), self.lang, self.unmatched_vocab)
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
        observational_keyword, interventional_keyword, observational_term, interventional_term = (
            ("observational", "interventional", "Observational Study", "Interventional Study")
            if self.lang == "en" else
            ("observationnelle", "interventionnelle", "Etude observationnelle", "Etude interventionnelle (expérimentale)")
        )
        for rt in root.iter('ResearchType'):
            if rt.text:
                val = rt.text.lower()
                if observational_keyword in val:
                    rt.text = resolve_vocab_term('ResearchType', observational_term, self.lang, self.unmatched_vocab)
                elif interventional_keyword in val:
                    rt.text = resolve_vocab_term('ResearchType', interventional_term, self.lang, self.unmatched_vocab)

        # -2. ConformityDeclaration est déjà normalisé via le vocabulaire contrôlé à l'extraction
        #     (HierarchicalExtractor._clean_value) ; pas de retraitement ici.

        # -3. On ne garde que la branche StudyMethodology correspondant au ResearchType
        # final : InterventionalStudy et ObservationalStudy sont mappés en parallèle
        # depuis les mêmes champs source (isInclusionGroups, intervention/item...),
        # donc l'une des deux est toujours un résidu à détruire.
        for sm in root.iter('StudyMethodology'):
            rt = sm.find('ResearchType')
            if rt is None:
                continue
            if rt.text == observational_term:
                interv = sm.find('InterventionalStudy')
                if interv is not None:
                    sm.remove(interv)
            elif rt.text == interventional_term:
                obs = sm.find('ObservationalStudy')
                if obs is not None:
                    sm.remove(obs)
        
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
                            new_node.text = resolve_vocab_term('DataType', clean_item, self.lang, self.unmatched_vocab)
                            dt_container.append(new_node)
                else:
                    # Cas classique : pas de crochets, on garde le texte tel quel
                    new_node = ET.Element('DataType')
                    new_node.text = resolve_vocab_term('DataType', raw_text, self.lang, self.unmatched_vocab)
                    dt_container.append(new_node)
                
                # On supprime la balise Raw
                dt_container.remove(raw_node)

        # 10.82 ArmType : décomposition en 5 booléens requis (voir ARM_TYPE_BOOL_MAP)
        for arm in root.iter('Arm'):
            raw_node = arm.find('ArmTypeRaw')
            if raw_node is None:
                continue
            raw_text = raw_node.text.strip() if raw_node.text else ""
            arm.remove(raw_node)
            if not raw_text:
                continue

            canonical = resolve_vocab_term('ArmType', raw_text, self.lang, self.unmatched_vocab)
            matched_field = ARM_TYPE_BOOL_MAP.get(self.lang, {}).get(canonical)

            arm_type_el = ET.Element('ArmType')
            for field_name in ARM_TYPE_BOOL_FIELDS:
                ET.SubElement(arm_type_el, field_name).text = "1" if field_name == matched_field else "0"

            # ArmType comes right after ArmName in the XSD sequence, regardless
            # of where ArmTypeRaw happened to land during the initial dict->XML
            # sort (it wasn't a known key in schema_hierarchy's "Arm" order).
            name_el = arm.find('ArmName')
            idx = list(arm).index(name_el) + 1 if name_el is not None else 0
            arm.insert(idx, arm_type_el)

        # 10.85 ThirdPartySource : SourceType n'est pas répétable dans un seul
        # ThirdPartySource, mais un <source> source peut avoir plusieurs <srcorig>
        # (donc plusieurs SourceTypeRaw). Chaque valeur devient son propre
        # ThirdPartySource, dupliquant SourceName/SourceId/SourcePurpose.
        for dci in root.iter('DataCollectionIntegration'):
            # OtherSourceTypeRaw: separate parallel list (like FundingAgentTypeRaw),
            # one entry per original <source> node, matched by position -- attached
            # before fan-out so deepcopy carries it onto every cloned ThirdPartySource.
            other_source_type_raws = dci.findall('OtherSourceTypeRaw')
            for i, tps in enumerate(list(dci.findall('ThirdPartySource'))):
                raw_nodes = tps.findall('SourceTypeRaw')
                if not raw_nodes:
                    continue
                type_vals = []
                for raw_node in raw_nodes:
                    if raw_node.text and raw_node.text.strip():
                        type_vals.append(resolve_vocab_term('SourceType', raw_node.text.strip(), self.lang, self.unmatched_vocab))
                    tps.remove(raw_node)

                if not type_vals:
                    dci.remove(tps)
                    continue

                source_id_el = tps.find('SourceId')
                idx = list(tps).index(source_id_el) + 1 if source_id_el is not None else 0
                type_el = ET.Element('SourceType')
                type_el.text = type_vals[0]
                tps.insert(idx, type_el)

                if i < len(other_source_type_raws) and other_source_type_raws[i].text and other_source_type_raws[i].text.strip():
                    ET.SubElement(tps, 'OtherSourceType').text = other_source_type_raws[i].text.strip()

                insert_idx = list(dci).index(tps)
                for extra_val in reversed(type_vals[1:]):
                    clone = copy.deepcopy(tps)
                    clone.find('SourceType').text = extra_val
                    dci.insert(insert_idx + 1, clone)

            for raw in other_source_type_raws:
                dci.remove(raw)

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
                    new_node.text = resolve_vocab_term('RecruitmentSource', val, self.lang, self.unmatched_vocab)
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
            'DataType', 'DataTypeOther', 'ClinicalDataDetails', 'ParaclinicalDataOther', 'BiologicalDataDetails',
            'isDataInBiobank', 'BiobankContent', 'BiobankContentOther',
            'OtherLiquidsDetails'
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