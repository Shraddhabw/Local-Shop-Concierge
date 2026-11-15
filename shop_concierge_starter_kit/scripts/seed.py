"""Seed 3 demo shops (demo-salon, demo-tutor, demo-repair). Safe to re-run: replaces them.

Usage: python scripts/seed.py [--db PATH]
Facts here must match eval/cases.json seed_fact fields. Do NOT add anything a seed_fact
says is not offered (no physics, no laptop repair, no tattoos, no rebonding, no discounts).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, global_lookups as g, repo  # noqa: E402

WEEK = range(7)

SHOPS = {
    "demo-salon": {
        "name": "Glow Salon", "address": "21 MG Road, Pune", "phone": "+91 98765 43210",
        "services": [
            ("Men's Haircut", 300, 30, "Wash and style included", "haircut men cut"),
            ("Women's Haircut", 600, 45, "Cut and blow dry", "haircut women cut"),
            ("Kids Haircut", 250, 25, "For children under 12", "haircut kids child"),
            ("Classic Facial", 900, 45, "Deep cleansing facial", "facial skin"),
            ("Bridal Makeup", 8000, 120, "Includes a free trial session", "bridal wedding makeup"),
            ("Party Makeup", 2500, 60, "Evening and party looks", "makeup party"),
            ("Hair Colour", 1800, 90, "Global colour with branded products", "colour color dye"),
            ("Head Massage", 400, 20, "Relaxing oil massage", "massage oil"),
            ("Manicure", 500, 40, "Nail shaping and polish", "nails manicure"),
            ("Pedicure", 700, 50, "Foot care and polish", "nails pedicure"),
        ],
        "hours": {**{d: ("10:00", "20:00") for d in range(6)}, 6: ("10:00", "17:00")},
        "faqs": [
            ("Do you take walk-ins?", "Yes, walk-ins are welcome, but booked appointments get priority.", "walkin appointment"),
            ("Which payment methods do you accept?", "We accept UPI, cards and cash.", "upi card cash payment"),
            ("Do I need to book an appointment?", "Booking is recommended for weekends and bridal services. Call or WhatsApp us.", "book appointment"),
            ("Is parking available?", "Yes, there is free parking in front of the salon.", "parking"),
            ("Which products do you use?", "We use branded, skin-tested products.", "products brand"),
            ("How early should I arrive?", "Please arrive 10 minutes before your slot.", "arrive early late"),
            ("Do you do bridal packages?", "Yes, our bridal makeup includes a free trial session. Call us to plan your date.", "bridal package wedding"),
            ("Can I reschedule my appointment?", "Yes, please let us know at least 3 hours before your slot.", "reschedule cancel"),
            ("Do you serve both men and women?", "Yes, we welcome men, women and children.", "men women gender unisex"),
            ("Is the salon hygienic?", "All tools are sanitised after every customer.", "hygiene clean sanitise"),
        ],
    },
    "demo-tutor": {
        "name": "Bright Minds Tuition", "address": "5 Station Road, Nashik", "phone": "+91 91234 56789",
        "services": [
            ("Class 10 Maths Batch", 1500, None, "Fee per month, small batch of 10 students", "class 10 maths math tenth"),
            ("Class 10 Science Batch", 1500, None, "Fee per month", "class 10 science tenth"),
            ("Class 9 Maths Batch", 1300, None, "Fee per month", "class 9 maths math ninth"),
            ("Class 12 Maths Batch", 2000, None, "Fee per month", "class 12 maths math twelfth"),
            ("Class 12 Chemistry Batch", 2000, None, "Fee per month", "class 12 chemistry twelfth"),
            ("Class 8 All Subjects", 1200, None, "Fee per month", "class 8 all subjects eighth"),
            ("English Speaking Course", 1000, None, "Fee per month, weekend batch", "english speaking spoken"),
            ("Exam Revision Crash Course", 2500, None, "Two-week course before exams", "revision crash exam"),
            ("One to One Doubt Class", 400, 60, "Price per hour", "doubt private one-to-one"),
        ],
        "hours": {**{d: ("16:00", "20:00") for d in range(5)}, 5: ("09:00", "13:00"), 6: None},
        "faqs": [
            ("Do you offer a free demo class?", "Yes, the first demo class is free. Come and try before you join.", "demo trial free"),
            ("What are the weekday batch timings?", "Weekday batches run 6:00 pm to 8:00 pm.", "batch timings weekday evening"),
            ("What is the batch size?", "Each batch has at most 10 students.", "batch size students"),
            ("How are fees paid?", "Fees are paid monthly by UPI, cash or bank transfer.", "fee pay upi cash"),
            ("Do you share study material?", "Yes, notes and practice sheets are included in the fee.", "notes material sheets"),
            ("Do you take tests?", "We hold a short test every Saturday and share progress with parents.", "test exam progress parents"),
            ("Do you teach the CBSE syllabus?", "Yes, our classes follow the CBSE syllabus.", "cbse syllabus board"),
            ("Can I join in the middle of the month?", "Yes, fees are adjusted for the remaining weeks.", "join admission mid month"),
            ("Do you have a weekend batch?", "Yes, the English Speaking Course runs on Saturday mornings.", "weekend saturday batch"),
            ("Where is the classroom?", "We are at 5 Station Road, Nashik, near the bus stand.", "classroom location address"),
        ],
    },
    "demo-repair": {
        "name": "QuickFix Mobile Repair", "address": "8 Market Street, Nagpur", "phone": "+91 99887 76655",
        "services": [
            ("iPhone Screen Replacement", 3500, 60, "Original quality screen", "iphone screen display glass"),
            ("Android Screen Replacement", 2200, 60, "Most popular brands", "android screen display glass"),
            ("Battery Replacement", 1500, 30, "New battery fitted while you wait", "battery drain charging"),
            ("Charging Port Repair", 800, 45, "Fixes loose or dead charging ports", "charging port usb"),
            ("Speaker and Mic Repair", 700, 40, "Fixes low or no sound", "speaker mic sound audio"),
            ("Camera Repair", 1800, 60, "Front and back camera", "camera lens"),
            ("Water Damage Inspection", 300, 30, "Inspection fee; the repair quote is given after inspection", "water liquid damage inspection"),
            ("Software Update and Reset", 400, 30, "Update, reset or remove slow apps", "software update reset slow"),
            ("Screen Guard Fitting", 200, 10, "Tempered glass fitted", "guard tempered glass protector"),
        ],
        "hours": {**{d: ("10:00", "19:00") for d in range(6)}, 6: None},
        "faqs": [
            ("Do you give a warranty on repairs?", "Yes, there is a 3 month warranty on all repairs.", "warranty guarantee"),
            ("How long does a battery replacement take?", "Battery replacement takes about 30 minutes.", "battery time"),
            ("Can you fix a phone that fell in water?", "Bring it in quickly and do not charge it. Water damage inspection costs 300 and the repair quote is given after inspection.", "water damage liquid"),
            ("Do I need an appointment?", "No, walk-ins are welcome. Most repairs are done the same day.", "appointment walkin"),
            ("Will my data be safe?", "We do not open personal files, and we advise you to take a backup first.", "data privacy backup"),
            ("Do you use original parts?", "We use original or high quality compatible parts and tell you which before we start.", "original parts quality"),
            ("Which payment methods do you accept?", "We accept UPI, cards and cash.", "upi card cash payment"),
            ("Do you offer pickup?", "No, please bring the phone to the shop.", "pickup delivery"),
            ("What if the phone cannot be repaired?", "You pay nothing except the inspection fee.", "cannot unrepairable fee"),
            ("Which brands do you repair?", "iPhone, Samsung, Redmi, Vivo, Oppo and most other phones.", "brands samsung redmi vivo oppo"),
        ],
    },
}


def seed(conn):
    for slug, spec in SHOPS.items():
        old = g.get_shop_by_slug(conn, slug)
        if old:
            conn.execute("DELETE FROM shops WHERE id = ?", (old["id"],))
            conn.commit()
        sid = g.create_shop(conn, spec["name"], slug)
        repo.update_shop(conn, sid, address=spec["address"], phone=spec["phone"])
        for name, price, dur, desc, kw in spec["services"]:
            repo.add_service(conn, sid, name, price, dur, desc, kw)
        for q, a, kw in spec["faqs"]:
            repo.add_faq(conn, sid, q, a, kw)
        for day in WEEK:
            span = spec["hours"].get(day)
            if span:
                repo.add_hours(conn, sid, day, span[0], span[1])
            else:
                repo.add_hours(conn, sid, day, closed=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--owner-email", help="LOCAL DEV ONLY: also create a verified owner for demo-salon")
    ap.add_argument("--owner-password", help="password for --owner-email (10+ characters)")
    args = ap.parse_args()
    c = db.connect(args.db)
    db.init_db(c)
    seed(c)
    print("Seeded:", ", ".join(SHOPS))
    if args.owner_email and args.owner_password:
        from app import security
        shop = g.get_shop_by_slug(c, "demo-salon")
        uid = g.create_user(c, shop["id"], args.owner_email, security.hash_password(args.owner_password))
        c.execute("UPDATE users SET verified = 1 WHERE id = ?", (uid,))
        c.commit()
        print("Created verified dev owner for demo-salon:", args.owner_email)
