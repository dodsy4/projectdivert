import random
import pandas as pd

random.seed(42)

CATEGORY_COUNTS = {
    "Charity": 1137,
    "Direct Recycling": 439,
    "Landfill": 114,
    "Reprocessor": 97,
    "MRF": 44,
    "Other": 27,
    "EFW": 12,
    "Recyling via MRF": 6,
    "Recycling facility": 5,
    "Take-Back Scheme": 1,
    "Manufacturer": 1,
}

CITIES = [
    ("London", 51.5074, -0.1278), ("Manchester", 53.4808, -2.2426),
    ("Birmingham", 52.4862, -1.8904), ("Leeds", 53.8008, -1.5491),
    ("Bristol", 51.4545, -2.5879), ("Sheffield", 53.3811, -1.4701),
    ("Liverpool", 53.4084, -2.9916), ("Newcastle", 54.9783, -1.6178),
    ("Nottingham", 52.9548, -1.1581), ("Southampton", 50.9097, -1.4044),
    ("Reading", 51.4543, -0.9781), ("Coventry", 52.4068, -1.5197),
]

WORD_A = ["Green", "Northern", "Metro", "Capital", "Riverside", "Summit", "Oak", "Bright",
          "Union", "Prime", "Civic", "Harbour", "Meadow", "Vale", "Crest"]
WORD_B = ["Recycling", "Reclaim", "Materials", "Resource", "Waste Solutions", "Environmental",
          "Salvage", "Reuse", "Circular", "Logistics"]
CHARITY_A = ["Hope", "Second Chance", "New Leaf", "Bridge", "Compass", "Lighthouse", "Haven",
             "Forward", "Together", "Steppingstone"]
CHARITY_B = ["Furniture Project", "Community Trust", "Reuse Store", "Support Network",
             "Foundation", "Charity Shop", "Outreach"]

rows = []
i = 0
for category, count in CATEGORY_COUNTS.items():
    for _ in range(count):
        city, base_lat, base_lng = random.choice(CITIES)
        lat = round(base_lat + random.uniform(-0.15, 0.15), 7)
        lng = round(base_lng + random.uniform(-0.15, 0.15), 7)

        if category == "Charity":
            name = f"{random.choice(CHARITY_A)} {random.choice(CHARITY_B)} ({city})"
            domain = "example-charity.org"
        else:
            name = f"{random.choice(WORD_A)} {random.choice(WORD_B)} {i % 97}"
            domain = "example-supplier.co.uk"

        slug = name.lower().replace(" ", ".").replace("(", "").replace(")", "")
        email = f"contact.{i}@{domain}"
        telephone = f"0{random.randint(1000, 9999)} {random.randint(100000, 999999)}"
        postcode = f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(1,9)} {random.randint(1,9)}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"

        rows.append({
            "Unnamed: 0": i,
            "sup_type": category,
            "name": name,
            "address_street": f"{random.randint(1, 200)} Sample Street",
            "city": city,
            "postcode": postcode,
            "lat": lat,
            "long": lng,
            "website": f"https://www.{domain}",
            "email": email,
            "telephone": telephone,
            "supplier_contact": "",
            "supplier_contact_email": "",
            "supplier_contact_telephone": "",
            "percent_recyclablenum": round(random.uniform(0, 100), 1) if random.random() > 0.6 else "",
            "percent_efwnum": "",
            "provides_a_rebateyn": random.choice([0, 1]),
            "supplier_auditislist_yes_no_na": "",
            "supplier_audit_date_completed": "",
            "notes": "",
            "hierarchy": "Reuse" if category == "Charity" else "",
            "origin": "synthetic_sample_data",
        })
        i += 1

df = pd.DataFrame(rows)
df.to_csv("data/df3.csv", index=False)
print("Wrote", len(df), "synthetic supplier rows to data/df3.csv")
