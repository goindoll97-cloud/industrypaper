#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent PubChem chemical-candidate discovery for Study 3.

These compounds are NOT retrieved from the 29 regulatory targets.
Curated search names offer chemical-class diversity; seeded numeric PubChem CID
probes offer another reproducible (but nonrepresentative) sampling frame.
Nothing here determines legal target membership or NOT_FOUND gold labels.
"""
from __future__ import annotations

import random
from itertools import zip_longest

GENERAL_NAME_GROUPS = {
    "solvents": [
        "ethanol", "methanol", "isopropanol", "1-butanol", "acetone",
        "butanone", "ethyl acetate", "dimethyl sulfoxide", "tetrahydrofuran",
        "acetonitrile", "toluene", "xylene", "cyclohexane", "heptane",
        "diethyl ether", "dimethylformamide", "1,4-dioxane",
    ],
    "food_and_metabolism": [
        "D-glucose", "D-fructose", "sucrose", "lactose", "maltose", "ribose",
        "glycerol", "sorbitol", "xylitol", "ascorbic acid", "riboflavin",
        "niacinamide", "citric acid monohydrate", "urea", "glutathione",
        "creatinine", "choline",
    ],
    "amino_acids_biomolecules": [
        "glycine", "L-alanine", "L-valine", "L-leucine", "L-lysine",
        "L-serine", "L-tryptophan", "L-histidine", "L-phenylalanine",
        "L-cysteine", "L-glutamine", "L-methionine", "taurine", "uracil",
        "adenine", "thymine", "cholesterol",
    ],
    "pharmaceuticals": [
        "caffeine", "theobromine", "acetaminophen", "aspirin", "ibuprofen",
        "naproxen", "lidocaine", "metformin", "diphenhydramine",
        "cetirizine", "loratadine", "benzocaine", "nicotine",
        "salbutamol", "allopurinol", "gabapentin", "melatonin",
    ],
    "inorganic_chemicals": [
        "sodium chloride", "potassium chloride", "sodium bicarbonate",
        "potassium carbonate", "calcium carbonate", "magnesium sulfate",
        "zinc oxide", "titanium dioxide", "sodium sulfate",
        "potassium bromide", "ammonium sulfate", "sodium phosphate",
        "calcium phosphate", "copper sulfate", "aluminum oxide",
        "silicon dioxide", "iron(III) oxide",
    ],
    "natural_products": [
        "limonene", "menthol", "camphor", "vanillin", "cinnamaldehyde",
        "linalool", "eugenol", "thymol", "borneol", "geraniol",
        "citronellol", "beta-carotene", "quercetin", "curcumin",
        "resveratrol", "squalene", "alpha-pinene",
    ],
    "industrial_organics": [
        "benzaldehyde", "phenol", "styrene", "ethylbenzene", "aniline",
        "benzophenone", "cyclohexanone", "anisole", "hexamethylenediamine",
        "acrylamide", "adipic acid", "1-octanol", "dodecane",
        "benzyl alcohol", "cyclohexanol", "diphenyl ether", "ethyl oleate",
    ],
}


def independent_names():
    """Mix classes by round robin, not exhaust one category first."""
    groups = list(GENERAL_NAME_GROUPS.values())
    for items in zip_longest(*groups):
        for name in items:
            if name:
                yield name


def collect_general(client, add, from_synonyms, args, reserved_cids, quota):
    """Find up to quota records with CAS-CID reciprocal support; no gold labels.

    add() itself enforces global/stratum quotas and excludes baseline and
    catalog-enumerated CAS. Skips CAS-less and SMILES-less records.
    """
    seen_cids = set(int(x) for x in reserved_cids if str(x).isdigit())
    collected = 0
    source_counts = {"CURATED": 0, "CID_PROBE": 0}
    curated_goal = max(0, min(quota, round(quota * args.general_name_share)))

    def collect_one(cid, method, seed):
        nonlocal collected
        cid = int(cid)
        if cid in seen_cids:
            return False
        seen_cids.add(cid)
        prop = client.properties(cid)
        if not prop.get("smiles"):
            return False
        candidates = from_synonyms(client.synonyms(cid))
        if not candidates:
            return False
        for cas in candidates[:3]:
            if cid not in client.cids_for_name(cas):
                continue
            if add(cas, "GENERAL_CHEMICAL", method, "", seed=seed, cid=cid,
                   title=prop["title"], struct=prop["smiles"],
                   qc="CAS_CID_RECIPROCAL_PUG_REST",
                   difficulty=("INDEPENDENT_NAME_SEARCH" if method == "PUBCHEM_GENERAL_NAME"
                               else "INDEPENDENT_CID_PROBE")):
                collected += 1
                source_counts["CURATED" if method == "PUBCHEM_GENERAL_NAME" else "CID_PROBE"] += 1
                return True
        return False

    for name in independent_names():
        if collected >= curated_goal:
            break
        # Chemical class names are not chosen from the frozen regulatory catalog;
        # some hits could nevertheless be legally regulated and require review.
        for cid in client.cids_for_name(name)[:2]:
            if collect_one(cid, "PUBCHEM_GENERAL_NAME", name):
                break

    rng = random.Random(args.random_seed)
    population = range(args.random_cid_min, args.random_cid_max + 1)
    num_probes = min(args.random_cid_probes, len(population))
    for cid in rng.sample(population, num_probes):
        if collected >= quota:
            break
        collect_one(cid, "PUBCHEM_RANDOM_CID_PROBE",
                    f"SEED={args.random_seed};RANGE={args.random_cid_min}-{args.random_cid_max}")

    # If random CID probes yield too few usable CAS records, continue the
    # curated-name frame. This fallback is explicit in discovery_method.
    if collected < quota:
        for name in independent_names():
            if collected >= quota:
                break
            for cid in client.cids_for_name(name)[:2]:
                if collect_one(cid, "PUBCHEM_GENERAL_NAME", name):
                    break
    return {"collected": collected, "by_subframe": source_counts,
            "general_target": quota, "random_cid_probes": num_probes}
