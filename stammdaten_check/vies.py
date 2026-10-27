"""Optional VAT check against the EU VIES REST service.

Off by default: it needs internet, VIES has daily outages per member state,
and you do not want 2,000 requests in a test run. Results are cached per run.
"""
import json
import time
import urllib.error
import urllib.request

URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{num}"


class Vies:
    def __init__(self, retries=3, timeout=10, pause=0.3):
        self.retries, self.timeout, self.pause = retries, timeout, pause
        self.cache = {}

    def check(self, vat):
        """Return 'valid', 'invalid' or 'unavailable'."""
        vat = vat.replace(" ", "").upper()
        if vat in self.cache:
            return self.cache[vat]
        cc, num = vat[:2], vat[2:]
        cc = "EL" if cc == "GR" else cc
        status = "unavailable"
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(URL.format(cc=cc, num=num), timeout=self.timeout) as resp:
                    data = json.load(resp)
                if data.get("userError") in ("MS_UNAVAILABLE", "TIMEOUT", "MS_MAX_CONCURRENT_REQ"):
                    raise urllib.error.URLError(data["userError"])
                status = "valid" if data.get("isValid") else "invalid"
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
        self.cache[vat] = status
        time.sleep(self.pause)
        return status
