from lxml import etree # type: ignore

class APIExtractor:
    def __init__(self, xml_file_path):
        self.tree = etree.parse(xml_file_path)
        self.namespaces = {} 

    def get_value(self, xpath):
        try:
            # This returns a list of ALL matching elements
            elements = self.tree.xpath(xpath, namespaces=self.namespaces)
            
            if not elements:
                return None
                
            # Extract text from all matches
            results = []
            for elem in elements:
                if isinstance(elem, str):
                    text = elem.strip()
                else:
                    text = elem.text.strip() if elem.text else ""
                
                if text:  # Only add non-empty strings
                    results.append(text)
            
            # If there's only one item, return it as a simple string
            # If there are multiple, return the whole list
            if len(results) == 1:
                return results[0]
            elif len(results) > 1:
                return results
                
            return None
            
        except etree.XPathEvalError as e:
            print(f"Warning: Invalid XPath '{xpath}' - {e}")
            return None