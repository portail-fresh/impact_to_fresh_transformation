from lxml import etree # type: ignore

def validate_xml_against_xsd(xml_path, xsd_path):
    """
    Valide un fichier XML par rapport à un schéma XSD en utilisant lxml.
    
    Outputs:
    - is_valid (bool): True si le XML est conforme, False sinon.
    - error_log (str ou None): Le journal des erreurs détaillé si la validation échoue.
    """
    try:
        # 1. Charger et compiler le fichier XSD
        print(f"   [XSD] Analyse du schéma : {xsd_path}")
        xsd_doc = etree.parse(xsd_path)
        xml_schema = etree.XMLSchema(xsd_doc)
        
        # 2. Charger le fichier XML généré pour validation
        xml_doc = etree.parse(xml_path)
        
        # 3. Exécuter la validation
        is_valid = xml_schema.validate(xml_doc)
        
        if is_valid:
            return True, None
        else:
            # Récupérer et formater le journal des erreurs de lxml
            return False, xml_schema.error_log
            
    except etree.XMLSyntaxError as e:
        return False, f"Erreur de syntaxe XML dans le fichier généré : {e}"
    except etree.XMLSchemaParseError as e:
        return False, f"Erreur d'analyse du schéma XSD : {e}"
    except Exception as e:
        return False, f"Erreur inattendue lors de la validation : {e}"