import json
from models import Person, Link, PopoloCollection
from resolver import evaluate_social_candidate


def main():
    # Sample input PEP seed data
    pep_records = [
        {
            "id": "pep-001",
            "name": "Jane Smith",
            "given_name": "Jane",
            "family_name": "Smith",
            "role": "Minister of Environment",
            "official_website": "https://environment.gov.example/ministers/janesmith",
            "candidates": [
                {
                    "platform": "twitter",
                    "url": "https://x.com/janesmith_env",
                    "data": {
                        "profile_name": "Jane Smith MP",
                        "bio": "Minister of Environment | Advocating for sustainability",
                        "is_verified": True,
                        "linked_from_official_site": True
                    }
                },
                {
                    "platform": "linkedin",
                    "url": "https://www.linkedin.com/in/janesmith-pol",
                    "data": {
                        "profile_name": "Jane Smith",
                        "bio": "Public servant and policymaker",
                        "is_verified": False,
                        "linked_from_official_site": False
                    }
                }
            ]
        },
        {
            "id": "pep-002",
            "name": "Carlos Gomez",
            "given_name": "Carlos",
            "family_name": "Gomez",
            "role": "Senator",
            "official_website": "https://senate.gov.example/members/cgomez",
            "candidates": [
                {
                    "platform": "facebook",
                    "url": "https://facebook.com/carlosgomez.senator",
                    "data": {
                        "profile_name": "Carlos Gomez Fan Page",
                        "bio": "News and updates",
                        "is_verified": False,
                        "linked_from_official_site": False
                    }
                }
            ]
        }
    ]

    collection = PopoloCollection()

    for item in pep_records:
        person = Person(
            id=item["id"],
            name=item["name"],
            given_name=item.get("given_name"),
            family_name=item.get("family_name"),
            links=[Link(url=item["official_website"], note="Official Government Website")] if item.get("official_website") else []
        )
        
        for cand in item.get("candidates", []):
            contact = evaluate_social_candidate(
                person_name=person.name,
                target_role=item.get("role", ""),
                platform=cand["platform"],
                candidate_url=cand["url"],
                profile_data=cand["data"]
            )
            person.contact_details.append(contact)

        collection.persons.append(person)

    # Save to Popolo JSON output file
    output_path = "popolo_pep_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(collection.model_dump_json(indent=2))

    print(f"Successfully exported Popolo PEP dataset with confidence scores to '{output_path}'.")


if __name__ == "__main__":
    main()
