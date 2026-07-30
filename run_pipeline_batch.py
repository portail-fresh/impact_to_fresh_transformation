# %%
import os
import glob
from run_pipeline import run_transformation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_fr_files(data_dir, study_ids=None):
    """Files are named e.g. FRESH-PEF100-en.xml / FRESH-PEF100-fr.xml. A plain
    'fr' substring check would also match the 'FRESH' prefix on every file, so
    filter on the '-fr.xml' language suffix instead.

    If study_ids is given, only the '-fr' files whose name contains one of
    those ids (case-insensitive) are kept -- e.g. "43597" matches
    "FReSH-43597-fr.xml", "PEF3476" matches "FReSH-PEF3476-fr.xml". Without
    study_ids, every '-fr' file in data_dir is returned."""
    all_xml = glob.glob(os.path.join(data_dir, "*.xml"))
    fr_files = sorted(f for f in all_xml if f.lower().endswith("-fr.xml"))
    if study_ids is None:
        return fr_files
    wanted = [str(study_id).strip().lower() for study_id in study_ids]
    return [f for f in fr_files if any(w in os.path.basename(f).lower() for w in wanted)]


def run_batch(data_dir, output_dir, logs_dir, mapping_csv_path, xsd_schema_path, study_ids=None):
    fr_files = find_fr_files(data_dir, study_ids=study_ids)

    print(f"Found {len(fr_files)} 'fr' file(s) in {data_dir}\n")

    succeeded, failed = [], []
    warnings_count = 0
    for input_xml_path in fr_files:
        file_name = os.path.splitext(os.path.basename(input_xml_path))[0]
        print(f"=== {file_name} ===")
        try:
            run_transformation(
                input_xml_path=input_xml_path,
                mapping_csv_path=mapping_csv_path,
                xsd_schema_path=xsd_schema_path,
                output_xml_path=os.path.join(output_dir, f"{file_name}_fresh_clean.xml"),
                logs_path=logs_dir,
            )
            succeeded.append(file_name)
        except Exception as e:
            print(f"   [ERROR] {e}")
            failed.append(file_name)
        print()

    print(f"Done: {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed files:")
        for name in failed:
            print(f"   - {name}")

    # count warnings
    # print(f"Total warnings: {warnings_count}")
    

if __name__ == "__main__":
    data_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\data\\xml_files_from_IH_API"
    output_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\data\\xml_files_out_IH_to_FRESH"
    logs_dir = "C:\\Users\\remy.ben-messaoud\\Documents\\python_local_projects\\xml_processing_home\\data\\IH_to_FRESH_logs"

    # Leave as None to process every '-fr' study found in data_dir. To run only
    # a subset, list the ids to include instead, e.g.:
    # study_ids = ["43597", "PEF3476", "PEF60139", "PEF73375", "PEF74055"]
    study_ids = None

    run_batch(
        data_dir=data_dir,
        output_dir=output_dir,
        logs_dir=logs_dir,
        mapping_csv_path=os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv"),
        xsd_schema_path=os.path.join(BASE_DIR, "mappings", "fresh-schema_v5.xsd"),
        study_ids=study_ids,
    )
# %%
