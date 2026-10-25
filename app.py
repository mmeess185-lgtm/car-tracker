import os
import json
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage
from datetime import datetime, date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from pymongo import MongoClient
from bson import ObjectId

MONGO_URI = os.environ.get("MONGO_URI", "")
client = MongoClient(MONGO_URI)
db = client["employee_tracker"]
cars = db["cars"]
plates = db["plates"]
fines = db["fines"]

FINE_FIELDS = ["date", "car", "plate", "violation_no", "driver", "amount"]


def clean_fine(doc):
    out = {f: str(doc.get(f, "")) for f in FINE_FIELDS}
    out["id"] = str(doc["_id"])
    return out

FIELDS = ["make", "model", "plate", "year", "color", "serial",
          "insurance_expiry", "inspection_expiry", "reg_expiry",
          "owner", "status"]


def clean(doc):
    out = {f: doc.get(f, "") for f in FIELDS}
    if out["status"] not in ("active", "stored"):
        out["status"] = "active"
    rens = doc.get("renewals") or []
    rens = sorted(rens, key=lambda r: str(r.get("done", "")), reverse=True)
    out["renewals"] = rens
    out["id"] = str(doc["_id"])
    return out


DOC_FIELD = {"insurance": "insurance_expiry",
             "inspection": "inspection_expiry",
             "registration": "reg_expiry"}


SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
MAIL_TO = os.environ.get("MAIL_TO", "").strip()
BREVO_KEY = os.environ.get("BREVO_KEY", "").strip()
ALERT_DAYS = int(os.environ.get("ALERT_DAYS", "30"))

DOC_AR = {"insurance_expiry": "التأمين",
          "inspection_expiry": "الفحص الدوري",
          "reg_expiry": "الاستمارة"}


def collect_alerts(limit_days=None):
    """Return list of (car, field, days_left) needing attention."""
    if limit_days is None:
        limit_days = ALERT_DAYS
    today = date.today()
    out = []
    for doc in cars.find():
        if doc.get("status") == "stored":
            continue
        for f in DOC_AR:
            val = str(doc.get(f, "")).strip()
            if not val:
                continue
            try:
                d = datetime.strptime(val, "%Y-%m-%d").date()
            except ValueError:
                continue
            n = (d - today).days
            if n <= limit_days:
                out.append((doc, f, n))
    out.sort(key=lambda x: x[2])
    return out


def build_email_html(items):
    today = date.today().strftime("%Y-%m-%d")
    rows = []
    for doc, f, n in items:
        if n < 0:
            state, col = "منتهية منذ %d يوم" % (-n), "#c0392b"
        elif n == 0:
            state, col = "تنتهي اليوم", "#c0392b"
        else:
            state, col = "متبقي %d يوم" % n, "#b7791f"
        rows.append(
            "<tr>"
            "<td style='padding:8px;border-bottom:1px solid #eee'>%s %s</td>"
            "<td style='padding:8px;border-bottom:1px solid #eee'><b>%s</b></td>"
            "<td style='padding:8px;border-bottom:1px solid #eee'>%s</td>"
            "<td style='padding:8px;border-bottom:1px solid #eee'>%s</td>"
            "<td style='padding:8px;border-bottom:1px solid #eee;color:%s'><b>%s</b></td>"
            "</tr>" % (doc.get("make", ""), doc.get("model", ""), doc.get("plate", ""),
                       DOC_AR[f], doc.get(f, ""), col, state))
    return (
        "<div dir='rtl' style=\"font-family:Tahoma,Arial,sans-serif;color:#222\">"
        "<h2 style='color:#c0392b'>تنبيه وثائق السيارات</h2>"
        "<p>تقرير يوم %s — عدد الوثائق التي تحتاج متابعة: <b>%d</b></p>"
        "<table style='border-collapse:collapse;width:100%%;font-size:14px'>"
        "<tr style='background:#f4f4f4'>"
        "<th style='padding:8px;text-align:right'>السيارة</th>"
        "<th style='padding:8px;text-align:right'>اللوحة</th>"
        "<th style='padding:8px;text-align:right'>الوثيقة</th>"
        "<th style='padding:8px;text-align:right'>تاريخ الانتهاء</th>"
        "<th style='padding:8px;text-align:right'>الحالة</th></tr>"
        "%s</table>"
        "<p style='margin-top:16px;font-size:13px;color:#666'>"
        "أُرسل تلقائياً من نظام متابعة السيارات</p></div>"
        % (today, len(items), "".join(rows)))


def _recipients():
    return [a.strip() for a in MAIL_TO.replace(";", ",").split(",") if a.strip()]


def _send_via_brevo(subject, html, to_list):
    print("[email] trying Brevo, key length:", len(BREVO_KEY), flush=True)
    payload = {
        "sender": {"name": "Car Tracker", "email": SMTP_USER},
        "to": [{"email": a} for a in to_list],
        "subject": subject,
        "htmlContent": html,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={"api-key": BREVO_KEY,
                 "Content-Type": "application/json",
                 "accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return True, ""
    except urllib.error.HTTPError as e:
        msg = "Brevo HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
        print("[email]", msg, flush=True)
        return False, msg
    except Exception as e:
        msg = "Brevo connection error: %r" % (e,)
        print("[email]", msg, flush=True)
        return False, msg


def _send_via_smtp(subject, html, to_list):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(to_list)
    msg.set_content("تقرير وثائق السيارات — افتح الرسالة بصيغة HTML.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


def send_digest():
    to_list = _recipients()
    if not (SMTP_USER and to_list):
        return {"sent": False, "reason": "email not configured"}
    if not (BREVO_KEY or SMTP_PASS):
        return {"sent": False, "reason": "email not configured"}
    items = collect_alerts()
    if not items:
        return {"sent": False, "reason": "nothing to report"}
    subject = "تنبيه وثائق السيارات — %d وثيقة تحتاج متابعة" % len(items)
    html = build_email_html(items)

    brevo_err = "BREVO_KEY is empty" if not BREVO_KEY else None
    if BREVO_KEY:
        ok, brevo_err = _send_via_brevo(subject, html, to_list)
        if ok:
            return {"sent": True, "count": len(items), "to": to_list, "via": "brevo"}
    if not SMTP_PASS:
        return {"sent": False, "reason": "brevo failed: %s" % brevo_err}
    ok, smtp_err = _send_via_smtp(subject, html, to_list)
    if ok:
        return {"sent": True, "count": len(items), "to": to_list, "via": "smtp"}
    return {"sent": False,
            "reason": "brevo failed: %s | gmail failed: %s" % (brevo_err, smtp_err),
            "brevo_error": brevo_err, "gmail_error": smtp_err,
            "key_len": len(BREVO_KEY), "key_head": BREVO_KEY[:8]}


HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Car Tracker</title>
<style>
:root{--bg:#0f172a;--card:#1e293b;--line:#334155;--txt:#e2e8f0;--mut:#94a3b8;--acc:#38bdf8;
--ok:#22c55e;--warn:#f59e0b;--bad:#ef4444}
*{box-sizing:border-box}
body{margin:0;font-family:"Segoe UI",Tahoma,Arial,sans-serif;background:var(--bg);color:var(--txt)}
header{background:var(--card);padding:14px 18px;display:flex;align-items:center;gap:12px;
flex-wrap:wrap;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
h1{font-size:19px;margin:0;flex:1}
button{cursor:pointer;border:none;border-radius:8px;padding:9px 14px;font-size:14px;
font-family:inherit;background:var(--line);color:var(--txt)}
button.primary{background:var(--acc);color:#06283d;font-weight:700}
button.danger{background:#7f1d1d;color:#fecaca}
.wrap{padding:16px;max-width:1400px;margin:0 auto}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-size:26px;margin-bottom:2px}
.stat.click{cursor:pointer;transition:.15s}
.stat.click:hover{border-color:var(--acc);transform:translateY(-2px)}
.stat.sel{border-color:var(--acc);background:#20344a}
.stat small{display:block;margin-top:6px;font-size:12px;color:var(--bad)}
.banner{background:var(--card);border:1px solid var(--acc);border-radius:10px;
padding:9px 13px;margin-bottom:12px;display:none;align-items:center;gap:10px;font-size:13.5px}
.banner.on{display:flex}
.sechead{font-size:13px;color:var(--mut);margin:0 0 8px}

.stat span{color:var(--mut);font-size:13px}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
input,select{background:var(--card);border:1px solid var(--line);color:var(--txt);
border-radius:8px;padding:9px 11px;font-size:14px;font-family:inherit}
#q{flex:1;min-width:180px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;text-align:start;font-size:13.5px;border-bottom:1px solid var(--line);
white-space:nowrap}
th{background:#172033;color:var(--mut);font-weight:600;cursor:pointer;user-select:none}
tr:hover td{background:#243044}
.tbl{overflow-x:auto}
.pill{display:inline-block;padding:3px 8px;border-radius:6px;font-size:12.5px;font-weight:600}
.g{background:rgba(34,197,94,.15);color:var(--ok)}
.y{background:rgba(245,158,11,.15);color:var(--warn)}
.r{background:rgba(239,68,68,.15);color:var(--bad)}
.n{background:#334155;color:var(--mut)}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;
align-items:flex-start;justify-content:center;padding:24px;overflow:auto;z-index:20}
.modal.on{display:flex}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;
width:100%;max-width:560px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
.fld label{display:block;font-size:12.5px;color:var(--mut);margin-bottom:5px}
.fld input{width:100%}
table.mini{width:100%;border-collapse:collapse;margin-bottom:14px;background:#172033;border-radius:8px;overflow:hidden}
table.mini th,table.mini td{padding:6px 8px;font-size:12.5px;border-bottom:1px solid var(--line);text-align:start}
table.mini th{color:var(--mut);font-weight:600}
.row-actions{display:flex;gap:6px}
.row-actions button{padding:5px 10px;font-size:12.5px}
@media(max-width:600px){.grid{grid-template-columns:1fr}h1{font-size:16px}}
</style>
</head>
<body>
<header>
  <h1 id="ttl"></h1>
  <span id="carBtns" style="display:contents">
    <button onclick="openForm()" class="primary" id="bAdd"></button>
    <button onclick="openWallet()" id="bWallet"></button>
    <button onclick="printAll()" id="bPrint"></button>
    <button onclick="testMail()" id="bMail"></button>
  </span>
  <span id="fineBtns" style="display:none">
    <button onclick="openFine()" class="primary" id="bAddFine"></button>
    <button onclick="printFines()" id="bPrintFines"></button>
  </span>
  <button onclick="switchView()" id="bView"></button>
  <button onclick="toggleLang()" id="bLang"></button>
</header>

<div class="wrap" id="carsView">
  <p class="sechead" id="fleetTtl"></p>
  <div class="stats" id="fleet"></div>
  <p class="sechead" id="dashTtl"></p>
  <div class="stats" id="stats"></div>
  <div class="banner" id="pbanner" style="border-color:var(--ok)">
    <span id="pbannerTxt"></span>
  </div>
  <div class="banner" id="banner">
    <span id="bannerTxt"></span>
    <button onclick="clearFocus()" id="bClear"></button>
  </div>
  <div class="tools">
    <input id="q" oninput="render()">
    <select id="filt" onchange="render()"></select>
    <select id="own" onchange="render()"></select>
  </div>
  <div class="tbl"><table><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table></div>
</div>

<div class="wrap" id="finesView" style="display:none">
  <p class="sechead" id="finesTtl"></p>
  <div class="stats" id="fstats"></div>
  <div class="tools">
    <input id="fq" oninput="renderFines()">
    <select id="fdrv" onchange="renderFines()"></select>
    <select id="fyr" onchange="renderFines()"></select>
  </div>
  <div class="tbl"><table><thead><tr id="fhead"></tr></thead><tbody id="fbody"></tbody></table></div>
</div>

<div class="modal" id="fmodal">
  <div class="box" style="max-width:520px">
    <h2 id="fTitle2" style="margin:0;font-size:18px"></h2>
    <div class="grid" id="fGrid"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button onclick="closeFine()" id="fCancel"></button>
      <button onclick="saveFine()" class="primary" id="fSave"></button>
    </div>
  </div>
</div>

<div class="modal" id="wmodal">
  <div class="box" style="max-width:460px">
    <h2 id="wTitle" style="margin:0 0 12px;font-size:18px"></h2>
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <input id="wInput" style="flex:1">
      <button onclick="addPlate()" class="primary" id="wAdd"></button>
    </div>
    <div id="wList"></div>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <button onclick="closeWallet()" id="wClose"></button>
    </div>
  </div>
</div>

<div class="modal" id="rmodal">
  <div class="box" style="max-width:460px">
    <h2 id="rTitle" style="margin:0;font-size:18px"></h2>
    <p id="rCar" style="color:var(--mut);font-size:13.5px;margin:6px 0 0"></p>
    <div class="grid" id="rGrid"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button onclick="closeRen()" id="rCancel"></button>
      <button onclick="saveRen()" class="primary" id="rSave"></button>
    </div>
  </div>
</div>

<div class="modal" id="modal">
  <div class="box">
    <h2 id="fTitle" style="margin:0;font-size:18px"></h2>
    <div class="grid" id="formGrid"></div>
    <div id="renBox"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button onclick="closeForm()" id="bCancel"></button>
      <button onclick="save()" class="primary" id="bSave"></button>
    </div>
  </div>
</div>

<script>
const T = {
 ar:{dir:"rtl",title:"نظام متابعة السيارات",add:"+ إضافة سيارة",lang:"English",
   search:"بحث بالنوع أو اللوحة أو الرقم التسلسلي...",
   all:"كل السيارات",exp:"منتهية",soon:"تنتهي خلال 30 يوم",soon60:"تنتهي خلال 60 يوم",
   stored:"السيارات المخزنة",allOwners:"كل الملاك",
   dTitle:"ينتهي خلال 30 يوم",fleetTtl:"ملخص الأسطول",
   allCars:"إجمالي السيارات",activeCars:"السيارات النشطة",
   storedCars:"السيارات المخزنة",ownerCount:"عدد الملاك",insurance:"التأمين",inspection:"الفحص الدوري",
   registration:"الاستمارة",carUnit:"سيارة",overdue:"منتهية",clear:"إلغاء التحديد",
   showing:"يعرض:",allGood:"لا يوجد شيء ينتهي قريباً ✅",
   fines:"المخالفات",backCars:"السيارات",finesTtl:"سجل المخالفات المرورية",
   addFine:"+ إضافة مخالفة",newFine:"مخالفة جديدة",editFine:"تعديل المخالفة",
   fDate:"تاريخ المخالفة",fCar:"السيارة",fPlate:"اللوحة",fNo:"رقم المخالفة",
   fDriver:"السائق",fAmount:"المبلغ (ريال)",pickCar:"— اختر من السيارات —",
   manual:"— إدخال يدوي —",fSearch:"بحث برقم المخالفة أو السائق أو اللوحة...",
   allDrivers:"كل السائقين",allYears:"كل السنوات",
   fCount:"عدد المخالفات",fTotal:"إجمالي المبالغ",fYear:"مخالفات هذه السنة",
   fYearAmt:"مبالغ هذه السنة",fDrivers:"عدد السائقين",
   noFines:"لا توجد مخالفات مسجلة",confirmFine:"حذف هذه المخالفة؟",
   repFines:"تقرير المخالفات المرورية",printFines:"طباعة المخالفات",
   topDriver:"الأكثر مخالفات",byDriver:"حسب السائق",byCar:"حسب السيارة",
   wallet:"محفظة اللوحات",walletTtl:"محفظة اللوحات الرقمية",
   addPlate:"إضافة لوحة",platePH:"اكتب رقم اللوحة",
   noPlates:"لا توجد لوحات مسجلة",dupPlate:"هذه اللوحة مسجلة مسبقاً",
   plateOnCar:"هذه اللوحة مركّبة على سيارة",
   found:"هذه اللوحة في محفظة اللوحات الرقمية — غير مركّبة على سيارة",
   confirmPlate:"حذف هذه اللوحة من المحفظة؟",close:"إغلاق",
   renew:"تسجيل تجديد",renewTtl:"تسجيل عملية تجديد",docKind:"نوع الوثيقة",
   doneDate:"تاريخ التجديد",newExp:"تاريخ الانتهاء الجديد",expiry:"تاريخ الانتهاء",amount:"المبلغ (ريال)",
   note:"ملاحظة",log:"سجل التجديدات",noLog:"لا يوجد تجديدات مسجلة",
   totalSpent:"إجمالي المصروف",sar:"ريال",print1:"طباعة",printAll:"طباعة التقرير",
   repTtl:"تقرير السيارات",repCar:"تقرير سيارة",repDate:"تاريخ التقرير",
   repCount:"عدد السيارات",carInfo:"بيانات السيارة",docs:"الوثائق",
   grand:"إجمالي مصاريف التجديد",delRen:"حذف",confirmRen:"حذف هذه العملية؟",
   mail:"إرسال تجريبي",mailOk:n=>"تم إرسال الإيميل ("+n+" وثيقة)",
   mailNo:"لا يوجد شيء يستدعي التنبيه حالياً",
   mailCfg:"الإيميل غير مُعد في Render",mailErr:"فشل الإرسال: ",
   total:"السيارات النشطة",expired:"وثائق منتهية",due:"تنتهي خلال 30 يوم",valid:"سليمة",
   cols:{make:"النوع",model:"الموديل",year:"سنة الصنع",plate:"اللوحة",color:"اللون",
     serial:"الرقم التسلسلي",insurance_expiry:"انتهاء التأمين",
     inspection_expiry:"انتهاء الفحص",reg_expiry:"انتهاء الاستمارة",
     owner:"المالك",status:"الحالة",actions:"إجراءات"},
   active:"نشطة",storedOne:"مخزنة",storedNote:"مخزنة",
   edit:"تعديل",del:"حذف",save:"حفظ",cancel:"إلغاء",
   newCar:"سيارة جديدة",editCar:"تعديل بيانات السيارة",
   confirm:"هل تريد حذف هذه السيارة؟",none:"غير مسجل",
   d:n=>"متبقي "+n+" يوم",od:n=>"منتهي منذ "+n+" يوم",today:"ينتهي اليوم",empty:"لا توجد نتائج"},
 en:{dir:"ltr",title:"Car Tracker",add:"+ Add Car",lang:"عربي",
   search:"Search by make, plate or serial...",
   all:"All cars",exp:"Expired",soon:"Expiring in 30 days",soon60:"Expiring in 60 days",
   stored:"Stored cars",allOwners:"All owners",
   dTitle:"Expiring in 30 days",fleetTtl:"Fleet summary",
   allCars:"Total cars",activeCars:"Active cars",
   storedCars:"Stored cars",ownerCount:"Owners",insurance:"Insurance",inspection:"Inspection",
   registration:"Registration",carUnit:"cars",overdue:"expired",clear:"Clear",
   showing:"Showing:",allGood:"Nothing expiring soon ✅",
   fines:"Fines",backCars:"Cars",finesTtl:"Traffic fines history",
   addFine:"+ Add fine",newFine:"New fine",editFine:"Edit fine",
   fDate:"Fine date",fCar:"Car",fPlate:"Plate",fNo:"Violation no.",
   fDriver:"Driver",fAmount:"Amount (SAR)",pickCar:"— pick from cars —",
   manual:"— manual entry —",fSearch:"Search by violation no., driver or plate...",
   allDrivers:"All drivers",allYears:"All years",
   fCount:"Fines",fTotal:"Total amount",fYear:"Fines this year",
   fYearAmt:"Amount this year",fDrivers:"Drivers",
   noFines:"No fines recorded",confirmFine:"Delete this fine?",
   repFines:"Traffic fines report",printFines:"Print fines",
   topDriver:"Most fines",byDriver:"By driver",byCar:"By car",
   wallet:"Plate wallet",walletTtl:"Digital plate wallet",
   addPlate:"Add plate",platePH:"Enter plate number",
   noPlates:"No plates saved",dupPlate:"This plate is already saved",
   plateOnCar:"This plate is already on a car",
   found:"This plate is in the digital plate wallet — not on any car",
   confirmPlate:"Remove this plate from the wallet?",close:"Close",
   renew:"Log renewal",renewTtl:"Log a renewal",docKind:"Document",
   doneDate:"Renewal date",newExp:"New expiry date",expiry:"Expiry date",amount:"Amount (SAR)",
   note:"Note",log:"Renewal history",noLog:"No renewals logged",
   totalSpent:"Total spent",sar:"SAR",print1:"Print",printAll:"Print report",
   repTtl:"Fleet report",repCar:"Car report",repDate:"Report date",
   repCount:"Cars",carInfo:"Car details",docs:"Documents",
   grand:"Total renewal cost",delRen:"Delete",confirmRen:"Delete this entry?",
   mail:"Send test email",mailOk:n=>"Email sent ("+n+" documents)",
   mailNo:"Nothing to report right now",
   mailCfg:"Email not configured in Render",mailErr:"Send failed: ",
   total:"Active cars",expired:"Expired docs",due:"Due in 30 days",valid:"All valid",
   cols:{make:"Make",model:"Model",year:"Year",plate:"Plate",color:"Color",
     serial:"Serial No.",insurance_expiry:"Insurance",
     inspection_expiry:"Inspection",reg_expiry:"Registration",
     owner:"Owner",status:"Status",actions:"Actions"},
   active:"Active",storedOne:"Stored",storedNote:"Stored",
   edit:"Edit",del:"Delete",save:"Save",cancel:"Cancel",
   newCar:"New car",editCar:"Edit car",
   confirm:"Delete this car?",none:"Not set",
   d:n=>n+" days left",od:n=>n+" days overdue",today:"Expires today",empty:"No results"}
};
const F=["make","model","plate","year","color","serial","insurance_expiry","inspection_expiry","reg_expiry","owner"];
const FORMF=F.concat(["status"]);
const DATES=["insurance_expiry","inspection_expiry","reg_expiry"];
let lang=localStorage.getItem("lang")||"ar", data=[], editing=null, sortBy=null, sortDir=1;
let focusDoc=null, renFor=null, lastRows=[], plates=[];
let view="cars", fineList=[], editingFine=null, lastFines=[];
const FCOLS=["date","car","plate","violation_no","driver","amount"];
const FLBL={date:"fDate",car:"fCar",plate:"fPlate",violation_no:"fNo",
            driver:"fDriver",amount:"fAmount"};
const DOCLBL={insurance_expiry:"insurance",inspection_expiry:"inspection",reg_expiry:"registration"};
const t=()=>T[lang];

function days(s){if(!s)return null;const a=new Date(s+"T00:00:00"),b=new Date();
 b.setHours(0,0,0,0);return Math.round((a-b)/864e5);}
function cell(s){const n=days(s);
 if(n===null)return '<span class="pill n">'+t().none+'</span>';
 const c=n<0?"r":n<=30?"y":"g";
 const lab=n<0?t().od(-n):n===0?t().today:t().d(n);
 return '<span class="pill '+c+'">'+s+'<br>'+lab+'</span>';}
function worst(c){let m=null;for(const f of DATES){const n=days(c[f]);
 if(n!==null&&(m===null||n<m))m=n;}return m;}

function toggleLang(){lang=lang==="ar"?"en":"ar";localStorage.setItem("lang",lang);paint();}

function paint(){
 document.documentElement.lang=lang;document.documentElement.dir=t().dir;
 ttl.textContent=t().title;bAdd.textContent=t().add;bLang.textContent=t().lang;
 bSave.textContent=t().save;bCancel.textContent=t().cancel;
 dashTtl.textContent=t().dTitle;fleetTtl.textContent=t().fleetTtl;
 bClear.textContent=t().clear;
 bMail.textContent=t().mail;bPrint.textContent=t().printAll;
 bWallet.textContent=t().wallet;
 bAddFine.textContent=t().addFine;bPrintFines.textContent=t().printFines;
 finesTtl.textContent=t().finesTtl;fSave.textContent=t().save;
 fCancel.textContent=t().cancel;fq.placeholder=t().fSearch;
 bView.textContent=view==="cars"?t().fines:t().backCars;
 ttl.textContent=view==="cars"?t().title:t().finesTtl;
 fhead.innerHTML=FCOLS.map(f=>'<th onclick="fsort(\''+f+'\')">'+t()[FLBL[f]]+
   '</th>').join('')+'<th>'+t().cols.actions+'</th>';
 q.placeholder=t().search;
 const fv=filt.value||'all';
 filt.innerHTML=['all','exp','soon','soon60','stored'].map(k=>
   '<option value="'+k+'">'+t()[k]+'</option>').join('');
 filt.value=fv;
 owners();
 head.innerHTML=F.map(f=>'<th onclick="sort(\''+f+'\')">'+t().cols[f]+'</th>').join('')
   +'<th>'+t().cols.actions+'</th>';
 render();renderFines();
}

function switchView(){
 view=view==="cars"?"fines":"cars";
 carsView.style.display=view==="cars"?"":"none";
 finesView.style.display=view==="fines"?"":"none";
 carBtns.style.display=view==="cars"?"contents":"none";
 fineBtns.style.display=view==="fines"?"contents":"none";
 bView.textContent=view==="cars"?t().fines:t().backCars;
 ttl.textContent=view==="cars"?t().title:t().finesTtl;
 if(view==="fines")renderFines();
}

function setFocus(f){focusDoc=(focusDoc===f?null:f);render();}
function clearFocus(){focusDoc=null;render();}

function owners(){
 const ov=own.value||"";
 const list=[...new Set(data.map(c=>c.owner).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"ar"));
 own.innerHTML='<option value="">'+t().allOwners+'</option>'+
   list.map(o=>'<option value="'+o+'">'+o+'</option>').join('');
 own.value=list.includes(ov)?ov:"";
}

function render(){
 const term=q.value.trim().toLowerCase(), mode=filt.value, ow=own.value;
 let rows=data.filter(c=>{
   if(term&&!F.map(f=>c[f]).join(" ").toLowerCase().includes(term))return false;
   if(ow&&c.owner!==ow)return false;
   const isStored=c.status==="stored";
   if(mode==="stored")return isStored;
   if(isStored)return false;
   if(focusDoc){const n=days(c[focusDoc]);return n!==null&&n<=30;}
   const w=worst(c);
   if(mode==="exp")return w!==null&&w<0;
   if(mode==="soon")return w!==null&&w>=0&&w<=30;
   if(mode==="soon60")return w!==null&&w>=0&&w<=60;
   return true;});
 if(sortBy)rows.sort((a,b)=>String(a[sortBy]).localeCompare(String(b[sortBy]),"ar",{numeric:true})*sortDir);
 else if(focusDoc)rows.sort((a,b)=>{const x=days(a[focusDoc]),y=days(b[focusDoc]);
   return (x===null?9e9:x)-(y===null?9e9:y);});
 else rows.sort((a,b)=>{const x=worst(a),y=worst(b);
   return (x===null?9e9:x)-(y===null?9e9:y);});

 const scope=ow?data.filter(c=>c.owner===ow):data;
 const act=scope.filter(c=>c.status!=="stored");
 const sto=scope.length-act.length;
 const nOwners=new Set(data.map(c=>c.owner).filter(Boolean)).size;
 fleet.innerHTML=[[t().allCars,scope.length,"var(--acc)"],
   [t().activeCars,act.length,"var(--ok)"],
   [t().storedCars,sto,"var(--mut)"],
   [t().ownerCount,nOwners,"var(--acc)"]]
   .map(x=>'<div class="stat"><b style="color:'+x[2]+'">'+x[1]+
   '</b><span>'+x[0]+'</span></div>').join('');

 stats.innerHTML=DATES.map(f=>{
   let soon=0,od=0;
   act.forEach(c=>{const n=days(c[f]);if(n===null)return;
     if(n<0)od++;else if(n<=30)soon++;});
   const col=soon>0?"var(--warn)":"var(--ok)";
   return '<div class="stat click'+(focusDoc===f?' sel':'')+'" onclick="setFocus(\''+f+'\')">'+
     '<b style="color:'+col+'">'+soon+'</b><span>'+t()[DOCLBL[f]]+'</span>'+
     (od?'<small>'+od+' '+t().overdue+'</small>':'')+'</div>';}).join('')+
   '<div class="stat"><b style="color:var(--acc)">'+act.length+'</b><span>'+t().total+'</span></div>';

 if(focusDoc){banner.classList.add("on");
   bannerTxt.textContent=t().showing+" "+t()[DOCLBL[focusDoc]];}
 else banner.classList.remove("on");

 const tq=norm(term);
 const hit=tq?plates.filter(p=>norm(p.plate).includes(tq)):[];
 if(hit.length){pbanner.classList.add("on");
   pbannerTxt.textContent=hit.map(p=>p.plate).join("، ")+" — "+t().found;}
 else pbanner.classList.remove("on");

 lastRows=rows;
 body.innerHTML=rows.length?rows.map(c=>'<tr>'+F.map(f=>
   '<td>'+(DATES.includes(f)?cell(c[f]):(c[f]||"—"))+
   (f==="make"&&c.status==="stored"?' <span class="pill n">'+t().storedNote+'</span>':'')+
   '</td>').join('')+
   '<td><div class="row-actions">'+
   '<button onclick="openRen(\''+c.id+'\')">'+t().renew+'</button>'+
   '<button onclick="printCar(\''+c.id+'\')">'+t().print1+'</button>'+
   '<button onclick="openForm(\''+c.id+'\')">'+t().edit+
   '</button><button class="danger" onclick="del(\''+c.id+'\')">'+t().del+
   '</button></div></td></tr>').join(''):
   '<tr><td colspan="11" style="text-align:center;color:var(--mut);padding:26px">'+t().empty+'</td></tr>';
}
function sort(f){sortDir=sortBy===f?-sortDir:1;sortBy=f;render();}

function openForm(id){
 editing=id||null;
 const c=id?data.find(x=>x.id===id):{};
 fTitle.textContent=id?t().editCar:t().newCar;
 const st=c.status==="stored"?"stored":"active";
 formGrid.innerHTML=F.map(f=>'<div class="fld"><label>'+t().cols[f]+'</label>'+
   '<input id="i_'+f+'" type="'+(DATES.includes(f)?"date":"text")+'" value="'+(c[f]||"")+'"></div>').join('')+
   '<div class="fld"><label>'+t().cols.status+'</label><select id="i_status" style="width:100%">'+
   '<option value="active"'+(st==="active"?" selected":"")+'>'+t().active+'</option>'+
   '<option value="stored"'+(st==="stored"?" selected":"")+'>'+t().storedOne+'</option>'+
   '</select></div>';
 renBox.innerHTML=id?renTable(c):"";
 modal.classList.add("on");
}
function money(n){return (Number(n)||0).toLocaleString("en-US",{maximumFractionDigits:2});}
function num(v){const n=Number(String(v).replace(/,/g,""));return isNaN(n)?0:n;}

function renTable(c){
 const r=c.renewals||[];
 if(!r.length)return '<p class="sechead">'+t().log+'</p><p style="color:var(--mut);font-size:13px">'+t().noLog+'</p>';
 let tot=0;r.forEach(x=>tot+=Number(x.amount)||0);
 return '<p class="sechead">'+t().log+'</p><table class="mini"><tr><th>'+t().doneDate+
   '</th><th>'+t().docKind+'</th><th>'+t().newExp+'</th><th>'+t().amount+'</th><th>'+t().note+'</th><th></th></tr>'+
   r.map((x,i)=>'<tr><td>'+(x.done||"—")+'</td><td>'+t()[x.kind]+'</td><td>'+(x.new_expiry||"—")+
   '</td><td>'+money(x.amount)+'</td><td>'+(x.note||"—")+
   '</td><td><button class="danger" style="padding:3px 8px;font-size:12px" onclick="delRen(\''+c.id+'\','+i+')">'+
   t().delRen+'</button></td></tr>').join('')+
   '<tr><td colspan="3"><b>'+t().totalSpent+'</b></td><td colspan="3"><b>'+money(tot)+' '+t().sar+'</b></td></tr></table>';
}

function openRen(id){
 renFor=id;const c=data.find(x=>x.id===id);
 rTitle.textContent=t().renewTtl;
 rCar.textContent=(c.make||"")+" "+(c.model||"")+" — "+(c.plate||"");
 const today=new Date().toISOString().slice(0,10);
 rGrid.innerHTML=
  '<div class="fld"><label>'+t().docKind+'</label><select id="r_kind" style="width:100%">'+
  ['insurance','inspection','registration'].map(k=>'<option value="'+k+'">'+t()[k]+'</option>').join('')+
  '</select></div>'+
  '<div class="fld"><label>'+t().doneDate+'</label><input id="r_done" type="date" value="'+today+'"></div>'+
  '<div class="fld"><label>'+t().newExp+'</label><input id="r_exp" type="date"></div>'+
  '<div class="fld"><label>'+t().amount+'</label><input id="r_amt" type="number" min="0" step="any"></div>'+
  '<div class="fld" style="grid-column:1/-1"><label>'+t().note+'</label><input id="r_note" type="text"></div>';
 rSave.textContent=t().save;rCancel.textContent=t().cancel;
 rmodal.classList.add("on");
}
function closeRen(){rmodal.classList.remove("on");renFor=null;}
async function saveRen(){
 const p={kind:r_kind.value,done:r_done.value,new_expiry:r_exp.value,
   amount:r_amt.value,note:r_note.value.trim()};
 await fetch("/api/cars/"+renFor+"/renew",{method:"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
 closeRen();await load();
}
async function delRen(id,i){
 if(!confirm(t().confirmRen))return;
 await fetch("/api/cars/"+id+"/renew/"+i,{method:"DELETE"});
 await load();
 const c=data.find(x=>x.id===id);if(c&&modal.classList.contains("on"))renBox.innerHTML=renTable(c);
}

function closeForm(){modal.classList.remove("on");}
async function save(){
 const p={};FORMF.forEach(f=>p[f]=document.getElementById("i_"+f).value.trim());
 await fetch("/api/cars"+(editing?"/"+editing:""),{method:editing?"PUT":"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});
 closeForm();load();
}
async function del(id){if(!confirm(t().confirm))return;
 await fetch("/api/cars/"+id,{method:"DELETE"});load();}
function norm(s){return String(s||"").replace(/\s+/g," ").trim().toLowerCase();}

async function loadPlates(){
 try{plates=await (await fetch("/api/plates")).json();}catch(e){plates=[];}
}

function openWallet(){
 wTitle.textContent=t().walletTtl;wAdd.textContent=t().addPlate;
 wClose.textContent=t().close;wInput.placeholder=t().platePH;
 wInput.value="";drawWallet();wmodal.classList.add("on");
}
function closeWallet(){wmodal.classList.remove("on");}

function drawWallet(){
 if(!plates.length){wList.innerHTML='<p style="color:var(--mut);font-size:13px">'+t().noPlates+'</p>';return;}
 wList.innerHTML='<table class="mini">'+plates.map(p=>
  '<tr><td style="font-size:14px">'+p.plate+'</td>'+
  '<td style="text-align:end"><button class="danger" style="padding:3px 9px;font-size:12px" '+
  'onclick="delPlate(\''+p.id+'\')">'+t().del+'</button></td></tr>').join('')+'</table>';
}

async function addPlate(){
 const v=wInput.value.trim();if(!v)return;
 const onCar=data.find(c=>norm(c.plate)===norm(v));
 if(onCar){alert(t().plateOnCar+": "+onCar.make+" "+onCar.model);return;}
 const r=await fetch("/api/plates",{method:"POST",
   headers:{"Content-Type":"application/json"},body:JSON.stringify({plate:v})});
 if(r.status===409){alert(t().dupPlate);return;}
 wInput.value="";await loadPlates();drawWallet();render();
}

async function delPlate(id){
 if(!confirm(t().confirmPlate))return;
 await fetch("/api/plates/"+id,{method:"DELETE"});
 await loadPlates();drawWallet();render();
}

function docRow(c,f){
 const n=days(c[f]);
 const lab=n===null?t().none:n<0?t().od(-n):n===0?t().today:t().d(n);
 const col=n===null?"#777":n<0?"#c0392b":n<=30?"#b7791f":"#1e8449";
 return '<tr><td>'+t()[DOCLBL[f]]+'</td><td>'+(c[f]||"—")+
   '</td><td style="color:'+col+'"><b>'+lab+'</b></td></tr>';
}

function carBlock(c){
 const r=c.renewals||[];let tot=0;r.forEach(x=>tot+=Number(x.amount)||0);
 return '<div class="pc"><h3>'+(c.make||"")+' '+(c.model||"")+' — '+(c.plate||"")+'</h3>'+
  '<table class="p"><tr><th>'+t().cols.year+'</th><td>'+(c.year||"—")+'</td>'+
  '<th>'+t().cols.color+'</th><td>'+(c.color||"—")+'</td></tr>'+
  '<tr><th>'+t().cols.serial+'</th><td>'+(c.serial||"—")+'</td>'+
  '<th>'+t().cols.owner+'</th><td>'+(c.owner||"—")+'</td></tr>'+
  '<tr><th>'+t().cols.status+'</th><td colspan="3">'+
  (c.status==="stored"?t().storedOne:t().active)+'</td></tr></table>'+
  '<table class="p"><tr><th>'+t().docs+'</th><th>'+t().expiry+'</th><th></th></tr>'+
  DATES.map(f=>docRow(c,f)).join('')+'</table>'+
  (r.length?'<table class="p"><tr><th>'+t().doneDate+'</th><th>'+t().docKind+
   '</th><th>'+t().newExp+'</th><th>'+t().amount+'</th><th>'+t().note+'</th></tr>'+
   r.map(x=>'<tr><td>'+(x.done||"—")+'</td><td>'+t()[x.kind]+'</td><td>'+
   (x.new_expiry||"—")+'</td><td>'+money(x.amount)+'</td><td>'+(x.note||"—")+'</td></tr>').join('')+
   '<tr><td colspan="3"><b>'+t().totalSpent+'</b></td><td colspan="2"><b>'+
   money(tot)+' '+t().sar+'</b></td></tr></table>'
   :'<p class="mut">'+t().noLog+'</p>')+'</div>';
}

function openPrint(title,sub,bodyHtml){
 const w=window.open("","_blank");
 if(!w){alert("Popup blocked");return;}
 w.document.write('<!DOCTYPE html><html lang="'+lang+'" dir="'+t().dir+
  '"><head><meta charset="utf-8"><title>'+title+'</title><style>'+
  'body{font-family:Tahoma,Arial,sans-serif;color:#222;margin:24px}'+
  'h1{font-size:20px;margin:0 0 4px}h3{font-size:15px;margin:0 0 8px;color:#1a5276}'+
  '.sub{color:#666;font-size:13px;margin:0 0 18px}'+
  'table.p{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:10px}'+
  'table.p th,table.p td{border:1px solid #ddd;padding:6px 8px;text-align:start}'+
  'table.p th{background:#f4f4f4;font-weight:600}'+
  '.pc{border:1px solid #ccc;border-radius:6px;padding:14px;margin-bottom:16px;page-break-inside:avoid}'+
  '.mut{color:#888;font-size:13px}.tot{font-size:15px;margin-top:14px}'+
  '@media print{button{display:none}}</style></head><body>'+
  '<h1>'+title+'</h1><p class="sub">'+sub+'</p>'+bodyHtml+
  '<button onclick="window.print()" style="padding:8px 16px;font-size:14px">'+
  t().print1+'</button></body></html>');
 w.document.close();
}

function printCar(id){
 const c=data.find(x=>x.id===id);if(!c)return;
 openPrint(t().repCar,t().repDate+": "+new Date().toISOString().slice(0,10),carBlock(c));
}

function printAll(){
 const rows=lastRows;
 if(!rows.length){alert(t().empty);return;}
 let tot=0;rows.forEach(c=>(c.renewals||[]).forEach(x=>tot+=Number(x.amount)||0));
 const bits=[];
 if(own.value)bits.push(t().cols.owner+": "+own.value);
 bits.push(t()[filt.value]);
 if(focusDoc)bits.push(t()[DOCLBL[focusDoc]]);
 if(q.value.trim())bits.push('"'+q.value.trim()+'"');
 const sub=t().repDate+": "+new Date().toISOString().slice(0,10)+
   " | "+t().repCount+": "+rows.length+" | "+bits.join(" · ");
 openPrint(t().repTtl,sub,rows.map(carBlock).join('')+
   '<p class="tot"><b>'+t().grand+": "+money(tot)+' '+t().sar+'</b></p>');
}


let fSortBy=null, fSortDir=1;
function fsort(f){fSortDir=fSortBy===f?-fSortDir:1;fSortBy=f;renderFines();}

function fineFilters(){
 const dv=fdrv.value||"", yv=fyr.value||"";
 const drv=[...new Set(fineList.map(x=>x.driver).filter(Boolean))]
   .sort((a,b)=>a.localeCompare(b,"ar"));
 fdrv.innerHTML='<option value="">'+t().allDrivers+'</option>'+
   drv.map(d=>'<option value="'+d+'">'+d+'</option>').join('');
 fdrv.value=drv.includes(dv)?dv:"";
 const yrs=[...new Set(fineList.map(x=>(x.date||"").slice(0,4)).filter(Boolean))]
   .sort().reverse();
 fyr.innerHTML='<option value="">'+t().allYears+'</option>'+
   yrs.map(y=>'<option value="'+y+'">'+y+'</option>').join('');
 fyr.value=yrs.includes(yv)?yv:"";
}

function renderFines(){
 fineFilters();
 const term=fq.value.trim().toLowerCase(), dv=fdrv.value, yv=fyr.value;
 let rows=fineList.filter(x=>{
   if(term&&!FCOLS.map(f=>x[f]).join(" ").toLowerCase().includes(term))return false;
   if(dv&&x.driver!==dv)return false;
   if(yv&&(x.date||"").slice(0,4)!==yv)return false;
   return true;});

 if(fSortBy)rows.sort((a,b)=>{
   const x=a[fSortBy]||"",y=b[fSortBy]||"";
   if(fSortBy==="amount")return (num(x)-num(y))*fSortDir;
   return String(x).localeCompare(String(y),"ar",{numeric:true})*fSortDir;});
 else rows.sort((a,b)=>String(b.date||"").localeCompare(String(a.date||"")));

 const scope=fineList.filter(x=>(!dv||x.driver===dv));
 const yr=String(new Date().getFullYear());
 let tot=0,ytot=0,ycnt=0;
 scope.forEach(x=>{const a=num(x.amount);tot+=a;
   if((x.date||"").slice(0,4)===yr){ytot+=a;ycnt++;}});
 const perDrv={};
 scope.forEach(x=>{if(x.driver)perDrv[x.driver]=(perDrv[x.driver]||0)+1;});
 const top=Object.entries(perDrv).sort((a,b)=>b[1]-a[1])[0];

 fstats.innerHTML=
  '<div class="stat"><b style="color:var(--acc)">'+scope.length+'</b><span>'+t().fCount+'</span></div>'+
  '<div class="stat"><b style="color:var(--bad)">'+money(tot)+'</b><span>'+t().fTotal+' ('+t().sar+')</span></div>'+
  '<div class="stat"><b style="color:var(--warn)">'+ycnt+'</b><span>'+t().fYear+'</span></div>'+
  '<div class="stat"><b style="color:var(--warn)">'+money(ytot)+'</b><span>'+t().fYearAmt+' ('+t().sar+')</span></div>'+
  '<div class="stat"><b style="color:var(--acc)">'+Object.keys(perDrv).length+'</b><span>'+t().fDrivers+'</span></div>'+
  (top?'<div class="stat"><b style="color:var(--mut)">'+top[1]+'</b><span>'+t().topDriver+': '+top[0]+'</span></div>':'');

 lastFines=rows;
 fbody.innerHTML=rows.length?rows.map(x=>'<tr>'+FCOLS.map(f=>{
   let v;
   if(f==="amount")v=x[f]?money(x[f]):"—";
   else if(f==="date")v='<span class="pill n">'+(x[f]||"—")+'</span>';
   else v=x[f]||"—";
   return '<td>'+v+'</td>';}).join('')+
   '<td><div class="row-actions">'+
   '<button onclick="openFine(\''+x.id+'\')">'+t().edit+'</button>'+
   '<button class="danger" onclick="delFine(\''+x.id+'\')">'+t().del+'</button>'+
   '</div></td></tr>').join(''):
   '<tr><td colspan="7" style="text-align:center;color:var(--mut);padding:26px">'+
   t().noFines+'</td></tr>';
}

function openFine(id){
 editingFine=id||null;
 const x=id?fineList.find(y=>y.id===id):{};
 fTitle2.textContent=id?t().editFine:t().newFine;
 const today=new Date().toISOString().slice(0,10);
 const opts='<option value="">'+t().pickCar+'</option>'+
   data.map(c=>'<option value="'+c.id+'">'+(c.make||"")+' '+(c.model||"")+
   ' — '+(c.plate||"")+'</option>').join('');
 fGrid.innerHTML=
  '<div class="fld"><label>'+t().fDate+'</label><input id="n_date" type="date" value="'+
   (x.date||today)+'"></div>'+
  '<div class="fld"><label>'+t().fNo+'</label><input id="n_violation_no" type="text" value="'+
   (x.violation_no||"").replace(/"/g,"&quot;")+'"></div>'+
  '<div class="fld" style="grid-column:1/-1"><label>'+t().pickCar+
   '</label><select id="n_pick" onchange="pickCar()">'+opts+'</select></div>'+
  '<div class="fld"><label>'+t().fCar+'</label><input id="n_car" type="text" value="'+
   (x.car||"").replace(/"/g,"&quot;")+'"></div>'+
  '<div class="fld"><label>'+t().fPlate+'</label><input id="n_plate" type="text" value="'+
   (x.plate||"").replace(/"/g,"&quot;")+'"></div>'+
  '<div class="fld"><label>'+t().fDriver+'</label><input id="n_driver" type="text" value="'+
   (x.driver||"").replace(/"/g,"&quot;")+'"></div>'+
  '<div class="fld"><label>'+t().fAmount+'</label><input id="n_amount" type="number" min="0" step="any" value="'+
   (x.amount||"")+'"></div>';
 fmodal.classList.add("on");
}

function pickCar(){
 const c=data.find(y=>y.id===n_pick.value);
 if(!c)return;
 n_car.value=((c.make||"")+" "+(c.model||"")).trim();
 n_plate.value=c.plate||"";
}

function closeFine(){fmodal.classList.remove("on");editingFine=null;}

async function saveFine(){
 const p={};FCOLS.forEach(f=>{const el=document.getElementById("n_"+f);
   if(el)p[f]=String(el.value||"").trim();});
 await fetch("/api/fines"+(editingFine?"/"+editingFine:""),
   {method:editingFine?"PUT":"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(p)});
 closeFine();await loadFines();renderFines();
}

async function delFine(id){
 if(!confirm(t().confirmFine))return;
 await fetch("/api/fines/"+id,{method:"DELETE"});
 await loadFines();renderFines();
}

function printFines(){
 const rows=lastFines;
 if(!rows.length){alert(t().noFines);return;}
 let tot=0;rows.forEach(x=>tot+=num(x.amount));
 const bits=[];
 if(fdrv.value)bits.push(t().fDriver+": "+fdrv.value);
 if(fyr.value)bits.push(fyr.value);
 if(fq.value.trim())bits.push('"'+fq.value.trim()+'"');
 const sub=t().repDate+": "+new Date().toISOString().slice(0,10)+
   " | "+t().fCount+": "+rows.length+(bits.length?" | "+bits.join(" · "):"");
 const body='<table class="p"><tr>'+
   FCOLS.map(f=>'<th>'+t()[FLBL[f]]+'</th>').join('')+'</tr>'+
   rows.map(x=>'<tr>'+FCOLS.map(f=>'<td>'+
     (f==="amount"?(x[f]?money(x[f]):"—"):(x[f]||"—"))+'</td>').join('')+'</tr>').join('')+
   '<tr><td colspan="5"><b>'+t().fTotal+'</b></td><td><b>'+money(tot)+' '+t().sar+'</b></td></tr>'+
   '</table>';
 openPrint(t().repFines,sub,body);
}

async function testMail(){
 bMail.disabled=true;const old=bMail.textContent;bMail.textContent="...";
 try{const r=await (await fetch("/api/send-digest")).json();
   if(r.sent)alert(t().mailOk(r.count));
   else if(r.reason==="email not configured")alert(t().mailCfg);
   else if(r.reason==="nothing to report")alert(t().mailNo);
   else alert(t().mailErr+r.reason);
 }catch(e){alert(t().mailErr+e);}
 bMail.disabled=false;bMail.textContent=old;
}

async function loadFines(){
 try{fineList=await (await fetch("/api/fines")).json();}catch(e){fineList=[];}
}

async function load(){
 data=await (await fetch("/api/cars")).json();
 await loadPlates();await loadFines();owners();render();renderFines();}

modal.addEventListener("click",e=>{if(e.target===modal)closeForm();});
wmodal.addEventListener("click",e=>{if(e.target===wmodal)closeWallet();});
fmodal.addEventListener("click",e=>{if(e.target===fmodal)closeFine();});
wInput.addEventListener("keydown",e=>{if(e.key==="Enter")addPlate();});
paint();load();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _payload(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        body = json.loads(raw.decode("utf-8"))
        return {f: str(body.get(f, "")).strip() for f in FIELDS}

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/api/send-digest", "/cron/daily"):
            try:
                res = send_digest()
            except Exception as e:
                res = {"sent": False, "reason": str(e)}
            self._send(200, json.dumps(res, ensure_ascii=False))
        elif path == "/api/fines":
            docs = [clean_fine(d) for d in fines.find()]
            docs.sort(key=lambda x: x["date"], reverse=True)
            self._send(200, json.dumps(docs, ensure_ascii=False))
        elif path == "/api/plates":
            docs = [{"id": str(d["_id"]), "plate": d.get("plate", "")}
                    for d in plates.find()]
            docs.sort(key=lambda x: x["plate"])
            self._send(200, json.dumps(docs, ensure_ascii=False))
        elif path == "/api/cars":
            docs = [clean(d) for d in cars.find()]
            self._send(200, json.dumps(docs, ensure_ascii=False))
        elif path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        # /api/cars/<id>/renew
        if len(parts) == 4 and parts[1] == "cars" and parts[3] == "renew":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            kind = str(body.get("kind", "")).strip()
            if kind not in DOC_FIELD:
                self._send(400, json.dumps({"error": "bad kind"}))
                return
            try:
                amount = float(str(body.get("amount", "")).strip() or 0)
            except ValueError:
                amount = 0.0
            entry = {
                "kind": kind,
                "done": str(body.get("done", "")).strip(),
                "new_expiry": str(body.get("new_expiry", "")).strip(),
                "amount": amount,
                "note": str(body.get("note", "")).strip(),
                "at": datetime.utcnow().isoformat(),
            }
            upd = {"$push": {"renewals": entry}}
            if entry["new_expiry"]:
                upd["$set"] = {DOC_FIELD[kind]: entry["new_expiry"]}
            cars.update_one({"_id": ObjectId(parts[2])}, upd)
            self._send(201, json.dumps({"ok": True}, ensure_ascii=False))
            return
        if urlparse(self.path).path == "/api/fines":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            doc = {f: str(body.get(f, "")).strip() for f in FINE_FIELDS}
            doc["created"] = datetime.utcnow().isoformat()
            fines.insert_one(doc)
            self._send(201, json.dumps({"ok": True}))
            return
        if urlparse(self.path).path == "/api/plates":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            p = " ".join(str(body.get("plate", "")).split())
            if not p:
                self._send(400, json.dumps({"error": "empty plate"}))
                return
            if plates.find_one({"plate": p}):
                self._send(409, json.dumps({"error": "duplicate"}))
                return
            plates.insert_one({"plate": p, "created": datetime.utcnow().isoformat()})
            self._send(201, json.dumps({"ok": True}))
            return
        if urlparse(self.path).path == "/api/cars":
            doc = self._payload()
            doc["created"] = datetime.utcnow().isoformat()
            cars.insert_one(doc)
            self._send(201, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_PUT(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "fines":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            doc = {f: str(body.get(f, "")).strip() for f in FINE_FIELDS}
            fines.update_one({"_id": ObjectId(parts[2])}, {"$set": doc})
            self._send(200, json.dumps({"ok": True}))
            return
        if len(parts) == 3 and parts[1] == "cars":
            cars.update_one({"_id": ObjectId(parts[2])}, {"$set": self._payload()})
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_DELETE(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 5 and parts[1] == "cars" and parts[3] == "renew":
            doc = cars.find_one({"_id": ObjectId(parts[2])})
            rens = (doc or {}).get("renewals") or []
            rens = sorted(rens, key=lambda r: str(r.get("done", "")), reverse=True)
            try:
                idx = int(parts[4])
                target = rens[idx]
            except (ValueError, IndexError):
                self._send(400, json.dumps({"error": "bad index"}))
                return
            cars.update_one({"_id": ObjectId(parts[2])},
                            {"$pull": {"renewals": {"at": target.get("at")}}})
            self._send(200, json.dumps({"ok": True}))
            return
        if len(parts) == 3 and parts[1] == "fines":
            fines.delete_one({"_id": ObjectId(parts[2])})
            self._send(200, json.dumps({"ok": True}))
            return
        if len(parts) == 3 and parts[1] == "plates":
            plates.delete_one({"_id": ObjectId(parts[2])})
            self._send(200, json.dumps({"ok": True}))
            return
        if len(parts) == 3 and parts[1] == "cars":
            cars.delete_one({"_id": ObjectId(parts[2])})
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("Car tracker running on port", port)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
