# Validates generated FReSH XML against the target XSD schema.
# Uses the `xmlschema` package (XSD 1.1 aware) rather than lxml/libxml2, which
# only implements XSD 1.0 and cannot check the Conditional Type Assignment
# (`xsd:alternative`) used by fresh-schema_v4.xsd for bilingual FR/EN vocab.
import xmlschema

def validate_xml_against_xsd(xml_path, xsd_path):
    """
    Valide un fichier XML par rapport à un schéma XSD (XSD 1.1, via xmlschema).

    Outputs:
    - is_valid (bool): True si le XML est conforme, False sinon.
    - error_log (str ou None): Le message d'erreur (première violation rencontrée) si échec.
    """
    try:
        print(f"   [XSD] Analyse du schéma : {xsd_path}")
        schema = xmlschema.XMLSchema11(xsd_path)

        # NB: iter_errors() defaults to validation='lax', which silently skips
        # content it can't resolve unambiguously instead of flagging it (this
        # let an invalid nested AllocationUnit value through undetected).
        # Passing validation='strict' to iter_errors() avoids that blind spot,
        # but in 'strict' mode this library raises on the first error from
        # inside the traversal itself (not as a yielded value), so it can't
        # be collected into a list -- use validate() directly instead, which
        # is exactly this raise-on-first-error behavior, wrapped here to
        # report just that first error rather than crashing the pipeline.
        schema.validate(xml_path)
        return True, None

    except xmlschema.XMLSchemaValidationError as e:
        return False, str(e)
    except xmlschema.XMLSchemaParseError as e:
        return False, f"Erreur d'analyse du schéma XSD : {e}"
    except Exception as e:
        return False, f"Erreur inattendue lors de la validation : {e}"
