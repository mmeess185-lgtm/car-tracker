import os
import json
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from pymongo import MongoClient
from bson import ObjectId

MONGO_URI = os.environ.get("MONGO_URI", "")
client = MongoClient(MONGO_URI)
db = client["employee_tracker"]
cars = db["cars"]

FIELDS = ["make", "model", "plate", "year", "color", "serial",
          "insurance_expiry", "inspection_expiry", "reg_expiry",
          "owner", "status"]


def clean(doc):
    out = {f: doc.get(f, "") for f in FIELDS}
    if out["status"] not in ("active", "stored"):
        out["status"] = "active"
    out["id"] = str(doc["_id"])
    return out


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
.row-actions{display:flex;gap:6px}
.row-actions button{padding:5px 10px;font-size:12.5px}
@media(max-width:600px){.grid{grid-template-columns:1fr}h1{font-size:16px}}
</style>
</head>
<body>
<header>
  <h1 id="ttl"></h1>
  <button onclick="openForm()" class="primary" id="bAdd"></button>
  <button onclick="toggleLang()" id="bLang"></button>
</header>

<div class="wrap">
  <p class="sechead" id="dashTtl"></p>
  <div class="stats" id="stats"></div>
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

<div class="modal" id="modal">
  <div class="box">
    <h2 id="fTitle" style="margin:0;font-size:18px"></h2>
    <div class="grid" id="formGrid"></div>
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
   dTitle:"ينتهي خلال 30 يوم",insurance:"التأمين",inspection:"الفحص الدوري",
   registration:"الاستمارة",carUnit:"سيارة",overdue:"منتهية",clear:"إلغاء التحديد",
   showing:"يعرض:",allGood:"لا يوجد شيء ينتهي قريباً ✅",
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
   dTitle:"Expiring in 30 days",insurance:"Insurance",inspection:"Inspection",
   registration:"Registration",carUnit:"cars",overdue:"expired",clear:"Clear",
   showing:"Showing:",allGood:"Nothing expiring soon ✅",
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
let focusDoc=null;
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
 dashTtl.textContent=t().dTitle;bClear.textContent=t().clear;
 q.placeholder=t().search;
 const fv=filt.value||'all';
 filt.innerHTML=['all','exp','soon','soon60','stored'].map(k=>
   '<option value="'+k+'">'+t()[k]+'</option>').join('');
 filt.value=fv;
 owners();
 head.innerHTML=F.map(f=>'<th onclick="sort(\''+f+'\')">'+t().cols[f]+'</th>').join('')
   +'<th>'+t().cols.actions+'</th>';
 render();
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

 const act=data.filter(c=>c.status!=="stored"&&(!ow||c.owner===ow));
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

 body.innerHTML=rows.length?rows.map(c=>'<tr>'+F.map(f=>
   '<td>'+(DATES.includes(f)?cell(c[f]):(c[f]||"—"))+
   (f==="make"&&c.status==="stored"?' <span class="pill n">'+t().storedNote+'</span>':'')+
   '</td>').join('')+
   '<td><div class="row-actions"><button onclick="openForm(\''+c.id+'\')">'+t().edit+
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
 modal.classList.add("on");
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
async function load(){data=await (await fetch("/api/cars")).json();owners();render();}

modal.addEventListener("click",e=>{if(e.target===modal)closeForm();});
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
        if path == "/api/cars":
            docs = [clean(d) for d in cars.find()]
            self._send(200, json.dumps(docs, ensure_ascii=False))
        elif path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if urlparse(self.path).path == "/api/cars":
            doc = self._payload()
            doc["created"] = datetime.utcnow().isoformat()
            cars.insert_one(doc)
            self._send(201, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_PUT(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "cars":
            cars.update_one({"_id": ObjectId(parts[2])}, {"$set": self._payload()})
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_DELETE(self):
        parts = urlparse(self.path).path.strip("/").split("/")
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
