"""Seed script for Firestore destinations collection."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-e4d70b5363d0"
COLLECTION_NAME = "destinations"

INITIAL_DESTINATIONS = [
    {
        "id": "san-francisco",
        "name": "San Francisco",
        "country": "United States",
        "category": "Coastal & Culture",
        "description": "Iconic bay views, historic cable cars, foggy hills, and culinary excellence.",
        "recommended_days": 3,
        "budget_tier": "$$$",
        "highlights": [
            "Golden Gate Bridge",
            "Alcatraz Island",
            "Fisherman's Wharf",
            "Chinatown",
        ],
    },
    {
        "id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Historic & Zen",
        "description": "Ancient temples, serene bamboo groves, traditional tea houses, and seasonal gardens.",
        "recommended_days": 4,
        "budget_tier": "$$",
        "highlights": [
            "Fushimi Inari Shrine",
            "Kinkaku-ji (Golden Pavilion)",
            "Arashiyama Bamboo Grove",
            "Gion District",
        ],
    },
    {
        "id": "paris",
        "name": "Paris",
        "country": "France",
        "category": "Art & Culinary",
        "description": "World-class art museums, cafe culture, architectural landmarks, and romantic boulevards.",
        "recommended_days": 5,
        "budget_tier": "$$$$",
        "highlights": [
            "Eiffel Tower",
            "Louvre Museum",
            "Notre-Dame Cathedral",
            "Montmartre",
        ],
    },
    {
        "id": "reykjavik",
        "name": "Reykjavik",
        "country": "Iceland",
        "category": "Adventure & Nature",
        "description": "Gateway to geothermal hot springs, volcanic landscapes, and spectacular Northern Lights.",
        "recommended_days": 4,
        "budget_tier": "$$$",
        "highlights": [
            "Blue Lagoon",
            "Golden Circle",
            "Hallgrímskirkja",
            "Northern Lights Tour",
        ],
    },
    {
        "id": "cape-town",
        "name": "Cape Town",
        "country": "South Africa",
        "category": "Scenic & Coastal",
        "description": "Dramatic mountain backdrops, pristine beaches, vibrant vineyards, and wildlife encounters.",
        "recommended_days": 5,
        "budget_tier": "$$",
        "highlights": [
            "Table Mountain",
            "Cape of Good Hope",
            "Robben Island",
            "Boulders Beach Penguins",
        ],
    },
]


def seed_database():
    """Seeds the Firestore database with initial destination catalog items."""
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    print(f"Seeding Firestore collection '{COLLECTION_NAME}' in project '{PROJECT_ID}'...")
    for item in INITIAL_DESTINATIONS:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"  ✓ Seeded destination: {item['name']} ({doc_id})")

    print("Firestore seeding complete!")


if __name__ == "__main__":
    seed_database()
