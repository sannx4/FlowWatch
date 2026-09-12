import json
from pathlib import Path


DATA_PATH = Path("data/raw/world_bank_sample.json")


def load_records():
    with DATA_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    print(f"Top-level Python type: {type(payload).__name__}")

    if isinstance(payload, dict):
        print(f"Top-level keys: {list(payload.keys())}")

        records = payload.get("data", [])
    elif isinstance(payload, list):
        records = payload
    else:
        raise ValueError("Unexpected JSON structure")

    return records


def explore():
    records = load_records()

    print(f"\nNumber of sample records: {len(records)}")

    if not records:
        print("No records found.")
        return

    print("\nFields in one record:")
    for field in sorted(records[0].keys()):
        print(f"  - {field}")

    print("\nSample identity:")
    first = records[0]

    for field in [
        "country",
        "country_code",
        "region",
        "project_id",
        "project_name",
        "credit_number",
        "credit_status",
        "end_of_period",
        "disbursed_amount_us_",
    ]:
        print(f"{field}: {first.get(field)}")

    print("\nDistinct values in sample:")
    for field in [
        "country",
        "project_id",
        "credit_number",
        "end_of_period",
    ]:
        values = {
            record.get(field)
            for record in records
            if record.get(field) is not None
        }

        print(f"{field}: {len(values)} distinct values")


if __name__ == "__main__":
    explore()