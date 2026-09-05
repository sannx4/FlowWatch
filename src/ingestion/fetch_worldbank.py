import json
from pathlib import Path

import requests


URL = (
    "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice"
    "?datasetId=DS00976"
    "&resourceId=RS00906"
    "&top=100"
    "&type=json"
)

OUTPUT_PATH = Path("data/raw/world_bank_sample.json")


def fetch_sample() -> None:
    print("Fetching 100 World Bank records...")

    response = requests.get(URL, timeout=30)
    response.raise_for_status()

    data = response.json()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    print(f"Sample saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    fetch_sample()