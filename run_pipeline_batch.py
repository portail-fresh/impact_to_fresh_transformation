# %%
import os
import glob
from run_pipeline import run_transformation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_files_by_suffix(data_dir, suffix, study_ids=None):
    """Files are named e.g. FRESH-PEF100-en.xml / FRESH-PEF100-fr.xml. A plain
    'fr'/'en' substring check would also match the 'FRESH' prefix or other
    parts of the name, so filter on the language suffix ('-fr.xml'/'-en.xml')
    instead.

    If study_ids is given, only files whose name contains one of those ids
    (case-insensitive) are kept -- e.g. "43597" matches "FReSH-43597-fr.xml",
    "PEF3476" matches "FReSH-PEF3476-fr.xml". Without study_ids, every file
    with the given suffix in data_dir is returned."""
    all_xml = glob.glob(os.path.join(data_dir, "*.xml"))
    matched = sorted(f for f in all_xml if f.lower().endswith(suffix))
    if study_ids is None:
        return matched
    wanted = [str(study_id).strip().lower() for study_id in study_ids]
    return [f for f in matched if any(w in os.path.basename(f).lower() for w in wanted)]


def find_fr_files(data_dir, study_ids=None):
    """French ('-fr.xml') source files -- see _find_files_by_suffix."""
    return _find_files_by_suffix(data_dir, "-fr.xml", study_ids=study_ids)


def find_en_files(data_dir, study_ids=None):
    """English ('-en.xml') source files -- see _find_files_by_suffix."""
    return _find_files_by_suffix(data_dir, "-en.xml", study_ids=study_ids)


def run_batch(data_dir, output_dir, logs_dir, mapping_csv_path, xsd_schema_path, study_ids=None):
    """Processes every '-fr' and '-en' source file in data_dir (or, if
    study_ids is given, only the ones matching those ids) -- so with
    study_ids=None, every study in both languages gets processed."""
    files = find_fr_files(data_dir, study_ids=study_ids) + find_en_files(data_dir, study_ids=study_ids)
    files.sort()

    print(f"Found {len(files)} file(s) in {data_dir}\n")

    succeeded, failed = [], []
    warnings_count = 0
    for input_xml_path in files:
        file_name = os.path.splitext(os.path.basename(input_xml_path))[0]
        print(f"=== {file_name} ===")
        try:
            run_transformation(
                input_xml_path=input_xml_path,
                mapping_csv_path=mapping_csv_path,
                xsd_schema_path=xsd_schema_path,
                output_xml_path=os.path.join(output_dir, f"{file_name}_clean.xml"),
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
    # Les chemins etaient ecrits en dur vers le poste d'un collegue, donc le
    # script ne demarrait chez personne d'autre sans etre edite. Ils pointent
    # desormais par defaut sur les dossiers du depot, et chacun peut les changer
    # en ligne de commande sans toucher au fichier.
    import argparse

    parser = argparse.ArgumentParser(
        description="Convertit toutes les fiches d'un dossier (fr et en) du format "
                    "source vers le format FReSH.")
    parser.add_argument("--data-dir", default=os.path.join(BASE_DIR, "data", "input"),
                        help="dossier des fiches source (defaut : data/input)")
    parser.add_argument("--output-dir", default=os.path.join(BASE_DIR, "data", "output"),
                        help="dossier des XML produits (defaut : data/output)")
    parser.add_argument("--logs-dir", default=os.path.join(BASE_DIR, "data", "logs"),
                        help="dossier des journaux et rapports (defaut : data/logs)")
    parser.add_argument("--study-ids", nargs="*", default=None,
                        help="ne traiter que ces etudes, p.ex. --study-ids 43597 PEF3476 ; "
                             "sans cette option, tout le dossier est traite")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.logs_dir, exist_ok=True)

    run_batch(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        logs_dir=args.logs_dir,
        mapping_csv_path=os.path.join(BASE_DIR, "mappings", "entity_wise_corres_table.csv"),
        xsd_schema_path=os.path.join(BASE_DIR, "mappings", "fresh-schema_v6.xsd"),
        study_ids=args.study_ids,
    )
