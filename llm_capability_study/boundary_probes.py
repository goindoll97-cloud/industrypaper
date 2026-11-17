# -*- coding: utf-8 -*-
"""Curated PubChem search names for BOUNDARY candidates (structural neighbours of the 29 targets).

These names are discovery probes only. They are NOT regulatory evidence and NOT labels:
a probe may turn out to be inside a target (e.g. a salt of a listed parent) or outside it
(e.g. an ester, an analogue acid, a different metal). The human reviewer decides.

kind:
  ANALOGUE     same chemical family / one structural step away from a listed member
  DERIVATIVE   ester, amide, anhydride, lactone or other non-salt derivative of a listed parent
  SALT_VARIANT salt, possibly of a listed parent with an unlisted counter-ion (or vice versa)
"""
from __future__ import annotations

from itertools import zip_longest

BOUNDARY_PROBES = {
    "CG::CRVI_COMPOUNDS": [
        ("sodium molybdate", "ANALOGUE"), ("sodium tungstate", "ANALOGUE"),
        ("potassium permanganate", "ANALOGUE"), ("chromium(III) sulfate", "ANALOGUE"),
        ("chromium(III) oxide", "ANALOGUE"), ("chromium(III) nitrate", "ANALOGUE"),
        ("ammonium metavanadate", "ANALOGUE"), ("sodium selenate", "ANALOGUE"),
    ],
    "CG::LEAD_COMPOUNDS": [
        ("tin(II) chloride", "ANALOGUE"), ("bismuth nitrate", "SALT_VARIANT"),
        ("zinc nitrate", "SALT_VARIANT"), ("barium nitrate", "SALT_VARIANT"),
        ("calcium stearate", "SALT_VARIANT"), ("zinc acetate", "SALT_VARIANT"),
        ("strontium nitrate", "SALT_VARIANT"), ("tin(II) acetate", "SALT_VARIANT"),
        ("bismuth subcarbonate", "ANALOGUE"), ("tin(IV) oxide", "ANALOGUE"),
    ],
    "CG::MG_SALTS": [
        ("crystal violet", "ANALOGUE"), ("brilliant green", "ANALOGUE"),
        ("methyl violet 2B", "ANALOGUE"), ("ethyl violet", "ANALOGUE"),
        ("pararosaniline", "ANALOGUE"), ("rhodamine B", "ANALOGUE"),
        ("methylene blue", "ANALOGUE"), ("auramine O", "ANALOGUE"),
    ],
    "CG::NONYLPHENOL_NPE": [
        ("4-octylphenol", "ANALOGUE"), ("4-dodecylphenol", "ANALOGUE"),
        ("4-tert-butylphenol", "ANALOGUE"), ("2,4-di-tert-butylphenol", "ANALOGUE"),
        ("1-nonanol", "ANALOGUE"), ("4-heptylphenol", "ANALOGUE"),
        ("nonylbenzene", "ANALOGUE"), ("bisphenol A", "ANALOGUE"),
    ],
    "CG::TBT_TRIALKYLTIN": [
        ("dibutyltin dichloride", "ANALOGUE"), ("tetrabutyltin", "ANALOGUE"),
        ("butyltin trichloride", "ANALOGUE"), ("triphenyltin hydroxide", "ANALOGUE"),
        ("cyhexatin", "ANALOGUE"), ("trimethyltin chloride", "ANALOGUE"),
        ("dioctyltin dichloride", "ANALOGUE"), ("tin(IV) chloride", "ANALOGUE"),
    ],
    "PS::110-15-6": [
        ("glutaric acid", "ANALOGUE"), ("adipic acid", "ANALOGUE"),
        ("fumaric acid", "ANALOGUE"), ("maleic acid", "ANALOGUE"),
        ("diethyl succinate", "DERIVATIVE"), ("succinic anhydride", "DERIVATIVE"),
        ("succinimide", "DERIVATIVE"), ("sodium fumarate", "SALT_VARIANT"),
    ],
    "PS::110-85-0": [
        ("morpholine", "ANALOGUE"), ("piperidine", "ANALOGUE"),
        ("1-methylpiperazine", "DERIVATIVE"), ("homopiperazine", "ANALOGUE"),
        ("piperazine adipate", "SALT_VARIANT"), ("piperazine citrate", "SALT_VARIANT"),
    ],
    "PS::113-00-8": [
        ("urea", "ANALOGUE"), ("arginine", "DERIVATIVE"),
        ("metformin hydrochloride", "DERIVATIVE"), ("guanidine carbonate", "SALT_VARIANT"),
        ("aminoguanidine bicarbonate", "SALT_VARIANT"), ("creatine", "DERIVATIVE"),
    ],
    "PS::144-62-7": [
        ("malonic acid", "ANALOGUE"), ("sodium malonate", "SALT_VARIANT"),
        ("diethyl oxalate", "DERIVATIVE"), ("calcium oxalate", "SALT_VARIANT"),
        ("oxamide", "DERIVATIVE"), ("ammonium oxalate", "SALT_VARIANT"),
    ],
    "PS::50-21-5": [
        ("glycolic acid", "ANALOGUE"), ("sodium glycolate", "SALT_VARIANT"),
        ("ethyl lactate", "DERIVATIVE"), ("lactide", "DERIVATIVE"),
        ("propionic acid", "ANALOGUE"), ("sodium propionate", "SALT_VARIANT"),
        ("tartaric acid", "ANALOGUE"), ("mandelic acid", "ANALOGUE"),
    ],
    "PS::64-19-7": [
        ("sodium formate", "SALT_VARIANT"), ("ammonium acetate", "SALT_VARIANT"),
        ("ethyl acetate", "DERIVATIVE"), ("acetic anhydride", "DERIVATIVE"),
        ("sodium trifluoroacetate", "SALT_VARIANT"), ("chloroacetic acid", "ANALOGUE"),
        ("butyric acid", "ANALOGUE"),
    ],
    "PS::65-85-0": [
        ("phthalic acid", "ANALOGUE"), ("sodium 4-hydroxybenzoate", "SALT_VARIANT"),
        ("methyl benzoate", "DERIVATIVE"), ("benzamide", "DERIVATIVE"),
        ("benzyl alcohol", "ANALOGUE"), ("p-toluic acid", "ANALOGUE"),
        ("ammonium benzoate", "SALT_VARIANT"),
    ],
    "PS::69-72-7": [
        ("acetylsalicylic acid", "DERIVATIVE"), ("methyl salicylate", "DERIVATIVE"),
        ("4-aminosalicylic acid", "ANALOGUE"), ("choline salicylate", "SALT_VARIANT"),
        ("salicylamide", "DERIVATIVE"), ("magnesium salicylate", "SALT_VARIANT"),
    ],
    "PS::77-92-9": [
        ("malic acid", "ANALOGUE"), ("sodium malate", "SALT_VARIANT"),
        ("triethyl citrate", "DERIVATIVE"), ("ammonium citrate", "SALT_VARIANT"),
        ("ferric citrate", "SALT_VARIANT"), ("calcium citrate", "SALT_VARIANT"),
        ("isocitric acid", "ANALOGUE"),
    ],
}


def probe_plan():
    """Round-robin over targets so that an early stop keeps every target represented."""
    queues = [[(tid, name, kind) for name, kind in items] for tid, items in BOUNDARY_PROBES.items()]
    for batch in zip_longest(*queues):
        for item in batch:
            if item:
                yield item
