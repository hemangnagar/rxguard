from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache

from .mfp_models import MfpDeposit, MfpDrugProduct, MfpFill
from .models import SourceFact

# The ledger the demo page and the API both serve. Entirely synthetic and
# deterministic: drug names and 2026 WAC/MFP context appear for realism, the
# prices are representative, and every identifier is fabricated. AS_OF is
# pinned so the dataset replays identically forever.
AS_OF = date(2026, 9, 2)

_DRUGS = {
    "eliquis":   ("Eliquis 5 mg", "apixaban", "00003-0894-21", "60 tabs (30-day)", "Bristol Myers Squibb", "594.00", "231.00"),
    "jardiance": ("Jardiance 25 mg", "empagliflozin", "00597-0153-30", "30 tabs (30-day)", "Boehringer Ingelheim", "611.00", "197.00"),
    "xarelto":   ("Xarelto 20 mg", "rivaroxaban", "50458-0579-30", "30 tabs (30-day)", "Janssen", "542.00", "197.00"),
    "januvia":   ("Januvia 100 mg", "sitagliptin", "00006-0277-31", "30 tabs (30-day)", "Merck", "563.00", "113.00"),
    "farxiga":   ("Farxiga 10 mg", "dapagliflozin", "00310-6210-30", "30 tabs (30-day)", "AstraZeneca", "556.00", "178.50"),
    "entresto":  ("Entresto 24/26 mg", "sacubitril/valsartan", "00078-0659-20", "60 tabs (30-day)", "Novartis", "618.00", "295.00"),
    "novolog":   ("NovoLog FlexPen", "insulin aspart", "00169-6339-10", "5 × 3 mL pens", "Novo Nordisk", "347.00", "119.00"),
    "enbrel":    ("Enbrel 50 mg SureClick", "etanercept", "58406-0435-04", "4 auto-injectors", "Amgen", "7105.00", "2355.00"),
}

# (drug, fill_date, outcome, arg)
#   P: paid in full <arg> days after MTF transmission
#   S: short-paid — deposit of arg[0] dollars, arg[1] days after transmission
#   O: no deposit, past the 14-day window at AS_OF
#   N: no deposit, still inside the window (or window not yet elapsed)
_FILLS = (
    ("eliquis", "2026-06-22", "P", 16), ("jardiance", "2026-06-23", "P", 21), ("novolog", "2026-06-24", "P", 13),
    ("xarelto", "2026-06-25", "P", 24), ("eliquis", "2026-06-26", "P", 19),
    ("januvia", "2026-06-29", "P", 27), ("farxiga", "2026-06-30", "P", 18), ("eliquis", "2026-07-01", "P", 22),
    ("entresto", "2026-07-02", "P", 20),
    ("eliquis", "2026-07-06", "P", 17), ("jardiance", "2026-07-07", "P", 25), ("novolog", "2026-07-08", "P", 14),
    ("xarelto", "2026-07-09", "P", 21), ("farxiga", "2026-07-10", "P", 23),
    ("eliquis", "2026-07-13", "P", 19), ("januvia", "2026-07-14", "O", None), ("jardiance", "2026-07-15", "P", 26),
    ("entresto", "2026-07-16", "P", 18), ("novolog", "2026-07-17", "P", 20),
    ("eliquis", "2026-07-20", "P", 22), ("xarelto", "2026-07-21", "O", None), ("farxiga", "2026-07-22", "P", 19),
    ("enbrel", "2026-07-23", "S", ("4137.50", 23)), ("jardiance", "2026-07-24", "P", 21),
    ("eliquis", "2026-07-27", "P", 24), ("januvia", "2026-07-28", "P", 17), ("novolog", "2026-07-29", "O", None),
    ("entresto", "2026-07-30", "P", 25),
    ("enbrel", "2026-08-03", "O", None), ("eliquis", "2026-08-04", "P", 20), ("jardiance", "2026-08-05", "O", None),
    ("xarelto", "2026-08-06", "P", 18), ("farxiga", "2026-08-07", "P", 22),
    ("eliquis", "2026-08-10", "P", 16), ("januvia", "2026-08-11", "P", 21), ("novolog", "2026-08-12", "P", 19),
    ("entresto", "2026-08-13", "O", None), ("jardiance", "2026-08-14", "P", 17),
    ("eliquis", "2026-08-17", "N", None), ("xarelto", "2026-08-18", "P", 15), ("farxiga", "2026-08-19", "S", ("301.00", 20)),
    ("eliquis", "2026-08-24", "N", None), ("januvia", "2026-08-25", "N", None), ("jardiance", "2026-08-26", "N", None),
    ("novolog", "2026-08-27", "N", None),
    ("eliquis", "2026-08-31", "N", None), ("entresto", "2026-09-01", "N", None),
)


def _fnv1a32(text: str) -> int:
    """Same 32-bit FNV-1a the demo page uses, so both surfaces derive
    identical synthetic dates and reference ids from one spec table."""
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


@lru_cache(maxsize=1)
def load_mfp_fills() -> tuple[MfpFill, ...]:
    fills: list[MfpFill] = []
    for i, (key, fill_iso, outcome, arg) in enumerate(_FILLS):
        display, generic, ndc, package, manufacturer, wac, mfp = _DRUGS[key]
        fill_date = date.fromisoformat(fill_iso)
        h = _fnv1a32(key + fill_iso)
        transmitted = fill_date + timedelta(days=2 + (h % 3))
        rx_number = str(701000 + ((h % 89000) + i * 37) % 89000).zfill(6)

        deposit = None
        if outcome in ("P", "S"):
            if outcome == "P":
                amount, days = Decimal(wac) - Decimal(mfp), arg
            else:
                amount, days = Decimal(arg[0]), arg[1]
            deposit = MfpDeposit(
                amount=SourceFact(
                    value=amount,
                    source_ref=f"bank:ACH-{910000000 + (h % 89999999)}",
                    description="Operating account ACH deposit",
                ),
                deposit_date=transmitted + timedelta(days=days),
            )

        fills.append(
            MfpFill(
                id=f"C{i + 1:03d}",
                rx_number=rx_number,
                drug=MfpDrugProduct(
                    display=display, generic=generic, ndc=ndc,
                    package=package, manufacturer=manufacturer,
                ),
                fill_date=fill_date,
                adjudication_ref=f"claim:D0-{1000000 + (h % 8999999)}",
                transmitted_date=transmitted,
                transmission_ref=f"mtf:MTF-26-{200000 + (h % 700000):06d}",
                acquisition=SourceFact(
                    value=Decimal(wac),
                    source_ref=f"invoice:INV-{280000 + (h % 19000)}/L{1 + (h % 22)}",
                    description="Wholesaler invoice line (EDI 810)",
                ),
                mfp_price=SourceFact(
                    value=Decimal(mfp),
                    source_ref=f"cms:mfp-2026#{ndc}",
                    description="CMS negotiated-price public file (2026)",
                ),
                deposit=deposit,
            )
        )
    return tuple(fills)


def get_mfp_fill(fill_id: str) -> MfpFill:
    for fill in load_mfp_fills():
        if fill.id == fill_id:
            return fill
    raise KeyError(fill_id)
