import csv
import json

def csv_to_json(csv_file, json_file):
    with open(csv_file, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        data = [row for row in reader]

    with open(json_file, 'w') as jsonfile:
        json.dump(data, jsonfile, indent=4)

def main():
    import sys
    if len(sys.argv) != 3:
        print("Usage: python converter.py <input_csv> <output_json>")
        return

    csv_file = sys.argv[1]
    json_file = sys.argv[2]

    try:
        csv_to_json(csv_file, json_file)
        print(f"CSV to JSON conversion successful. Output saved in {json_file}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()