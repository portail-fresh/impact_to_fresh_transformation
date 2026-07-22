import pandas as pd

def load_mapping_table(csv_path):
    """
    Loads the correspondence table and returns a dictionary mapping.
    Format: { '/xml/dataset/metadata/.../title': '/FreshSchema/StudyRelatedInfo/StudyOverview/Title' }
    """
    # Assuming columns are 'source_xpath' and 'target_xpath'
    df = pd.read_csv(csv_path)
    
    # Drop empty mappings where the colleague hasn't found a match yet
    df = df.dropna(subset=['target_xpath'])
    
    # Convert to a dictionary for fast lookups during transformation
    mapping_dict = dict(zip(df['source_xpath'], df['target_xpath']))
    
    return mapping_dict