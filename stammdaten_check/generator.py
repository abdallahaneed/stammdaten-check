"""Synthetic ECC extracts with known errors.

Builds a fictional Mittelstand company (wholesale, company code 1000) with
customers, vendors, bank data, contacts, materials and posting activity.
Then it breaks a known set of records on purpose and writes what it broke
to labels.csv. evaluate.py compares the findings against that file.

Some errors are marked holdout. They use variants the rules were not tuned
on (transliterated umlauts, other spellings of the legal form, swapped
digits). Results for those are reported separately, misses included.

Everything here is invented. No real company or person data.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

from .extracts import EXTRA_COLUMNS, SCHEMAS
from .validators import make_de_vat, make_iban

CUTOVER = date(2026, 12, 31)
COMPANY_CODE = "1000"
FIRST_CUSTOMER = 100000
FIRST_VENDOR = 300000
FIRST_MATERIAL = 1000000

COUNTRY_MIX = [("DE", 0.78), ("AT", 0.08), ("NL", 0.06), ("BE", 0.04), ("CH", 0.04)]
LOCALES = {"DE": "de_DE", "AT": "de_AT", "NL": "nl_NL", "BE": "nl_BE", "CH": "de_CH"}
LANGU = {"DE": "D", "AT": "D", "CH": "D", "NL": "N", "BE": "N"}
LEGAL = ["GmbH", "GmbH", "GmbH", "GmbH & Co. KG", "KG", "AG", "e.K.", "OHG", "UG (haftungsbeschränkt)"]
FOREIGN_LEGAL = {"AT": ["GmbH", "KG"], "NL": ["B.V."], "BE": ["BV", "NV"], "CH": ["AG", "GmbH"]}
TRADES = ["Haustechnik", "Elektro", "Metallbau", "Logistik", "Bürobedarf", "Verpackung",
          "Holzhandel", "Gastro Service", "Sanitär", "Baustoffe", "Druckerei", "Kältetechnik",
          "Werkzeuge", "Fahrzeugteile", "Lebensmittel", "Reinigung", "IT-Service", "Etiketten"]
MATERIAL_WORDS = ["Schraube", "Mutter", "Dichtung", "Kabel", "Rohr", "Winkel", "Platte",
                  "Folie", "Karton", "Ventil", "Filter", "Lager", "Scharnier", "Klemme"]
MATERIAL_EN = {"Schraube": "Screw", "Mutter": "Nut", "Dichtung": "Seal", "Kabel": "Cable",
               "Rohr": "Pipe", "Winkel": "Bracket", "Platte": "Plate", "Folie": "Film",
               "Karton": "Box", "Ventil": "Valve", "Filter": "Filter", "Lager": "Bearing",
               "Scharnier": "Hinge", "Klemme": "Clamp"}


class Builder:
    def __init__(self, seed=42, customers=1500, vendors=600, materials=1200):
        self.rnd = random.Random(seed)
        self.fake = {c: Faker(loc) for c, loc in LOCALES.items()}
        for i, f in enumerate(self.fake.values()):
            f.seed_instance(seed + i)
        self.n_cust, self.n_vend, self.n_mat = customers, vendors, materials
        self.t = {name: [] for name in SCHEMAS}
        self.labels = []
        self.banks = {}
        self.used_names = set()
        self.places = {}

    # ---------- helpers ----------

    def label(self, rule, obj, key, variant, holdout=False):
        self.labels.append({"rule": rule, "object": obj, "key": key,
                            "variant": variant, "holdout": "X" if holdout else ""})

    def country(self):
        x, acc = self.rnd.random(), 0
        for c, p in COUNTRY_MIX:
            acc += p
            if x <= acc:
                return c
        return "DE"

    def day(self, start, end):
        d = start + timedelta(days=self.rnd.randint(0, (end - start).days))
        return d.strftime("%Y%m%d")

    def company_name(self, cc):
        f = self.fake[cc]
        for _ in range(50):
            pattern = self.rnd.random()
            if pattern < 0.45:
                base = f"{f.last_name()} {self.rnd.choice(TRADES)}"
            elif pattern < 0.75:
                base = f.last_name()
            else:
                base = f"{f.last_name()} & {f.last_name()}"
            form = self.rnd.choice(FOREIGN_LEGAL.get(cc, LEGAL))
            name = f"{base} {form}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        return name

    def place(self, cc):
        """Postal code and city. Partners cluster in a few towns like in real
        data: a handful of big ones, a long tail of small ones."""
        if cc not in self.places:
            f = self.fake[cc]
            n = 150 if cc == "DE" else 25
            self.places[cc] = [(f.postcode(), f.city()) for _ in range(n)]
        pool = self.places[cc]
        weights = [1 / (i + 1) for i in range(len(pool))]
        return self.rnd.choices(pool, weights)[0]

    def address(self, cc):
        f = self.fake[cc]
        street = f.street_name()
        no = str(self.rnd.randint(1, 180))
        if self.rnd.random() < 0.1:
            no += self.rnd.choice("abc")
        postal, city = self.place(cc)
        return f"{street} {no}", postal, city

    def vat(self, cc):
        r = self.rnd
        if cc == "DE":
            return make_de_vat("".join(str(r.randint(0, 9)) for _ in range(8)).replace("0", "1", 1))
        if cc == "AT":
            return "ATU" + "".join(str(r.randint(0, 9)) for _ in range(8))
        if cc == "NL":
            return "NL" + "".join(str(r.randint(0, 9)) for _ in range(9)) + "B01"
        if cc == "BE":
            return "BE0" + "".join(str(r.randint(0, 9)) for _ in range(9))
        return ""  # CH is not in the EU VAT system

    def bank(self, cc):
        """Return (bank key, account, iban) and make sure the bank is in BNKA."""
        r = self.rnd
        if cc == "DE":
            blz = r.choice(self.de_blz)
            acc = str(r.randint(10**7, 10**10 - 1))
            return blz, acc, make_iban("DE", blz + acc.zfill(10))
        if cc == "AT":
            blz = r.choice(["20111", "12000", "32000", "14000", "38000"])
            acc = str(r.randint(10**9, 10**11 - 1)).zfill(11)
            key = blz
            iban = make_iban("AT", blz + acc)
        elif cc == "NL":
            key = r.choice(["ABNA", "INGB", "RABO", "TRIO", "SNSB"])
            acc = str(r.randint(10**8, 10**10 - 1)).zfill(10)
            iban = make_iban("NL", key + acc)
        elif cc == "BE":
            key = r.choice(["001", "068", "310", "735"])
            body = key + str(r.randint(0, 9999999)).zfill(7)
            chk = int(body) % 97 or 97
            acc = body[3:] + f"{chk:02d}"
            iban = make_iban("BE", body + f"{chk:02d}")
        else:
            key = r.choice(["00230", "00700", "08390", "09000"])
            acc = str(r.randint(10**10, 10**12 - 1)).zfill(12)
            iban = make_iban("CH", key + acc)
        if (cc, key) not in self.banks:
            self.add_bank(cc, key, f"Bank {cc}-{key}")
        return key, acc, iban

    def add_bank(self, cc, key, name):
        self.banks[(cc, key)] = True
        self.t["bnka"].append({"BANKS": cc, "BANKL": key, "BANKA": name,
                               "SWIFT": "", "LOEVM": ""})

    def activity(self, obj, pid, last=None, open_items=None):
        if last is None:
            last = self.day(date(2025, 1, 1), date(2026, 10, 20))
        if open_items is None:
            open_items = self.rnd.choice([0, 0, 1, 2, 3, 5, 8, 12])
        self.t["activity"].append({"OBJECT": obj, "ID": pid, "BUKRS": COMPANY_CODE,
                                   "LAST_POSTING": last, "OPEN_ITEMS": str(open_items)})

    # ---------- clean master data ----------

    def build_banks(self):
        names = ["Sparkasse", "Volksbank", "Raiffeisenbank", "Commerzbank", "Deutsche Bank",
                 "Postbank", "Sparda-Bank", "GLS Bank"]
        self.de_blz = []
        for i in range(30):
            blz = str(self.rnd.randint(10000000, 89999999))
            self.de_blz.append(blz)
            self.add_bank("DE", blz, f"{self.rnd.choice(names)} {self.fake['DE'].city()}")

    def build_customers(self):
        for i in range(self.n_cust):
            kunnr = str(FIRST_CUSTOMER + i)
            cc = self.country()
            public = cc == "DE" and self.rnd.random() < 0.02
            if public:
                city = self.fake["DE"].city()
                name = f"Stadtverwaltung {city}"
                street, postal, _ = self.address("DE")
                ktokd, anred = "OEFF", ""
            else:
                name = self.company_name(cc)
                street, postal, city = self.address(cc)
                ktokd = {"DE": "KUNA", "CH": "KUND"}.get(cc, "KUNE")
                anred = "Firma"
            vat, stcd1 = self.vat(cc), ""
            if cc == "DE" and not public and self.rnd.random() < 0.12:
                vat, stcd1 = "", f"{self.rnd.randint(200, 599)}/{self.rnd.randint(100, 999)}/{self.rnd.randint(10000, 99999)}"
            if public:
                vat, stcd1 = "", f"{self.rnd.randint(200, 599)}/{self.rnd.randint(100, 999)}/{self.rnd.randint(10000, 99999)}"
            local = name.split()[0].lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
            self.t["kna1"].append({
                "KUNNR": kunnr, "KTOKD": ktokd, "ANRED": anred, "NAME1": name, "NAME2": "",
                "STRAS": street, "PSTLZ": postal, "ORT01": city, "LAND1": cc, "SPRAS": LANGU[cc],
                "STCEG": vat, "STCD1": stcd1, "LIFNR": "", "LOEVM": "",
                "SMTP_ADDR": f"rechnung@{local}-{kunnr[-3:]}.example",
                "ZZ_LEITWEG": f"05314000-{self.rnd.randint(1000, 9999)}-{self.rnd.randint(10, 99)}" if public else "",
                "ERDAT": self.day(date(2008, 1, 1), date(2024, 12, 31)),
            })
            self.t["knb1"].append({"KUNNR": kunnr, "BUKRS": COMPANY_CODE, "AKONT": "140000", "LOEVM": ""})
            self.activity("customer", kunnr)
            if self.rnd.random() < 0.2:  # SEPA direct debit customers
                key, acc, iban = self.bank(cc)
                self.t["knbk"].append({"KUNNR": kunnr, "BANKS": cc, "BANKL": key, "BANKN": acc, "BKONT": ""})
                self.t["tiban"].append({"BANKS": cc, "BANKL": key, "BANKN": acc, "BKONT": "", "IBAN": iban})
            for _ in range(self.rnd.choice([0, 0, 1, 1, 2])):
                f = self.fake["DE"]
                self.t["knvk"].append({"PARNR": str(len(self.t["knvk"]) + 1).zfill(10), "KUNNR": kunnr,
                                       "NAMEV": f.first_name(), "NAME1": f.last_name(),
                                       "ABTNR": self.rnd.choice(["0001", "0003", "0005"]),
                                       "TELF1": f.phone_number()})

    def build_vendors(self):
        for i in range(self.n_vend):
            lifnr = str(FIRST_VENDOR + i)
            self.new_vendor(lifnr)

    def new_vendor(self, lifnr, cc=None, name=None, addr=None, vat=None):
        cc = cc or self.country()
        name = name or self.company_name(cc)
        street, postal, city = addr or self.address(cc)
        row = {
            "LIFNR": lifnr, "KTOKK": "KRED" if cc == "DE" else "KREE", "ANRED": "Firma",
            "NAME1": name, "NAME2": "", "STRAS": street, "PSTLZ": postal, "ORT01": city,
            "LAND1": cc, "SPRAS": LANGU[cc], "STCEG": self.vat(cc) if vat is None else vat,
            "STCD1": "", "KUNNR": "", "LOEVM": "", "SPERR": "",
            "ERDAT": self.day(date(2008, 1, 1), date(2024, 12, 31)),
        }
        row.update(self.vendor_contact(lifnr, name, cc))
        self.t["lfa1"].append(row)
        self.t["lfb1"].append({"LIFNR": lifnr, "BUKRS": COMPANY_CODE, "AKONT": "160000", "ZTERM": "ZB30"})
        key, acc, iban = self.bank(cc)
        self.t["lfbk"].append({"LIFNR": lifnr, "BANKS": cc, "BANKL": key, "BANKN": acc, "BKONT": "",
                               "KOINH": name})
        self.t["tiban"].append({"BANKS": cc, "BANKL": key, "BANKN": acc, "BKONT": "", "IBAN": iban})
        self.activity("vendor", lifnr)
        return row

    @staticmethod
    def vendor_contact(lifnr, name, cc):
        """Phone and invoice email for a vendor. Own random source per vendor,
        so adding these fields does not change any other generated value."""
        r = random.Random(f"contact-{lifnr}")
        prefix = {"DE": "+49 228", "AT": "+43 1", "NL": "+31 20", "BE": "+32 2", "CH": "+41 44"}[cc]
        slug = name.split()[0].lower()
        for k, v in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            slug = slug.replace(k, v)
        slug = "".join(ch for ch in slug if ch.isalnum()) or "firma"
        tld = {"DE": "de", "AT": "at", "NL": "nl", "BE": "be", "CH": "ch"}[cc]
        return {"TELF1": f"{prefix} {r.randint(100000, 9999999)}",
                "SMTP_ADDR": f"buchhaltung@{slug}-{lifnr[-3:]}.example.{tld}"}

    def build_materials(self):
        units = ["ST", "ST", "ST", "KAR", "PAL", "KG", "M", "ROL", "PAK"]
        for i in range(self.n_mat):
            matnr = str(FIRST_MATERIAL + i)
            word = self.rnd.choice(MATERIAL_WORDS)
            size = f"{self.rnd.randint(2, 80)}x{self.rnd.randint(5, 200)}"
            self.t["mara"].append({"MATNR": matnr, "MTART": self.rnd.choice(["HAWA", "HAWA", "ROH"]),
                                   "MEINS": self.rnd.choice(units), "LVORM": ""})
            self.t["makt"].append({"MATNR": matnr, "SPRAS": "D", "MAKTX": f"{word} {size}"})
            self.t["makt"].append({"MATNR": matnr, "SPRAS": "E", "MAKTX": f"{MATERIAL_EN[word]} {size}"})

    # ---------- planted errors ----------

    def pick(self, table, n, where=lambda r: True, taken=None):
        taken = taken if taken is not None else self.taken
        pool = [r for r in self.t[table] if where(r) and id(r) not in taken]
        chosen = self.rnd.sample(pool, min(n, len(pool)))  # small test sets have fewer candidates
        for r in chosen:
            taken.add(id(r))
        return chosen

    def plant_duplicates(self):
        customers = self.t["kna1"]
        next_no = FIRST_CUSTOMER + len(customers)

        def copy(r, variant, holdout):
            nonlocal next_no
            c = dict(r)
            c["KUNNR"] = str(next_no)
            next_no += 1
            c["STCEG"] = r["STCEG"] if self.rnd.random() < 0.25 else ""
            c["ERDAT"] = self.day(date(2015, 1, 1), date(2025, 12, 31))
            c["SMTP_ADDR"] = r["SMTP_ADDR"]
            self.mutate(c, variant)
            if c.pop("_orig_prefix", None):
                r["NAME1"] = "Gebr. " + r["NAME1"]
            customers.append(c)
            self.taken.add(id(c))
            self.t["knb1"].append({"KUNNR": c["KUNNR"], "BUKRS": COMPANY_CODE, "AKONT": "140000", "LOEVM": ""})
            self.activity("customer", c["KUNNR"])
            self.label("R01", "customer", f"{r['KUNNR']}|{c['KUNNR']}", variant, holdout)
            if c["LAND1"] == "DE" and not c["STCEG"] and not c["STCD1"]:
                self.label("R11", "customer", c["KUNNR"], "duplicate_without_tax_id")

        trained = ["case_spacing", "street_abbrev", "legal_form_dots", "name2_split"]
        holdout = ["umlaut_translit", "co_kg_spelling", "house_no_swap", "name_typo",
                   "district_and_postal", "gebr_abbrev"]
        src = self.pick("kna1", 64, lambda r: r["KTOKD"] != "OEFF" and r["LAND1"] == "DE")
        for i, r in enumerate(src[:40]):
            copy(r, trained[i % 4], False)
        for i, r in enumerate(src[40:]):
            copy(r, holdout[i % 6], True)

        # Two different firms in the same building, same family name. Must NOT match.
        for r in self.pick("kna1", 8, lambda r: r["KTOKD"] == "KUNA"):
            c = dict(r)
            c["KUNNR"] = str(next_no)
            next_no += 1
            family = r["NAME1"].split()[0]
            c["NAME1"] = f"{family} {self.rnd.choice(TRADES)} {self.rnd.choice(['GmbH', 'KG'])}"
            c["STCEG"] = self.vat("DE")
            customers.append(c)
            self.taken.add(id(c))
            self.t["knb1"].append({"KUNNR": c["KUNNR"], "BUKRS": COMPANY_CODE, "AKONT": "140000", "LOEVM": ""})
            self.activity("customer", c["KUNNR"])

        # Branches: same legal entity and VAT ID, other city. Separate accounts on purpose.
        for r in self.pick("kna1", 5, lambda r: r["KTOKD"] == "KUNA" and r["STCEG"]):
            c = dict(r)
            c["KUNNR"] = str(next_no)
            next_no += 1
            c["NAME2"] = "Niederlassung " + self.fake["DE"].city()
            c["STRAS"], c["PSTLZ"], c["ORT01"] = self.address("DE")
            customers.append(c)
            self.taken.add(id(c))
            self.t["knb1"].append({"KUNNR": c["KUNNR"], "BUKRS": COMPANY_CODE, "AKONT": "140000", "LOEVM": ""})
            self.activity("customer", c["KUNNR"])

        # same family name, different legal form, same town. Must NOT match.
        for r in self.pick("kna1", 10, lambda r: r["KTOKD"] == "KUNA"):
            c = dict(r)
            c["KUNNR"] = str(next_no)
            next_no += 1
            base = r["NAME1"].rsplit(" ", 1)[0] if not r["NAME1"].endswith(")") else r["NAME1"].split(" UG")[0]
            other = "KG" if "GmbH" in r["NAME1"] else "GmbH"
            c["NAME1"] = f"{base} {other}"
            c["STRAS"], _, _ = self.address("DE")
            c["STCEG"] = self.vat("DE")
            customers.append(c)
            self.taken.add(id(c))
            self.t["knb1"].append({"KUNNR": c["KUNNR"], "BUKRS": COMPANY_CODE, "AKONT": "140000", "LOEVM": ""})
            self.activity("customer", c["KUNNR"])

        # vendor duplicates
        vendors = self.t["lfa1"]
        next_v = FIRST_VENDOR + len(vendors)
        for i, r in enumerate(self.pick("lfa1", 15)):
            variant = (trained + holdout)[i % 8]
            c = dict(r)
            c["LIFNR"] = str(next_v)
            next_v += 1
            c["STCEG"] = ""
            self.mutate(c, variant)
            vendors.append(c)
            self.taken.add(id(c))
            self.t["lfb1"].append({"LIFNR": c["LIFNR"], "BUKRS": COMPANY_CODE, "AKONT": "160000", "ZTERM": "ZB30"})
            key, acc, iban = self.bank(c["LAND1"])
            self.t["lfbk"].append({"LIFNR": c["LIFNR"], "BANKS": c["LAND1"], "BANKL": key, "BANKN": acc,
                                   "BKONT": "", "KOINH": c["NAME1"]})
            self.t["tiban"].append({"BANKS": c["LAND1"], "BANKL": key, "BANKN": acc, "BKONT": "", "IBAN": iban})
            self.activity("vendor", c["LIFNR"])
            self.label("R01", "vendor", f"{r['LIFNR']}|{c['LIFNR']}", variant, variant in holdout)

    def mutate(self, c, variant):
        if variant == "case_spacing":
            c["NAME1"] = c["NAME1"].upper().replace(" ", "  ", 1)
        elif variant == "street_abbrev":
            s = c["STRAS"]
            c["STRAS"] = s.replace("straße", "str.").replace("Straße", "Str.") if "traße" in s else s.replace("str.", "straße")
            c["NAME1"] = c["NAME1"].replace(" & ", " und ")
        elif variant == "legal_form_dots":
            c["NAME1"] = c["NAME1"].replace("GmbH", "G.m.b.H.").replace("e.K.", "eK").replace("AG", "A.G.")
        elif variant == "name2_split":
            parts = c["NAME1"].split(" ")
            if len(parts) > 2:
                c["NAME1"], c["NAME2"] = " ".join(parts[:-1]), parts[-1]
            else:
                c["NAME1"] = c["NAME1"].lower()
        elif variant == "umlaut_translit":
            for k, v in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
                c["NAME1"] = c["NAME1"].replace(k, v)
                c["STRAS"] = c["STRAS"].replace(k, v)
            c["STRAS"] = c["STRAS"].replace("str.", "strasse")
        elif variant == "co_kg_spelling":
            if "& Co. KG" in c["NAME1"]:
                c["NAME1"] = c["NAME1"].replace("GmbH & Co. KG", "GmbH u. Co KG")
            else:
                c["NAME1"] = c["NAME1"].replace(" GmbH", " Gesellschaft mbH")
        elif variant == "house_no_swap":
            s, no = c["STRAS"].rsplit(" ", 1)
            if len(no) >= 2 and no[:2].isdigit():
                no = no[1] + no[0] + no[2:]
            else:
                no = str(int("".join(ch for ch in no if ch.isdigit()) or 1) + 2)
            c["STRAS"] = f"{s} {no}"
        elif variant == "district_and_postal":
            # same firm, entered with the district name and a mistyped postal code
            c["ORT01"] = c["ORT01"] + "-" + self.rnd.choice(["Mitte", "Nord", "Süd", "West"])
            p = c["PSTLZ"]
            c["PSTLZ"] = p[:-1] + str((int(p[-1]) + 1) % 10) if p[-1:].isdigit() else p
        elif variant == "gebr_abbrev":
            c["NAME1"] = "Gebrüder " + c["NAME1"]
            c["_orig_prefix"] = "Gebr. "
        elif variant == "name_typo":
            n = c["NAME1"]
            i = self.rnd.randint(1, max(1, min(6, len(n) - 2)))
            c["NAME1"] = n[:i] + n[i + 1] + n[i] + n[i + 2:]

    def plant_master_errors(self):
        # R02 missing fields and unmapped account groups
        for r in self.pick("kna1", 15):
            f = self.rnd.choice(["ORT01", "PSTLZ", "LAND1"])
            r[f] = ""
            self.label("R02", "customer", r["KUNNR"], f"missing_{f}")
        for r in self.pick("lfa1", 5):
            r["ORT01"] = ""
            self.label("R02", "vendor", r["LIFNR"], "missing_ORT01")
        for r in self.pick("kna1", 6):
            r["ORT01"] = self.rnd.choice(["unbekannt", "xxx", "-"])
            self.label("R02", "customer", r["KUNNR"], "placeholder_ORT01")
        for r in self.pick("kna1", 4):
            r["KTOKD"] = "ALT1"
            self.label("R02", "customer", r["KUNNR"], "unmapped_group")

        # R05 postal codes
        for r in self.pick("kna1", 8, lambda r: r["LAND1"] == "DE" and r["PSTLZ"]):
            r["PSTLZ"] = r["PSTLZ"][1:]
            self.label("R05", "customer", r["KUNNR"], "de_4_digits")
        for r in self.pick("kna1", 3, lambda r: r["LAND1"] == "DE" and r["PSTLZ"]):
            r["PSTLZ"] = "D-" + r["PSTLZ"]
            self.label("R05", "customer", r["KUNNR"], "country_prefix_in_postal", holdout=True)
        for r in self.pick("kna1", 4, lambda r: r["LAND1"] == "NL" and r["PSTLZ"]):
            r["PSTLZ"] = r["PSTLZ"][:4]
            self.label("R05", "customer", r["KUNNR"], "nl_no_letters")

        # R04 VAT IDs
        for r in self.pick("kna1", 10, lambda r: r["STCEG"].startswith("DE")):
            last = int(r["STCEG"][-1])
            r["STCEG"] = r["STCEG"][:-1] + str((last + 3) % 10)
            self.label("R04", "customer", r["KUNNR"], "check_digit")
        for r in self.pick("kna1", 5, lambda r: r["STCEG"].startswith("DE")):
            r["STCEG"] = r["STCEG"][:-2]
            self.label("R04", "customer", r["KUNNR"], "too_short")
        for r in self.pick("lfa1", 4, lambda r: r["LAND1"] == "AT"):
            r["STCEG"] = self.vat("DE")
            self.label("R04", "vendor", r["LIFNR"], "country_prefix")

        # R09 form of address
        for r in self.pick("kna1", 12, lambda r: r["ANRED"] == "Firma"):
            r["ANRED"] = self.rnd.choice(["Fa.", "Fima", "Company"])
            self.label("R09", "customer", r["KUNNR"], "unmapped_anred")
        for r in self.pick("kna1", 3, lambda r: r["ANRED"] == "Firma"):
            r["ANRED"] = "firma"
            self.label("R09", "customer", r["KUNNR"], "lowercase", holdout=True)
        for r in self.pick("lfa1", 4):
            r["ANRED"] = "Fa."
            self.label("R09", "vendor", r["LIFNR"], "unmapped_anred")

    def plant_bank_errors(self):
        tiban = {(r["BANKS"], r["BANKL"], r["BANKN"]): r for r in self.t["tiban"]}

        def iban_row(b):
            return tiban[(b["BANKS"], b["BANKL"], b["BANKN"])]

        de = lambda b: b["BANKS"] == "DE"
        for b in self.pick("lfbk", 10, de):
            t = iban_row(b)
            i = self.rnd.randint(12, 21)
            t["IBAN"] = t["IBAN"][:i] + str((int(t["IBAN"][i]) + 1) % 10) + t["IBAN"][i + 1:]
            self.label("R03", "vendor", b["LIFNR"], "checksum")
        for b in self.pick("lfbk", 5, de):
            t = iban_row(b)
            s = t["IBAN"]
            i = self.rnd.randint(13, 19)
            if s[i] == s[i + 1]:
                s = s[:i] + str((int(s[i]) + 1) % 10) + s[i + 1:]
            t["IBAN"] = s[:i] + s[i + 1] + s[i] + s[i + 2:]
            self.label("R03", "vendor", b["LIFNR"], "digit_swap", holdout=True)
        for b in self.pick("lfbk", 6, de):
            t = iban_row(b)
            new_acc = str(int(b["BANKN"]) + 1)
            t["BANKN"] = b["BANKN"] = new_acc  # LFBK changed, IBAN left as it was
            self.label("R03", "vendor", b["LIFNR"], "blz_account_mismatch")
        for b in self.pick("lfbk", 4, de):
            t = iban_row(b)
            t["BANKL"] = b["BANKL"] = "99999999"
            self.label("R03", "vendor", b["LIFNR"], "bank_not_in_bnka")
        for b in self.pick("lfbk", 5, de):
            self.t["tiban"].remove(iban_row(b))
            self.label("R03", "vendor", b["LIFNR"], "iban_missing")
        for b in self.pick("knbk", 5, de):
            t = iban_row(b)
            t["IBAN"] = t["IBAN"][:-1] + str((int(t["IBAN"][-1]) + 5) % 10)
            self.label("R03", "customer", b["KUNNR"], "checksum")

    def plant_cvi(self):
        # 20 clean linked pairs: customer and vendor with the same number
        for r in self.pick("kna1", 20, lambda r: r["KTOKD"] == "KUNA"):
            v = self.new_vendor(r["KUNNR"], cc="DE", name=r["NAME1"],
                                addr=(r["STRAS"], r["PSTLZ"], r["ORT01"]), vat=r["STCEG"])
            v["KUNNR"] = r["KUNNR"]
            r["LIFNR"] = r["KUNNR"]
            self.taken.add(id(v))
        # same company, not linked
        next_v = FIRST_VENDOR + len(self.t["lfa1"]) + 100
        for r in self.pick("kna1", 6, lambda r: r["KTOKD"] == "KUNA" and r["STCEG"]):
            v = self.new_vendor(str(next_v), cc="DE", name=r["NAME1"],
                                addr=(r["STRAS"], r["PSTLZ"], r["ORT01"]), vat=r["STCEG"])
            self.taken.add(id(v))
            self.label("R07", "customer", r["KUNNR"], "same_entity_unlinked")
            next_v += 1
        # link not mutual: customer -> vendor, vendor -> nobody
        for r in self.pick("kna1", 4, lambda r: r["KTOKD"] == "KUNA"):
            v = self.new_vendor(str(next_v), cc="DE", name=r["NAME1"],
                                addr=(r["STRAS"], r["PSTLZ"], r["ORT01"]), vat=r["STCEG"])
            r["LIFNR"] = v["LIFNR"]
            self.taken.add(id(v))
            self.label("R07", "customer", r["KUNNR"], "link_not_mutual")
            next_v += 1
        # link to a vendor that does not exist
        for r in self.pick("kna1", 3, lambda r: r["KTOKD"] == "KUNA"):
            r["LIFNR"] = "399999"
            self.label("R07", "customer", r["KUNNR"], "link_target_missing")
        # number collision: vendor got a number that a customer already has
        for r in self.pick("kna1", 5, lambda r: r["KTOKD"] == "KUNA" and not r["LIFNR"]):
            self.taken.add(id(self.new_vendor(r["KUNNR"], cc="DE")))
            self.label("R08", "customer", r["KUNNR"], "number_collision")

    def plant_activity(self):
        act = {(a["OBJECT"], a["ID"]): a for a in self.t["activity"]}
        free = lambda r: not r["LIFNR"] and r["LOEVM"] == ""
        for r in self.pick("kna1", 70, free):
            act[("customer", r["KUNNR"])]["LAST_POSTING"] = self.day(date(2012, 1, 1), date(2023, 6, 30))
            act[("customer", r["KUNNR"])]["OPEN_ITEMS"] = "0"
            self.label("R06", "customer", r["KUNNR"], "old_no_open_items")
        # old but with open items: must NOT be suggested
        for r in self.pick("kna1", 15, free):
            act[("customer", r["KUNNR"])]["LAST_POSTING"] = self.day(date(2014, 1, 1), date(2022, 12, 31))
            act[("customer", r["KUNNR"])]["OPEN_ITEMS"] = str(self.rnd.randint(1, 4))
        for r in self.pick("kna1", 10, free):
            act[("customer", r["KUNNR"])]["LAST_POSTING"] = self.day(date(2013, 1, 1), date(2021, 12, 31))
            act[("customer", r["KUNNR"])]["OPEN_ITEMS"] = "0"
            self.t["activity"].append({"OBJECT": "customer", "ID": r["KUNNR"], "BUKRS": "2000",
                                       "LAST_POSTING": self.day(date(2026, 1, 1), date(2026, 9, 30)),
                                       "OPEN_ITEMS": "1"})
        for r in self.pick("lfa1", 25, lambda r: not r["KUNNR"]):
            act[("vendor", r["LIFNR"])]["LAST_POSTING"] = self.day(date(2012, 1, 1), date(2023, 6, 30))
            act[("vendor", r["LIFNR"])]["OPEN_ITEMS"] = "0"
            self.label("R06", "vendor", r["LIFNR"], "old_no_open_items")
        # deletion flag set long ago, fine
        for r in self.pick("kna1", 20, free):
            r["LOEVM"] = "X"
            act[("customer", r["KUNNR"])]["LAST_POSTING"] = self.day(date(2012, 1, 1), date(2020, 12, 31))
            act[("customer", r["KUNNR"])]["OPEN_ITEMS"] = "0"
        # deletion flag but still busy
        for r in self.pick("kna1", 6, free):
            r["LOEVM"] = "X"
            act[("customer", r["KUNNR"])]["LAST_POSTING"] = self.day(date(2026, 3, 1), date(2026, 10, 15))
            self.label("R10", "customer", r["KUNNR"], "flag_but_recent_postings")

    def plant_einvoice(self):
        de = lambda r: r["LAND1"] == "DE" and r["KTOKD"] in ("KUNA",) and r["LOEVM"] == ""
        for r in self.pick("kna1", 25, de):
            r["STCEG"], r["STCD1"] = "", ""
            self.label("R11", "customer", r["KUNNR"], "no_tax_id")
        for r in self.pick("kna1", 30, de):
            r["SMTP_ADDR"] = ""
            self.label("R11", "customer", r["KUNNR"], "no_invoice_email")
        for r in self.pick("kna1", 5, de):
            r["SMTP_ADDR"] = r["SMTP_ADDR"].replace("@", " at ")
            self.label("R11", "customer", r["KUNNR"], "bad_invoice_email")
        public = [r for r in self.t["kna1"] if r["KTOKD"] == "OEFF" and id(r) not in self.taken]
        for r in self.pick("kna1", min(6, len(public)), lambda r: r["KTOKD"] == "OEFF"):
            r["ZZ_LEITWEG"] = ""
            self.label("R11", "customer", r["KUNNR"], "no_leitweg_id")

    def plant_contacts_and_materials(self):
        for r in self.pick("knvk", 5):
            r["KUNNR"] = str(190000 + self.rnd.randint(0, 9999))
            self.label("R12", "contact", r["PARNR"], "orphan")
        for r in self.pick("knvk", 5):
            r["NAME1"] = ""
            self.label("R12", "contact", r["PARNR"], "no_last_name")
        for r in self.pick("mara", 8):
            r["MEINS"] = self.rnd.choice(["STK", "Stck", "PCS"])
            self.label("R13", "material", r["MATNR"], "invalid_unit")
        en = [m for m in self.t["makt"] if m["SPRAS"] == "E"]
        for m in self.rnd.sample(en, 25):
            self.t["makt"].remove(m)
            self.label("R13", "material", m["MATNR"], "no_english_text")

    def plant_extract_errors(self):
        # a few rows exported twice, and company code rows of customers deleted from KNA1
        for r in self.pick("kna1", 3):
            self.t["kna1"].append(dict(r))
            self.label("R00", "customer", r["KUNNR"], "duplicate_row")
        for i in range(3):
            kunnr = str(180000 + i)
            self.t["knb1"].append({"KUNNR": kunnr, "BUKRS": COMPANY_CODE, "AKONT": "140000", "LOEVM": ""})
            self.label("R00", "customer", kunnr, "knb1_without_kna1")

    # ---------- run ----------

    def build(self):
        self.taken = set()
        self.build_banks()
        self.build_customers()
        self.build_vendors()
        self.build_materials()
        self.plant_duplicates()
        self.plant_cvi()
        self.plant_master_errors()
        self.plant_bank_errors()
        self.plant_activity()
        self.plant_einvoice()
        self.plant_contacts_and_materials()
        self.plant_extract_errors()
        return self

    def write(self, out):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for name, cols in SCHEMAS.items():
            cols = cols + EXTRA_COLUMNS.get(name, [])
            with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(self.t[name])
        with open(out / "labels.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["rule", "object", "key", "variant", "holdout"])
            w.writeheader()
            w.writerows(self.labels)
        return out


def generate(out, seed=42, customers=1500, vendors=600, materials=1200):
    return Builder(seed, customers, vendors, materials).build().write(out)
