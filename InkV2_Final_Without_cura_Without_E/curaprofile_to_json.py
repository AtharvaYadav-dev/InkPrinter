import zipfile
import configparser
import json
import argparse
import io
import os

def parse_curaprofile(path):
    if not zipfile.is_zipfile(path):
        raise ValueError(" The file is not a valid .curaprofile ZIP archive")

    result = {}
    with zipfile.ZipFile(path, 'r') as z:
        for name in z.namelist():
            # Each inner file (custom_ink-test1, custom_extruder_1_#2_ink-test1, etc.)
            if not name.lower().startswith("custom"):
                continue

            with z.open(name) as f:
                text = f.read().decode("utf-8", errors="replace")

            config = configparser.ConfigParser()
            config.read_string(text)

            # Extract the profile name (e.g., 'custom_extruder_1_#2_ink-test1')
            key = name.replace("#", "").replace(".cfg", "")

            # Store values
            if "values" in config:
                result[key] = dict(config["values"])

    if not result:
        raise ValueError(" No valid [values] sections found inside profile.")

    return result


def convert_curaprofile_to_json(input_path, output_path=None):
    data = parse_curaprofile(input_path)
    json_data = json.dumps(data, indent=4, ensure_ascii=False)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_data)
        print(f" JSON profile saved to: {os.path.abspath(output_path)}")
    else:
        print(json_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Cura 5.x .curaprofile to JSON")
    parser.add_argument("--input", required=True, help="Path to Cura .curaprofile")
    parser.add_argument("--output", help="Path to save JSON output")
    args = parser.parse_args()

    convert_curaprofile_to_json(args.input, args.output)
