"""
Gujarati-origin name pools for the UniAssist synthetic dataset.

PDEU / PDPU (School of Technology) sits in Gandhinagar, Gujarat, so students,
faculty and admins are given names drawn from Gujarati usage. Surnames are the
common Gujarati family names; given-name pools lean modern for students (the
17-22 age band) and are mixed-generation for staff.

Sources consulted while building these pools:
  - forebears.io "Most common forenames in Gujarat"
  - momjunction / NESTA TOYS "modern Gujarati baby names"
  - Wikipedia "Category:Gujarati-language surnames", surnamelist.in
Everything here is a hand-curated list; nothing is scraped at runtime.

Helper functions take an explicit `random.Random` so generation stays
deterministic under the caller's fixed seed.
"""

from __future__ import annotations

import random

# ---------------------------------------------------------------------------
# Surnames — common Gujarati family names (Patidar, Vania/Jain, Brahmin,
# Rajput/Kshatriya, Lohana, artisan castes, Parsi occupational, Christian).
# ---------------------------------------------------------------------------
SURNAMES = [
    # Patidar / Patel cluster
    "Patel", "Amin", "Desai", "Kachhadiya", "Savani", "Vekariya", "Dhaduk",
    "Kalariya", "Ramani", "Kanani", "Godhani", "Hirpara", "Bhalodia", "Sojitra",
    "Vachhani", "Dobariya", "Ghodasara", "Kacha", "Lakhani", "Ganatra",
    # Vania / Jain merchant
    "Shah", "Mehta", "Doshi", "Vora", "Kapadia", "Sheth", "Jhaveri", "Sanghvi",
    "Parekh", "Kothari", "Gandhi", "Modi", "Chokshi", "Thakkar", "Zaveri",
    "Kadakia", "Munshi", "Bakshi", "Nanavati", "Choksi",
    # Brahmin
    "Joshi", "Trivedi", "Dave", "Pandya", "Vyas", "Bhatt", "Raval", "Pathak",
    "Purohit", "Acharya", "Upadhyay", "Adhvaryu", "Shukla", "Antani", "Jani",
    "Thaker", "Buch", "Oza", "Rawal",
    # Rajput / Kshatriya
    "Parmar", "Solanki", "Chauhan", "Vaghela", "Zala", "Jadeja", "Gohil",
    "Rathod", "Chudasama", "Sarvaiya", "Dabhi", "Chavda", "Barot", "Rana",
    # Lohana / Bhanushali / others
    "Thakkar", "Kotak", "Rajyaguru", "Bhanushali", "Karia", "Sodha",
    # Artisan / OBC occupational
    "Prajapati", "Suthar", "Mistry", "Panchal", "Luhar", "Soni", "Darji",
    "Valand", "Chunara", "Gajjar", "Sompura", "Bhavsar", "Ratanpara",
    # Parsi / Christian occupational
    "Contractor", "Engineer", "Merchant", "Dalal", "Christian", "Macwan",
    "Parmar", "Rathod",
]

# ---------------------------------------------------------------------------
# Student given names — modern Gujarati, 2004-2009 birth cohort.
# ---------------------------------------------------------------------------
STUDENT_MALE = [
    "Aarav", "Aayush", "Aditya", "Advait", "Akshat", "Aman", "Aniket", "Ankit",
    "Ankur", "Arjun", "Aryan", "Bhavya", "Chirag", "Darshan", "Dev", "Devarsh",
    "Dhairya", "Dhruv", "Dhruvil", "Dhruvin", "Harsh", "Harshil", "Hardik",
    "Hemang", "Het", "Hitarth", "Jainam", "Jainil", "Jash", "Jay", "Jeel",
    "Jenil", "Kalp", "Karan", "Kavan", "Kenil", "Keval", "Krish", "Krunal",
    "Kunj", "Kush", "Malhar", "Manan", "Meet", "Mihir", "Milan", "Mit", "Neel",
    "Nihar", "Nikunj", "Nilay", "Nisarg", "Om", "Parth", "Pranav", "Preet",
    "Priyansh", "Raj", "Rishabh", "Rishi", "Ronak", "Rudra", "Sahil", "Samarth",
    "Sarthak", "Shivam", "Shubham", "Smit", "Soham", "Tirth", "Utsav", "Vatsal",
    "Ved", "Vraj", "Yash", "Yug", "Vivek", "Krish", "Manav", "Naitik", "Deep",
]

STUDENT_FEMALE = [
    "Aarohi", "Aashka", "Aditi", "Aesha", "Ananya", "Anjali", "Ankita", "Avani",
    "Bhoomi", "Charmi", "Darshana", "Dhara", "Dhruvi", "Diya", "Drashti",
    "Devanshi", "Dinal", "Foram", "Freya", "Gauri", "Grishma", "Heena",
    "Hetvi", "Hiral", "Hardika", "Isha", "Ishita", "Janvi", "Janki",
    "Jenisha", "Jiya", "Kavya", "Kesha", "Khushi", "Krisha", "Krupa", "Kruti",
    "Mahi", "Manasi", "Mansi", "Mira", "Mitali", "Nidhi", "Nikita", "Niharika",
    "Nishtha", "Palak", "Pooja", "Prachi", "Priya", "Rachana", "Riddhi", "Riya",
    "Ruchi", "Rutvi", "Sakshi", "Shivani", "Shreya", "Tanvi", "Tvisha", "Urvi",
    "Vandana", "Vidhi", "Yesha", "Zeel", "Zankhana", "Twinkle", "Aayushi",
    "Bansari", "Disha", "Kinjal", "Nandini",
]

# ---------------------------------------------------------------------------
# Staff given names — wider generational range for faculty / admins
# (1960s-1990s birth cohort), so a few more traditional entries.
# ---------------------------------------------------------------------------
STAFF_MALE = STUDENT_MALE + [
    "Amit", "Ashish", "Ashok", "Bhavesh", "Chetan", "Dilip", "Girish",
    "Hardik", "Hiren", "Jignesh", "Kalpesh", "Ketan", "Kirit", "Mahesh",
    "Manish", "Mehul", "Nilesh", "Paresh", "Pradip", "Rajesh", "Rakesh",
    "Sanjay", "Sunil", "Tushar", "Vijay", "Vipul", "Bharat", "Naresh",
    "Prakash", "Ramesh", "Yogesh", "Alpesh", "Devang", "Nikhil", "Parag",
]

STAFF_FEMALE = STUDENT_FEMALE + [
    "Alka", "Bhavna", "Daksha", "Falguni", "Geeta", "Hansa", "Hina", "Jagruti",
    "Jyoti", "Kokila", "Lata", "Meena", "Nayana", "Nita", "Pallavi", "Rekha",
    "Sadhana", "Seema", "Sejal", "Shilpa", "Trupti", "Varsha", "Bhakti",
    "Purnima", "Rashmi", "Sonal", "Urmila",
]


def _pick(rng: random.Random, pool: list[str]) -> str:
    return pool[rng.randrange(len(pool))]


def student_name(rng: random.Random, gender: str) -> tuple[str, str]:
    first = _pick(rng, STUDENT_MALE if gender == "Male" else STUDENT_FEMALE)
    return first, _pick(rng, SURNAMES)


def staff_name(rng: random.Random, gender: str) -> tuple[str, str]:
    first = _pick(rng, STAFF_MALE if gender == "Male" else STAFF_FEMALE)
    return first, _pick(rng, SURNAMES)


def guardian_first_name(rng: random.Random) -> str:
    """A parent-generation given name, either gender."""
    pool = STAFF_MALE if rng.random() < 0.7 else STAFF_FEMALE
    return _pick(rng, pool)


# ---------------------------------------------------------------------------
# Home towns — Gujarat-weighted, with a minority from the rest of India
# (PDEU does admit out-of-state students, but the bulk are Gujarati).
# ---------------------------------------------------------------------------
GUJARAT_CITIES = [
    ("Ahmedabad", "Gujarat"), ("Surat", "Gujarat"), ("Vadodara", "Gujarat"),
    ("Rajkot", "Gujarat"), ("Bhavnagar", "Gujarat"), ("Jamnagar", "Gujarat"),
    ("Gandhinagar", "Gujarat"), ("Junagadh", "Gujarat"), ("Anand", "Gujarat"),
    ("Nadiad", "Gujarat"), ("Mehsana", "Gujarat"), ("Morbi", "Gujarat"),
    ("Surendranagar", "Gujarat"), ("Bharuch", "Gujarat"), ("Navsari", "Gujarat"),
    ("Vapi", "Gujarat"), ("Valsad", "Gujarat"), ("Porbandar", "Gujarat"),
    ("Gondal", "Gujarat"), ("Botad", "Gujarat"), ("Palanpur", "Gujarat"),
    ("Patan", "Gujarat"), ("Godhra", "Gujarat"), ("Dahod", "Gujarat"),
    ("Amreli", "Gujarat"), ("Veraval", "Gujarat"), ("Bhuj", "Gujarat"),
    ("Gandhidham", "Gujarat"), ("Ankleshwar", "Gujarat"), ("Deesa", "Gujarat"),
    ("Jetpur", "Gujarat"), ("Kalol", "Gujarat"), ("Modasa", "Gujarat"),
    ("Himatnagar", "Gujarat"), ("Wadhwan", "Gujarat"), ("Mandvi", "Gujarat"),
]

OTHER_CITIES = [
    ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"), ("Jaipur", "Rajasthan"),
    ("Udaipur", "Rajasthan"), ("Jodhpur", "Rajasthan"), ("Indore", "Madhya Pradesh"),
    ("Bhopal", "Madhya Pradesh"), ("Delhi", "Delhi"), ("Bengaluru", "Karnataka"),
    ("Hyderabad", "Telangana"), ("Nagpur", "Maharashtra"), ("Nashik", "Maharashtra"),
    ("Kota", "Rajasthan"), ("Raipur", "Chhattisgarh"), ("Lucknow", "Uttar Pradesh"),
]


def home_town(rng: random.Random) -> tuple[str, str]:
    if rng.random() < 0.86:
        return GUJARAT_CITIES[rng.randrange(len(GUJARAT_CITIES))]
    return OTHER_CITIES[rng.randrange(len(OTHER_CITIES))]
