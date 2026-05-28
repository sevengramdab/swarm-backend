import csv
import json
import sys

def convert_csv_to_json(csv_file, json_file):
    data = []
    reader = csv.DictReader(open(csv_file))
    for row in reader:
        data.append(row)
    
    with open(json_file, 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python main.py <input_csv> <output_json>")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_json = sys.argv[2]

    convert_csv_to_json(input_csv, output_json)