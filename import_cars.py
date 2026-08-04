import os
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "")
if not MONGO_URI:
    MONGO_URI = input("Paste your MongoDB connection string: ").strip()

CARS = [
    {
        "make": "isuzu",
        "model": "غمارة",
        "year": "2020",
        "plate": "ح ح ح 222",
        "color": "ابيض",
        "serial": "20630810",
        "insurance_expiry": "2027-02-11",
        "inspection_expiry": "2027-04-28",
        "reg_expiry": "2029-07-14"
    },
    {
        "make": "hyundai",
        "model": "سوناتا",
        "year": "2024",
        "plate": "د ك د 1212",
        "color": "رصاصي فاتح",
        "serial": "24067020",
        "insurance_expiry": "2027-04-27",
        "inspection_expiry": "2027-04-13",
        "reg_expiry": "2027-03-30"
    },
    {
        "make": "subaru",
        "model": "امبريزا",
        "year": "2008",
        "plate": "و ح ن 460",
        "color": "رصاصي",
        "serial": "26050900",
        "insurance_expiry": "2026-02-03",
        "inspection_expiry": "2026-03-04",
        "reg_expiry": "2027-02-11"
    },
    {
        "make": "GMC",
        "model": "يوكون",
        "year": "2025",
        "plate": "د ع ا 24",
        "color": "رصاصي",
        "serial": "38176120",
        "insurance_expiry": "2027-03-08",
        "inspection_expiry": "2027-01-01",
        "reg_expiry": "2028-02-14"
    },
    {
        "make": "بورش",
        "model": "بوكستر",
        "year": "2021",
        "plate": "س س ص 9599",
        "color": "اسود",
        "serial": "110745020",
        "insurance_expiry": "2027-06-22",
        "inspection_expiry": "2027-03-08",
        "reg_expiry": "2029-05-28"
    },
    {
        "make": "متسوبيشي",
        "model": "اوت لاندر",
        "year": "2023",
        "plate": "ه ن و 72",
        "color": "ابيض",
        "serial": "138036910",
        "insurance_expiry": "2027-08-03",
        "inspection_expiry": "2027-04-07",
        "reg_expiry": "2028-07-13"
    },
    {
        "make": "نيسان",
        "model": "نافارا",
        "year": "2017",
        "plate": "ب ح ه 3085",
        "color": "ابيض",
        "serial": "140511610",
        "insurance_expiry": "2027-08-03",
        "inspection_expiry": "2027-03-09",
        "reg_expiry": "2029-03-10"
    },
    {
        "make": "بي ام",
        "model": "ال 7",
        "year": "2006",
        "plate": "ه ي 85",
        "color": "ازرق",
        "serial": "181192700",
        "insurance_expiry": "2023-02-02",
        "inspection_expiry": "2026-03-10",
        "reg_expiry": "2026-03-12"
    },
    {
        "make": "فورد",
        "model": "رينجر",
        "year": "2023",
        "plate": "ا ا د 1",
        "color": "اسود",
        "serial": "218018910",
        "insurance_expiry": "2027-04-11",
        "inspection_expiry": "2027-04-29",
        "reg_expiry": "2029-02-28"
    },
    {
        "make": "هارلي",
        "model": "دراجه ناريه",
        "year": "2014",
        "plate": "رر 441",
        "color": "برتقالي",
        "serial": "256111410",
        "insurance_expiry": "2023-02-02",
        "inspection_expiry": "2026-03-18",
        "reg_expiry": "2026-03-11"
    },
    {
        "make": "نيسان",
        "model": "نافارا",
        "year": "2020",
        "plate": "ب ح ه 3149",
        "color": "ابيض",
        "serial": "328656810",
        "insurance_expiry": "2026-12-23",
        "inspection_expiry": "2027-07-05",
        "reg_expiry": "2028-02-15"
    },
    {
        "make": "هارلي",
        "model": "دراجه ناريه",
        "year": "2005",
        "plate": "ي و 33",
        "color": "ازرق",
        "serial": "364681700",
        "insurance_expiry": "2026-02-05",
        "inspection_expiry": "2026-03-19",
        "reg_expiry": "2026-03-26"
    },
    {
        "make": "فولكس واجن",
        "model": "طوارق جيب",
        "year": "2016",
        "plate": "ر ص س 1949",
        "color": "ذهبي",
        "serial": "436658410",
        "insurance_expiry": "2027-04-25",
        "inspection_expiry": "2027-04-12",
        "reg_expiry": "2027-04-06"
    },
    {
        "make": "متسوبيشي",
        "model": "اي اس اكس",
        "year": "2022",
        "plate": "س س ص 9116",
        "color": "ابيض",
        "serial": "493179810",
        "insurance_expiry": "2026-07-21",
        "inspection_expiry": "2026-12-30",
        "reg_expiry": "2027-12-24"
    },
    {
        "make": "سوزوكي",
        "model": "ديزاير",
        "year": "2023",
        "plate": "ب ا ا 8000",
        "color": "فضي",
        "serial": "552398910",
        "insurance_expiry": "2027-06-20",
        "inspection_expiry": "2027-04-02",
        "reg_expiry": "2029-03-26"
    },
    {
        "make": "HONDA",
        "model": "دراجه ناريه",
        "year": "2004",
        "plate": "ن ي 66",
        "color": "احمر",
        "serial": "557938600",
        "insurance_expiry": "2026-03-31",
        "inspection_expiry": "2026-03-25",
        "reg_expiry": "2026-03-25"
    },
    {
        "make": "هارلي",
        "model": "دراجه ناريه",
        "year": "2004",
        "plate": "ا ك 44",
        "color": "ازرق",
        "serial": "614454600",
        "insurance_expiry": "2026-03-25",
        "inspection_expiry": "2026-03-25",
        "reg_expiry": "2026-03-25"
    },
    {
        "make": "نيسان",
        "model": "نافارا",
        "year": "2017",
        "plate": "ح ح ح 77",
        "color": "ابيض",
        "serial": "619411610",
        "insurance_expiry": "2027-08-03",
        "inspection_expiry": "2027-02-08",
        "reg_expiry": "2028-02-15"
    },
    {
        "make": "فورد",
        "model": "موستنق",
        "year": "2005",
        "plate": "ا م ن 345",
        "color": "ازرق فاتح",
        "serial": "668462700",
        "insurance_expiry": "2026-03-18",
        "inspection_expiry": "2026-03-10",
        "reg_expiry": "2026-03-05"
    },
    {
        "make": "بي ام",
        "model": "536",
        "year": "2005",
        "plate": "م ص ع 490",
        "color": "رصاصي",
        "serial": "780056600",
        "insurance_expiry": "2026-03-09",
        "inspection_expiry": "2026-03-04",
        "reg_expiry": "2026-03-04"
    },
    {
        "make": "kawasaki",
        "model": "دراجه ناريه",
        "year": "2011",
        "plate": "ح ح 288",
        "color": "ازرق",
        "serial": "813993110",
        "insurance_expiry": "2026-03-10",
        "inspection_expiry": "2026-03-05",
        "reg_expiry": "2026-03-05"
    },
    {
        "make": "فورد",
        "model": "سبور",
        "year": "1980",
        "plate": "د ن ك 6880",
        "color": "ابيض",
        "serial": "847570810",
        "insurance_expiry": "2026-03-11",
        "inspection_expiry": "2026-03-06",
        "reg_expiry": "2026-03-06"
    },
    {
        "make": "جينسس",
        "model": "جي في 70",
        "year": "2023",
        "plate": "ه ن و 800",
        "color": "اسود",
        "serial": "879034910",
        "insurance_expiry": "2027-05-10",
        "inspection_expiry": "2027-04-08",
        "reg_expiry": "2027-05-26"
    },
    {
        "make": "بيجو",
        "model": "فان",
        "year": "2014",
        "plate": "ه ن و 855",
        "color": "ابيض",
        "serial": "882624410",
        "insurance_expiry": "2027-11-02",
        "inspection_expiry": "2026-09-03",
        "reg_expiry": "2027-08-01"
    },
    {
        "make": "بي ام",
        "model": "كوبيه",
        "year": "2011",
        "plate": "ب م م 3335",
        "color": "ازرق",
        "serial": "894176010",
        "insurance_expiry": "2026-03-04",
        "inspection_expiry": "2025-10-02",
        "reg_expiry": "2026-03-18"
    },
    {
        "make": "تويوتا",
        "model": "لاند كروزر",
        "year": "2023",
        "plate": "ن د ا 6",
        "color": "فضي",
        "serial": "899929910",
        "insurance_expiry": "2026-12-19",
        "inspection_expiry": "2027-04-02",
        "reg_expiry": "2026-12-16"
    },
    {
        "make": "ايسوزو",
        "model": "ايسوزو",
        "year": "2012",
        "plate": "ب ص ي 5676",
        "color": "ابيض",
        "serial": "179475210",
        "insurance_expiry": "2026-07-15",
        "inspection_expiry": "2027-05-18",
        "reg_expiry": "2027-05-29"
    },
    {
        "make": "ايسوزو",
        "model": "ايسوزو",
        "year": "2012",
        "plate": "ا ن ي 3972",
        "color": "ابيض",
        "serial": "358475210",
        "insurance_expiry": "2026-10-19",
        "inspection_expiry": "2027-04-20",
        "reg_expiry": "2028-02-14"
    },
    {
        "make": "ايسوزو",
        "model": "ايسوزو",
        "year": "2020",
        "plate": "ب س ق 9927",
        "color": "ابيض",
        "serial": "83092810",
        "insurance_expiry": "2027-04-27",
        "inspection_expiry": "2026-10-21",
        "reg_expiry": "2027-07-23"
    },
    {
        "make": "جينسس",
        "model": "جينسس",
        "year": "2025",
        "plate": "ا س ط 200",
        "color": "فضي",
        "serial": "682563120",
        "insurance_expiry": "2027-07-21",
        "inspection_expiry": "2028-01-01",
        "reg_expiry": "2028-08-15"
    },
    {
        "make": "نيسان",
        "model": "صني",
        "year": "2024",
        "plate": "ه س ن 800",
        "color": "اسود",
        "serial": "776715020",
        "insurance_expiry": "2026-07-23",
        "inspection_expiry": "2027-11-01",
        "reg_expiry": "2026-08-25"
    },
    {
        "make": "كيا",
        "model": "اي في 5",
        "year": "2025",
        "plate": "ي ا س 40",
        "color": "رصاصي",
        "serial": "393188220",
        "insurance_expiry": "2027-06-21",
        "inspection_expiry": "",
        "reg_expiry": ""
    }
]

client = MongoClient(MONGO_URI)
col = client["employee_tracker"]["cars"]

existing = col.count_documents({})
print("Cars already in database:", existing)
if existing:
    ans = input("Delete them and re-import? (yes/no): ").strip().lower()
    if ans == "yes":
        col.delete_many({})
    else:
        print("Nothing changed.")
        raise SystemExit

col.insert_many(CARS)
print("Imported", col.count_documents({}), "cars successfully.")
