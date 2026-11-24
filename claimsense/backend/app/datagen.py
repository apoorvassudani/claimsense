"""Synthetic ClaimSense dataset generator.

Real Indian cities, localities, PIN codes and RTO codes are used for realism. Everything else
(people, house numbers, phone numbers, businesses, policies, amounts, documents) is fictional.
Phone numbers use the 55xxx range, which is not an Indian mobile range; vehicle numbers use a
'Z*' test series. Output is deterministic for a given seed.

Each claim carries its scenario and the rules that SHOULD fire (the answer key), and each document
carries the field values actually written in it.
"""
import random
from collections import defaultdict
from datetime import date, timedelta

SEED = 2026
DATA_START, DATA_END = date(2025, 4, 1), date(2026, 9, 30)
INSURER = "Northwind General Insurance Co. Ltd. (fictional)"

# city, locality, PIN, RTO prefix, GST state code
LOCALITIES = [
    ("New Delhi", "Dwarka Sector 12", "110078", "DL 9C", "07"),
    ("New Delhi", "Lajpat Nagar", "110024", "DL 3C", "07"),
    ("New Delhi", "Rohini Sector 9", "110085", "DL 8C", "07"),
    ("Noida", "Sector 62", "201309", "UP 16", "09"),
    ("Gurugram", "DLF Phase 3", "122002", "HR 26", "06"),
    ("Faridabad", "Sector 15", "121007", "HR 51", "06"),
    ("Mumbai", "Andheri West", "400058", "MH 02", "27"),
    ("Mumbai", "Powai", "400076", "MH 03", "27"),
    ("Pune", "Kothrud", "411038", "MH 12", "27"),
    ("Bengaluru", "Koramangala", "560034", "KA 01", "29"),
    ("Bengaluru", "Whitefield", "560066", "KA 53", "29"),
    ("Lucknow", "Gomti Nagar", "226010", "UP 32", "09"),
    ("Jaipur", "Malviya Nagar", "302017", "RJ 14", "08"),
    ("Hyderabad", "Madhapur", "500081", "TG 07", "36"),
    ("Ahmedabad", "Navrangpura", "380009", "GJ 01", "24"),
]
FIRST = ["Aarav", "Vivaan", "Aditya", "Rohan", "Karan", "Nikhil", "Siddharth", "Varun", "Manish", "Sanjay",
         "Rakesh", "Imran", "Harpreet", "Arjun", "Kunal", "Deepak", "Ananya", "Diya", "Ishita", "Kavya",
         "Meera", "Neha", "Pooja", "Riya", "Sakshi", "Shreya", "Tanvi", "Nandini", "Farah", "Lakshmi",
         "Gaurav", "Pranav", "Yash", "Aditi", "Swati", "Ritu", "Vikram", "Suresh", "Anjali", "Mohit"]
LAST = ["Sharma", "Verma", "Gupta", "Mehta", "Iyer", "Nair", "Reddy", "Patel", "Shah", "Joshi", "Kulkarni",
        "Deshpande", "Rao", "Menon", "Chopra", "Malhotra", "Bansal", "Agarwal", "Singh", "Khan", "Das",
        "Bose", "Pillai", "Saxena", "Tiwari", "Mishra", "Kapoor", "Bhatt", "Chauhan", "Sethi"]
GARAGE_WORDS = ["Kestrel", "Arclight", "Bluepine", "Northgate", "Copperleaf", "Ironbark", "Silverfern",
                "Redwood", "Quillstone", "Marigold", "Tealbrook", "Ambergate", "Cobalt", "Juniper", "Harbourline"]
GARAGE_SUFFIX = ["Motor Works", "Auto Care", "Car Clinic", "Auto Repairs"]
HOSPITAL_WORDS = ["Willowmere", "Amberleaf", "Brightwell", "Sunvale", "Lotusgrove", "Cedarbrook", "Hollyfield",
                  "Rosemount", "Fairhaven", "Greenmeadow"]
HOSPITAL_SUFFIX = ["Hospital", "Multispeciality Hospital", "Medical Centre"]
CONTRACTOR_WORDS = ["Stonebridge", "Tidewater", "Granite & Grain", "Oakline", "Brickfield"]
CAR_MODELS = ["Maruti Swift", "Hyundai i20", "Tata Nexon", "Honda City", "Mahindra XUV300", "Kia Seltos",
              "Maruti Baleno", "Toyota Innova Crysta", "Hyundai Creta", "Tata Punch"]

MOTOR_INCIDENTS = {
    "Rear-ended at a traffic signal": [("Rear bumper assembly", 7800, 11200), ("Tail lamp (RH)", 2400, 4200),
                                       ("Boot lid panel", 9500, 15000)],
    "Side collision while turning": [("Front door panel (LH)", 9800, 14500), ("ORVM assembly (LH)", 2900, 5200),
                                     ("Fender (LH)", 4200, 7600)],
    "Front damage after hitting a road divider": [("Front bumper assembly", 8400, 12800),
                                                  ("Radiator", 9200, 16500), ("Headlamp assembly (RH)", 6200, 11800)],
    "Windshield and bonnet damaged by a falling branch": [("Windshield glass", 9800, 17500),
                                                          ("Bonnet panel", 8900, 14200), ("Wiper assembly", 1600, 2900)],
    "Hit by an unidentified vehicle while parked": [("Rear door panel (RH)", 9200, 13800),
                                                     ("Quarter panel (RH)", 7600, 12400), ("Tail lamp (RH)", 2400, 4200)],
}
HEALTH_CASES = {  # diagnosis/procedure: (days range, procedure fee range, medicines range)
    "Acute appendicitis - laparoscopic appendectomy": ((2, 4), (45000, 70000), (6000, 12000)),
    "Dengue fever - supportive care": ((3, 6), (0, 0), (8000, 18000)),
    "Fracture of right radius - open reduction and internal fixation": ((2, 4), (55000, 90000), (7000, 14000)),
    "Cataract (left eye) - phacoemulsification with IOL": ((1, 1), (28000, 45000), (2500, 5000)),
    "Gallstones - laparoscopic cholecystectomy": ((2, 4), (60000, 95000), (7000, 13000)),
    "Community-acquired pneumonia - IV antibiotics": ((4, 7), (0, 0), (12000, 26000)),
}
PROPERTY_CASES = {
    "Water seepage from overhead tank damaged walls and flooring": [
        ("Wall plastering and waterproofing", 18000, 42000), ("Replacement of damaged vitrified flooring", 24000, 60000),
        ("Repainting of affected rooms", 12000, 26000)],
    "Short-circuit fire in kitchen": [("Electrical rewiring (kitchen)", 15000, 32000),
                                      ("Modular kitchen cabinet replacement", 45000, 110000),
                                      ("Smoke cleaning and repainting", 14000, 28000)],
    "False ceiling collapse after heavy rain": [("False ceiling replacement", 26000, 58000),
                                                ("Roof waterproofing treatment", 22000, 48000),
                                                ("Repair of light fixtures", 6000, 14000)],
}

RING_GARAGE = "Redfern Auto Hub"
RING_HOSPITAL = "Clearbrook Nursing Home"


# ---------------------------------------------------------------- formatting helpers
def inr(x: float) -> tuple[str, str]:
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail, parts = whole[:-3], whole[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return whole, frac


def fmt_amt(x: float, style: int) -> str:
    w, f = inr(x)
    return [f"₹{w}.{f}", f"Rs. {w}/-" if f == "00" else f"Rs. {w}.{f}", f"INR {w}.{f}", f"Rs {x:.2f}"][style % 4]


def fmt_date(d: date, style: int) -> str:
    return [d.isoformat(), d.strftime("%d/%m/%Y"), d.strftime("%d-%m-%Y"), d.strftime("%d %b %Y"),
            d.strftime("%d %B %Y"), d.strftime("%d.%m.%Y")][style % 6]


def name_variant(full: str, style: int) -> str:
    first, last = full.split()
    return [full, full.upper(), f"{first[0]}. {last}"][style % 3]


def gst(amount: float) -> float:
    return round(amount * 0.18, 2)


class Generator:
    def __init__(self, seed: int = SEED):
        self.r = random.Random(seed)
        self.used_phones: set[str] = set()
        self.used_regs: set[str] = set()
        self.used_names: set[str] = set()
        self.provider_dates: dict[str, list[date]] = defaultdict(list)
        self.claimants: list[dict] = []
        self.policies: list[dict] = []
        self.claims: list[dict] = []
        self.counters = defaultdict(int)
        self.garages = {loc[1]: [self._biz(GARAGE_WORDS, GARAGE_SUFFIX) for _ in range(2)] for loc in LOCALITIES}
        self.hospitals = {loc[0]: [self._biz(HOSPITAL_WORDS, HOSPITAL_SUFFIX) for _ in range(2)] for loc in LOCALITIES}
        self.contractors = {loc[0]: f"{self.r.choice(CONTRACTOR_WORDS)} Home Repairs" for loc in LOCALITIES}

    # ---------------------------------------------------------------- entities
    def _biz(self, words, suffixes):
        while True:
            name = f"{self.r.choice(words)} {self.r.choice(suffixes)}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name

    def _next(self, key: str) -> int:
        self.counters[key] += 1
        return self.counters[key]

    def phone(self) -> str:
        while True:
            p = f"+91 55{self.r.randint(100, 999)} {self.r.randint(10000, 99999)}"
            if p not in self.used_phones:
                self.used_phones.add(p)
                return p

    def reg(self, loc) -> str:
        while True:
            r = f"{loc[3]} Z{self.r.choice('VWXY')} {self.r.randint(1000, 9999)}"
            if r not in self.used_regs:
                self.used_regs.add(r)
                return r

    def address(self, loc) -> str:
        return f"House No. {self.r.randint(11, 899)}, {loc[1]}, {loc[0]} - {loc[2]}"

    def person(self, loc, *, address: str | None = None, phone: str | None = None, last: str | None = None) -> dict:
        while True:
            name = f"{self.r.choice(FIRST)} {last or self.r.choice(LAST)}"
            if name not in self.used_names:
                self.used_names.add(name)
                break
        p = {"claimant_code": f"C{self._next('claimant'):03d}", "full_name": name, "loc": loc,
             "phone": phone or self.phone(), "address": address or self.address(loc)}
        self.claimants.append(p)
        return p

    def policy(self, holder: dict, product: str, start: date, sum_insured: float) -> dict:
        code = {"MOTOR": "MTR", "HEALTH": "HLT", "PROPERTY": "PRP"}[product]
        p = {"policy_number": f"NW/{code}/{start.year}/{self._next('policy'):06d}", "holder_code": holder["claimant_code"],
             "product_type": product, "sum_insured": sum_insured, "start_date": start,
             "end_date": start + timedelta(days=364)}
        self.policies.append(p)
        return p

    def free_date(self, provider: str | None, lo: date = DATA_START, hi: date = DATA_END, gap: int = 31) -> date:
        """Random date in [lo, hi] with no other claim at the same provider within `gap` days."""
        for _ in range(500):
            d = lo + timedelta(days=self.r.randint(0, (hi - lo).days))
            if not provider or all(abs((d - o).days) >= gap for o in self.provider_dates[provider]):
                return d
        raise RuntimeError(f"no free date for {provider}")

    # ---------------------------------------------------------------- line items
    def motor_items(self, incident: str, heavy: bool = False):
        parts = self.r.sample(MOTOR_INCIDENTS[incident], k=self.r.randint(2, 3) if not heavy else 3)
        items = [(name, 1, round(self.r.uniform(lo, hi) * (1.8 if heavy else 1), -1)) for name, lo, hi in parts]
        if heavy:
            items.append(("Chassis alignment and structural repair", 1, round(self.r.uniform(42000, 60000), -1)))
        labour = round(self.r.uniform(3500, 9500) * (1.6 if heavy else 1), -1)
        sub = sum(q * rate for _, q, rate in items) + labour
        return items, labour, sub, gst(sub), round(sub + gst(sub), 2)

    def property_items(self, case: str, heavy: bool = False):
        items = [(n, 1, round(self.r.uniform(lo, hi) * (2.2 if heavy else 1), -2)) for n, lo, hi in PROPERTY_CASES[case]]
        labour = round(self.r.uniform(8000, 20000), -2)
        sub = sum(r for _, _, r in items) + labour
        return items, labour, sub, gst(sub), round(sub + gst(sub), 2)

    def health_items(self, case: str, admit: date):
        (dmin, dmax), (plo, phi), (mlo, mhi) = HEALTH_CASES[case]
        days = self.r.randint(dmin, dmax)
        room_rate = self.r.choice([3500, 4500, 6000])
        items = [(f"Room charges ({days} day{'s' if days > 1 else ''} @ {room_rate})", days * room_rate)]
        if phi:
            items.append(("Procedure / surgeon fees", round(self.r.uniform(plo, phi), -2)))
            items.append(("Operation theatre charges", round(self.r.uniform(9000, 18000), -2)))
        items.append(("Medicines and consumables", round(self.r.uniform(mlo, mhi), -1)))
        items.append(("Laboratory and radiology", round(self.r.uniform(3500, 9500), -1)))
        total = round(sum(a for _, a in items), 2)
        return items, total, admit + timedelta(days=days)

    # ---------------------------------------------------------------- documents
    def _doc(self, doc_type: str, text: str, fields: dict) -> dict:
        base = {k: None for k in ("policy_number", "claimant_name", "incident_date", "document_date", "amount",
                                  "invoice_number", "provider_name", "vehicle_registration", "phone")}
        base.update(fields)
        base["document_type"] = doc_type
        for k in ("incident_date", "document_date"):
            if isinstance(base[k], date):
                base[k] = base[k].isoformat()
        if base["amount"] is not None:
            base["amount"] = round(float(base["amount"]), 2)
        header = "SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD"
        return {"doc_type": doc_type, "text": text.strip() + f"\n\n{header}\n", "fields": base}

    def claim_form(self, c: dict, variant: int, policy_number: str | None = None) -> dict:
        r, ds, am = self.r, r_style(self.r), self.r.randint(0, 3)
        name = name_variant(c["claimant"]["full_name"], 0 if variant == 2 else r.randint(0, 1))
        pn = policy_number or c["policy"]["policy_number"]
        product = {"MOTOR": "Private Car Package Policy", "HEALTH": "Individual Health Policy",
                   "PROPERTY": "Home Shield Policy"}[c["claim_type"]]
        veh = c.get("vehicle")
        loc = c["claimant"]["loc"]
        f = {"policy_number": pn, "claimant_name": name, "incident_date": c["incident_date"],
             "amount": c["claimed_amount"]}
        if variant == 0:
            lines = [f"{INSURER}", "CLAIM INTIMATION FORM", "",
                     f"Policy No.          : {pn}", f"Product             : {product}",
                     f"Name of Insured     : {name}", f"Contact Number      : {c['claimant']['phone']}",
                     f"Address             : {c['claimant']['address']}",
                     f"{'Date of Admission' if c['claim_type'] == 'HEALTH' else 'Date of Loss':<20}: "
                     f"{fmt_date(c['incident_date'], ds)}",
                     f"Place of Loss       : {loc[1]}, {loc[0]}"]
            if veh:
                lines.append(f"Vehicle Reg. No.    : {veh}")
            lines += [f"Nature of Loss      : {c['description']}",
                      f"Amount Claimed      : {fmt_amt(c['claimed_amount'], am)}",
                      f"Date of Intimation  : {fmt_date(c['reported_date'], ds)}", "",
                      "Declaration: I declare that the information given above is true to the best of my knowledge."]
            f.update(phone=c["claimant"]["phone"], document_date=c["reported_date"], vehicle_registration=veh)
        elif variant == 1:
            lines = [f"CLAIM FORM - {c['claim_type']}", INSURER, "",
                     "Section 1: Policy details", f"  Policy number ............ {pn}", f"  Product .................. {product}",
                     "Section 2: Insured person", f"  Full name ................ {name}",
                     f"  Mobile ................... {c['claimant']['phone']}",
                     "Section 3: Loss details",
                     f"  {'Admitted on' if c['claim_type'] == 'HEALTH' else 'Incident on'} .............. "
                     f"{fmt_date(c['incident_date'], ds)}",
                     f"  Location ................. {loc[1]}, {loc[0]}",
                     f"  Description .............. {c['description']}"]
            if veh:
                lines.append(f"  Vehicle .................. {veh} ({c['model']})")
            lines += [f"  Estimated loss ........... {fmt_amt(c['claimed_amount'], am)}", "",
                      f"Signed by the insured on {fmt_date(c['reported_date'], ds)}"]
            f.update(phone=c["claimant"]["phone"], document_date=c["reported_date"], vehicle_registration=veh)
        else:
            when = fmt_date(c["incident_date"], 4)
            desc = c["description"][0].lower() + c["description"][1:]
            if c["claim_type"] == "MOTOR":
                event = f"On {when}, my vehicle {veh} ({c['model']}) was damaged: {desc}."
            elif c["claim_type"] == "HEALTH":
                event = f"I was admitted to hospital on {when} for {desc}."
            else:
                event = f"On {when}, my home suffered damage: {desc}."
            lines = ["To,", "The Claims Manager,", INSURER, "",
                     f"Subject: Claim under policy {pn}", "", "Dear Sir/Madam,", "",
                     f"I, {name}, residing at {c['claimant']['address']}, wish to intimate a claim under the above "
                     f"policy. {event}",
                     f"I request reimbursement of {fmt_amt(c['claimed_amount'], am)} as per the attached documents.",
                     "", "Yours faithfully,", name, f"Date: {fmt_date(c['reported_date'], ds)}"]
            f.update(document_date=c["reported_date"], vehicle_registration=veh)
        return self._doc("CLAIM_FORM", "\n".join(lines), f)

    def motor_invoice(self, c: dict, variant: int, *, name=None, vehicle=None, inv_no=None, bill_date=None,
                      show_incident=None) -> dict:
        r = self.r
        name = name or name_variant(c["claimant"]["full_name"], r.randint(0, 2))
        vehicle = vehicle or c["vehicle"]
        inv_no = inv_no or c["invoice_number"]
        bill_date = bill_date or c["bill_date"]
        g, loc = c["provider"], c["provider_loc"]
        items, labour, sub, tax, total = c["bill"]
        ds, am = r_style(r), r.randint(0, 3)
        f = {"claimant_name": name, "document_date": bill_date, "amount": total, "invoice_number": inv_no,
             "provider_name": g, "vehicle_registration": vehicle}
        if variant == 0:
            gstin = f"{loc[4]}AAB{'CFGHK'[len(g) % 5]}{'PQRST'[len(inv_no) % 5]}{1000 + len(g) * 37 % 9000}K1Z{len(g) % 9}"
            lines = [g.upper(), f"{loc[1]}, {loc[0]} - {loc[2]}     GSTIN: {gstin}", "", "TAX INVOICE",
                     f"Invoice No: {inv_no}          Date: {fmt_date(bill_date, ds)}",
                     f"Customer: {name}     Vehicle: {vehicle}     Model: {c['model']}",
                     f"Insurance Policy: {c['policy']['policy_number']}",
                     "-" * 64, f"{'Sr':<4}{'Description':<40}{'Qty':>4}{'Amount':>16}"]
            for i, (desc, q, rate) in enumerate(items, 1):
                lines.append(f"{i:<4}{desc:<40}{q:>4}{inr(rate)[0] + '.' + inr(rate)[1]:>16}")
            lines += [f"{len(items) + 1:<4}{'Labour charges':<40}{1:>4}{'.'.join(inr(labour)):>16}", "-" * 64,
                      f"{'Sub-total':>48}{'.'.join(inr(sub)):>16}", f"{'GST @ 18%':>48}{'.'.join(inr(tax)):>16}",
                      f"{'GRAND TOTAL':>48}{fmt_amt(total, am):>16}"]
            f["policy_number"] = c["policy"]["policy_number"]
        elif variant == 1:
            lines = [f"JOB CARD CUM BILL - {g}, {loc[1]}, {loc[0]}",
                     f"Bill No. {inv_no} | Dated {fmt_date(bill_date, 3)}",
                     f"Vehicle {vehicle} ({c['model']}), owner {name}",
                     f"Accident date as reported by customer: {fmt_date(show_incident or c['incident_date'], ds)}",
                     "", "Work done:"]
            for desc, q, rate in items:
                lines.append(f" - {desc} ........ {fmt_amt(rate, 1)}")
            lines += [f" - Labour (denting, painting, fitting) ........ {fmt_amt(labour, 1)}", "",
                      f"Sub-total {fmt_amt(sub, 1)}; GST 18% {fmt_amt(tax, 1)}",
                      f"NET PAYABLE: {fmt_amt(total, am)}"]
            f["incident_date"] = show_incident or c["incident_date"]
        else:
            lines = [f"{g} | Payment Receipt", f"Receipt No: {inv_no}    Date: {fmt_date(bill_date, ds)}",
                     f"Received from {name} towards accident repairs of vehicle {vehicle}.",
                     f"Total received: {fmt_amt(total, am)} (inclusive of GST)", "Thank you for your business."]
        return self._doc("INVOICE", "\n".join(lines), f)

    def property_invoice(self, c: dict, variant: int) -> dict:
        r = self.r
        name = name_variant(c["claimant"]["full_name"], r.randint(0, 2))
        items, labour, sub, tax, total = c["bill"]
        ds, am = r_style(r), r.randint(0, 3)
        g, loc = c["provider"], c["claimant"]["loc"]
        f = {"claimant_name": name, "document_date": c["bill_date"], "amount": total,
             "invoice_number": c["invoice_number"], "provider_name": g}
        if variant == 0:
            lines = [g.upper(), f"{loc[0]}", "", "TAX INVOICE",
                     f"Invoice No: {c['invoice_number']}    Date: {fmt_date(c['bill_date'], ds)}",
                     f"Client: {name}, {c['claimant']['address']}", "-" * 60]
            for desc, _, rate in items:
                lines.append(f"{desc:<46}{'.'.join(inr(rate)):>14}")
            lines += [f"{'Labour and site supervision':<46}{'.'.join(inr(labour)):>14}", "-" * 60,
                      f"{'Sub-total':<46}{'.'.join(inr(sub)):>14}", f"{'GST 18%':<46}{'.'.join(inr(tax)):>14}",
                      f"{'TOTAL':<46}{fmt_amt(total, am):>14}"]
        else:
            lines = [f"{g} - Repair Bill", f"Bill {c['invoice_number']} dated {fmt_date(c['bill_date'], 4)}",
                     f"Work carried out at the residence of {name} after the incident of "
                     f"{fmt_date(c['incident_date'], 3)}:"]
            lines += [f"  * {desc}: {fmt_amt(rate, 1)}" for desc, _, rate in items]
            lines += [f"  * Labour: {fmt_amt(labour, 1)}", f"Total payable (incl. 18% GST): {fmt_amt(total, am)}"]
            f["incident_date"] = c["incident_date"]
        return self._doc("INVOICE", "\n".join(lines), f)

    def medical_bill(self, c: dict, variant: int, patient: str | None = None) -> dict:
        r = self.r
        if patient == "OTHER":  # someone else's bill: different surname
            own_last = c["claimant"]["full_name"].split()[1]
            patient = f"{r.choice(FIRST)} {r.choice([n for n in LAST if n != own_last])}"
        name = patient or name_variant(c["claimant"]["full_name"], r.randint(0, 2))
        items, total, discharge = c["bill"]
        ds, am = r_style(r), r.randint(0, 3)
        h, loc = c["provider"], c["claimant"]["loc"]
        f = {"claimant_name": name, "incident_date": c["incident_date"], "document_date": discharge,
             "amount": total, "invoice_number": c["invoice_number"], "provider_name": h}
        if variant == 0:
            lines = [h.upper(), f"{loc[1]}, {loc[0]}", "", "FINAL HOSPITAL BILL",
                     f"Bill No: {c['invoice_number']}     UHID: {r.randint(100000, 999999)}",
                     f"Patient Name: {name}", f"Date of Admission: {fmt_date(c['incident_date'], ds)}",
                     f"Date of Discharge: {fmt_date(discharge, ds)}", f"Diagnosis: {c['description']}", "-" * 60]
            lines += [f"{desc:<46}{'.'.join(inr(a)):>14}" for desc, a in items]
            lines += ["-" * 60, f"{'NET AMOUNT':<46}{fmt_amt(total, am):>14}"]
        else:
            lines = [f"{h}", "DISCHARGE SUMMARY AND BILLING NOTE", "",
                     f"{name} was admitted on {fmt_date(c['incident_date'], 4)} with {c['description'].split(' - ')[0].lower()} "
                     f"and was managed with {c['description'].split(' - ')[1]}. The patient was discharged in stable "
                     f"condition on {fmt_date(discharge, 4)}.", "",
                     f"Final bill no. {c['invoice_number']} amounting to {fmt_amt(total, am)} has been settled in full.",
                     "Break-up: " + "; ".join(f"{d} {fmt_amt(a, 1)}" for d, a in items) + "."]
        return self._doc("MEDICAL_BILL", "\n".join(lines), f)

    def police_report(self, c: dict, variant: int, incident: date | None = None) -> dict:
        r = self.r
        d = incident or c["incident_date"]
        name = name_variant(c["claimant"]["full_name"], r.randint(0, 1))
        loc = c["claimant"]["loc"]
        hh, mm = r.randint(7, 22), r.choice([5, 15, 20, 30, 40, 50])
        f = {"claimant_name": name, "incident_date": d, "vehicle_registration": c["vehicle"]}
        if variant == 0:
            lines = [f"GENERAL DIARY ENTRY - LOCAL POLICE STATION, {loc[0].upper()}",
                     f"G.D. No. {r.randint(100, 999)}B dated {fmt_date(d, 5)}", "",
                     f"On {fmt_date(d, 5)} at about {hh:02d}:{mm:02d} hrs, the complainant {name}, r/o "
                     f"{c['claimant']['address']}, reported that their vehicle {c['vehicle']} ({c['model']}) was "
                     f"damaged near {loc[1]}: {c['description'][0].lower() + c['description'][1:]}. No injuries were reported. The entry has been made "
                     "for record and insurance purposes."]
        else:
            lines = [f"ACCIDENT REPORT - TRAFFIC POLICE, {loc[0].upper()}",
                     f"Report No: TR/{loc[0][:3].upper()}/{d.year}/{r.randint(1000, 9999)}",
                     f"Date & time of accident: {fmt_date(d, 3)}, {hh:02d}:{mm:02d}",
                     f"Vehicle involved: {c['vehicle']} ({c['model']})", f"Reported by: {name}",
                     f"Location: {loc[1]}, {loc[0]}", f"Remarks: {c['description']}. Damage limited to vehicle."]
        return self._doc("POLICE_REPORT", "\n".join(lines), f)

    # ---------------------------------------------------------------- claim builders
    def _base(self, product, claimant, policy, incident, reported, description, scenario, expected):
        n = self._next("claim")
        return {"claim_number": f"CLM-{incident.year}-{n:05d}", "claim_type": product, "claimant": claimant,
                "policy": policy, "incident_date": incident, "reported_date": reported, "description": description,
                "scenario": scenario, "expected_rules": sorted(expected), "docs": []}

    def motor(self, *, scenario="legit", expected=(), claimant=None, loc=None, garage=None, incident=None,
              start_offset=None, report_delay=None, claim_factor=1.0, heavy=False, si_factor=None, vehicle=None,
              model=None, inv_variant=None, police=True, police_date=None, form_policy=None, expired=False,
              copy_invoice_from=None, edit_invoice_from=None, description=None) -> dict:
        r = self.r
        loc = loc or (claimant["loc"] if claimant else r.choice(LOCALITIES))
        claimant = claimant or self.person(loc)
        garage = garage or r.choice(self.garages[loc[1]])
        src = copy_invoice_from or edit_invoice_from
        if incident is None:
            incident = self.free_date(garage, gap=31)
        self.provider_dates[garage].append(incident)
        description = description or r.choice(list(MOTOR_INCIDENTS))
        if src:
            bill = src["bill"]
        else:
            bill = self.motor_items(description, heavy=heavy)
        total = bill[4]
        claimed = round(total * claim_factor, -1) if claim_factor != 1.0 else total
        si = round(total * si_factor, -3) if si_factor else round(r.uniform(3.5, 9) * 100000, -4)
        start = self._policy_start(incident, start_offset, expired)
        policy = self.policy(claimant, "MOTOR", start, si)
        reported = incident + timedelta(days=report_delay if report_delay is not None else r.randint(0, 8))
        c = self._base("MOTOR", claimant, policy, incident, reported, description, scenario, expected)
        c.update(vehicle=vehicle or self.reg(loc), model=model or r.choice(CAR_MODELS), provider=garage,
                 provider_loc=loc, bill=bill, claimed_amount=claimed,
                 invoice_number=src["invoice_number"] if src else f"{garage.split()[0][:3].upper()}/{self._next('inv'):05d}",
                 bill_date=incident + timedelta(days=r.randint(2, 6)))
        c["docs"].append(self.claim_form(c, r.randint(0, 2), policy_number=form_policy))
        if copy_invoice_from:
            c["docs"].append(dict(copy_invoice_from["invoice_doc"]))  # byte-identical reuse
        elif edit_invoice_from:
            c["docs"].append(self.motor_invoice(c, 2, inv_no=src["invoice_number"]))
        else:
            c["invoice_doc"] = self.motor_invoice(c, inv_variant if inv_variant is not None else r.randint(0, 2))
            c["docs"].append(c["invoice_doc"])
        if police:
            c["docs"].append(self.police_report(c, r.randint(0, 1), incident=police_date))
        self.claims.append(c)
        return c

    def health(self, *, scenario="legit", expected=(), claimant=None, loc=None, hospital=None, incident=None,
               start_offset=None, report_delay=None, claim_factor=1.0, si=None, bill=True, patient=None,
               expired=False) -> dict:
        r = self.r
        loc = loc or (claimant["loc"] if claimant else r.choice(LOCALITIES))
        claimant = claimant or self.person(loc)
        hospital = hospital or r.choice(self.hospitals[loc[0]])
        if incident is None:
            incident = self.free_date(hospital, gap=31)
        self.provider_dates[hospital].append(incident)
        case = r.choice(list(HEALTH_CASES))
        items, total, discharge = self.health_items(case, incident)
        claimed = round(total * claim_factor, -1) if claim_factor != 1.0 else total
        policy = self.policy(claimant, "HEALTH", self._policy_start(incident, start_offset, expired),
                             si or r.choice([300000, 500000, 1000000]))
        reported = discharge + timedelta(days=report_delay if report_delay is not None else r.randint(0, 7))
        c = self._base("HEALTH", claimant, policy, incident, reported, case, scenario, expected)
        c.update(provider=hospital, bill=(items, total, discharge), claimed_amount=claimed,
                 invoice_number=f"{hospital.split()[0][:2].upper()}B-{self._next('bill'):05d}")
        c["docs"].append(self.claim_form(c, r.randint(0, 2)))
        if bill:
            c["docs"].append(self.medical_bill(c, r.randint(0, 1), patient=patient))
        self.claims.append(c)
        return c

    def property(self, *, scenario="legit", expected=(), claim_factor=1.0, heavy=False, si_factor=None,
                 invoice=True) -> dict:
        r = self.r
        loc = r.choice(LOCALITIES)
        claimant = self.person(loc)
        contractor = self.contractors[loc[0]]
        incident = self.free_date(contractor, gap=31)
        self.provider_dates[contractor].append(incident)
        case = r.choice(list(PROPERTY_CASES))
        bill = self.property_items(case, heavy=heavy)
        claimed = round(bill[4] * claim_factor, -1) if claim_factor != 1.0 else bill[4]
        si = round(bill[4] * si_factor, -3) if si_factor else round(r.uniform(10, 50) * 100000, -5)
        policy = self.policy(claimant, "PROPERTY", self._policy_start(incident, None, False), si)
        c = self._base("PROPERTY", claimant, policy, incident, incident + timedelta(days=r.randint(1, 9)), case,
                       scenario, expected)
        c.update(provider=contractor, bill=bill, claimed_amount=claimed,
                 invoice_number=f"{contractor.split()[0][:3].upper()}-{self._next('pinv'):04d}",
                 bill_date=incident + timedelta(days=r.randint(5, 15)))
        c["docs"].append(self.claim_form(c, r.randint(0, 2)))
        if invoice:
            c["docs"].append(self.property_invoice(c, r.randint(0, 1)))
        self.claims.append(c)
        return c

    def _policy_start(self, incident: date, start_offset: int | None, expired: bool) -> date:
        if expired:  # incident 3-10 days after expiry
            return incident - timedelta(days=364 + self.r.randint(3, 10))
        if start_offset is not None:  # negative = incident before start
            return incident - timedelta(days=start_offset)
        return incident - timedelta(days=self.r.randint(45, 330))

    # ---------------------------------------------------------------- the dataset
    def build(self) -> "Generator":
        r = self.r
        # Legitimate claims (most of the queue)
        for _ in range(26):
            self.motor()
        for _ in range(16):
            self.health()
        for _ in range(7):
            self.property()
        # Innocent oddities - expected NOT to fire any rule
        self.motor(scenario="innocent: claim 5% above invoice (towing charges)", claim_factor=1.05)
        self.health(scenario="innocent: reported 20 days after discharge", report_delay=20)
        fam_loc = LOCALITIES[9]
        a = self.person(fam_loc, last="Rao")
        b = self.person(fam_loc, address=a["address"], last="Rao")
        self.health(scenario="innocent: family members share an address", claimant=a)
        self.health(scenario="innocent: family members share an address", claimant=b)
        repeat = self.motor(scenario="innocent: repeat claimant (first claim)")
        later = repeat["incident_date"] + timedelta(days=200)
        if later > DATA_END:
            later = repeat["incident_date"] - timedelta(days=200)
        self.motor(scenario="innocent: repeat claimant, same vehicle, months later", claimant=repeat["claimant"],
                   vehicle=repeat["vehicle"], model=repeat["model"], garage=self._other_garage(repeat),
                   incident=later)

        # Planted fraud / red-flag scenarios
        self.motor(scenario="incident one day before policy start", expected={"POLICY_PERIOD"}, start_offset=-1)
        self.health(scenario="incident after policy expiry", expected={"POLICY_PERIOD"}, expired=True)
        self.motor(scenario="claim exceeds sum insured", expected={"OVER_SUM_INSURED"}, heavy=True, si_factor=0.8)
        self.property(scenario="claim exceeds sum insured", expected={"OVER_SUM_INSURED"}, heavy=True, si_factor=0.75)
        self.motor(scenario="inflated claim vs invoice", expected={"AMOUNT_MISMATCH"}, claim_factor=1.45)
        self.health(scenario="inflated claim vs hospital bill", expected={"AMOUNT_MISMATCH"}, claim_factor=1.35)
        self.property(scenario="inflated claim vs contractor bill", expected={"AMOUNT_MISMATCH"}, claim_factor=1.5)

        # Exact copy of another claim's invoice (source claim is legit but gets linked)
        src = self.motor(scenario="duplicate source: invoice later reused by another claim",
                         expected={"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE", "SHARED_VEHICLE"}, inv_variant=2)
        src_last = src["claimant"]["full_name"].split()[1]
        copier = self.person(src["provider_loc"], last=r.choice([n for n in LAST if n != src_last]))
        self.motor(scenario="reused invoice file from another claim",
                   expected={"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE", "NAME_MISMATCH", "SHARED_VEHICLE"},
                   copy_invoice_from=src, claimant=copier, garage=src["provider"],
                   incident=self.free_date(src["provider"], gap=31))
        # Edited copy: same invoice number and garage, details changed
        src2 = self.motor(scenario="duplicate source: invoice number later reused",
                          expected={"DUPLICATE_INVOICE"}, inv_variant=0)
        self.motor(scenario="edited copy of another claim's invoice", expected={"DUPLICATE_INVOICE"},
                   edit_invoice_from=src2, loc=src2["provider_loc"], garage=src2["provider"],
                   incident=self.free_date(src2["provider"], gap=31))

        # Garage ring in Faridabad: 4 claims at one garage within ~3 weeks, two share a phone
        far = LOCALITIES[5]
        shared_phone = self.phone()
        base = self.free_date(None, date(2026, 3, 1), date(2026, 6, 30))
        for i in range(4):
            cl = self.person(far, phone=shared_phone if i < 2 else None)
            exp = {"PROVIDER_CLUSTER", "SHARED_PHONE"} if i < 2 else {"PROVIDER_CLUSTER"}
            self.motor(scenario="garage ring: claims clustered at one garage", expected=exp, claimant=cl,
                       garage=RING_GARAGE, incident=base + timedelta(days=i * 6 + r.randint(0, 3)),
                       description="Hit by an unidentified vehicle while parked")
        # Hospital ring in Lucknow: 3 claimants share a phone, same nursing home within ~4 weeks
        lko = LOCALITIES[11]
        ring_phone = self.phone()
        base = self.free_date(None, date(2025, 10, 1), date(2026, 2, 28))
        for i in range(3):
            cl = self.person(lko, phone=ring_phone)
            self.health(scenario="hospital ring: shared phone and clustered admissions",
                        expected={"PROVIDER_CLUSTER", "SHARED_PHONE"}, claimant=cl, hospital=RING_HOSPITAL,
                        incident=base + timedelta(days=i * 9 + r.randint(0, 4)))
        # Same vehicle claimed by two different people
        v1 = self.motor(scenario="vehicle claimed by two different claimants (first)", expected={"SHARED_VEHICLE"})
        self.motor(scenario="vehicle claimed by two different claimants (second)", expected={"SHARED_VEHICLE"},
                   vehicle=v1["vehicle"], model=v1["model"], loc=v1["provider_loc"], garage=self._other_garage(v1))

        self.health(scenario="hospital bill in another person's name", expected={"NAME_MISMATCH"}, patient="OTHER")
        other_pol = r.choice([p for p in self.policies if p["product_type"] == "MOTOR"])["policy_number"]
        self.motor(scenario="claim form quotes a different policy number", expected={"POLICY_NUMBER_MISMATCH"},
                   form_policy=other_pol, inv_variant=r.choice([1, 2]))
        fake_inc = self.motor(scenario="police report date differs from claim", expected={"DATE_MISMATCH"},
                              inv_variant=r.choice([0, 2]), police_date=None)
        self._shift_police_date(fake_inc, days=6)
        self.motor(scenario="early claim with inflated amount", expected={"EARLY_CLAIM", "AMOUNT_MISMATCH"},
                   start_offset=9, claim_factor=1.4)
        self.motor(scenario="early claim (red flag, may be genuine)", expected={"EARLY_CLAIM"}, start_offset=20)
        self.motor(scenario="no police report, reported late, inflated",
                   expected={"MISSING_DOCUMENT", "LATE_REPORTING", "AMOUNT_MISMATCH"}, police=False,
                   report_delay=50, claim_factor=1.3)
        self.health(scenario="hospital bill not submitted", expected={"MISSING_DOCUMENT"}, bill=False)
        self.property(scenario="contractor invoice not submitted", expected={"MISSING_DOCUMENT"}, invoice=False)
        self.motor(scenario="reported 45 days after incident", expected={"LATE_REPORTING"}, report_delay=45)

        return self

    def _other_garage(self, c):
        return next(g for g in self.garages[c["provider_loc"][1]] if g != c["provider"])

    def _shift_police_date(self, c: dict, days: int):
        """Replace the police report with one stating a different incident date."""
        c["docs"] = [d for d in c["docs"] if d["doc_type"] != "POLICE_REPORT"]
        c["docs"].append(self.police_report(c, self.r.randint(0, 1), incident=c["incident_date"] + timedelta(days=days)))


def r_style(r: random.Random) -> int:
    return r.randint(0, 5)


WEIGHTS = {"HIGH": 40, "MEDIUM": 20, "LOW": 5}


def generate(seed: int = SEED) -> dict:
    """Return plain-data dataset: claimants, policies, claims (with docs and answer key)."""
    from .services.rules import SEVERITY

    g = Generator(seed).build()
    claims = sorted(g.claims, key=lambda c: c["incident_date"])
    out_claims = []
    for i, c in enumerate(claims, 1):
        c["claim_number"] = f"CLM-{c['incident_date'].year}-{i:05d}"
        score = min(100, sum(WEIGHTS[SEVERITY[r]] for r in c["expected_rules"]))
        out_claims.append({
            "claim_number": c["claim_number"], "claim_type": c["claim_type"],
            "claimant_code": c["claimant"]["claimant_code"], "policy_number": c["policy"]["policy_number"],
            "incident_date": c["incident_date"], "reported_date": c["reported_date"],
            "claimed_amount": c["claimed_amount"], "description": c["description"], "scenario": c["scenario"],
            "expected_rules": c["expected_rules"], "expected_flagged": score >= 20,
            "docs": [{"doc_type": d["doc_type"], "text": d["text"], "fields": d["fields"]} for d in c["docs"]],
        })
    claimants = [{k: p[k] for k in ("claimant_code", "full_name", "phone", "address")} | {"city": p["loc"][0]}
                 for p in g.claimants]
    return {"claimants": claimants, "policies": g.policies, "claims": out_claims}
