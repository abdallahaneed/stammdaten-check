from dataclasses import dataclass, field, asdict

# Penalty per record, used by scoring.py
SEVERITY_WEIGHT = {"blocker": 1.0, "error": 0.6, "warning": 0.25, "info": 0.0}


@dataclass
class Finding:
    rule: str
    severity: str
    object: str          # customer, vendor, material
    key: str             # KUNNR / LIFNR / MATNR
    field: str           # SAP field, e.g. KNA1-STCEG
    message: str
    fix: str = ""
    related: str = ""    # other key, e.g. duplicate partner

    def as_dict(self):
        return asdict(self)


@dataclass
class Rule:
    id: str
    title: str
    paths: tuple          # ("brownfield", "greenfield")
    func: object
    description: str = ""


REGISTRY = {}


def rule(id, title, paths=("brownfield", "greenfield")):
    def wrap(func):
        REGISTRY[id] = Rule(id, title, tuple(paths), func, (func.__doc__ or "").strip())
        return func
    return wrap


@dataclass
class Context:
    tables: dict
    ref: dict
    config: dict
    db: object = None          # sqlite3 connection with the extracts loaded
    vies: object = None        # optional online checker
    extra: dict = field(default_factory=dict)

    def cfg(self, section, key, default=None):
        return self.config.get(section, {}).get(key, default)
