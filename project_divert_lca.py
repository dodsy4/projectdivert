"""ISO 14040 / 14044-aligned life-cycle carbon model for material diversion.

This module quantifies the **net avoided greenhouse-gas emissions** (kg CO2e) of
diverting a material from landfill, following the four-phase LCA framework of
ISO 14040:2006 / ISO 14044:2006. See ``docs/lca-methodology.md`` for the goal &
scope definition, system boundary, impact-assessment method and data sources.

Summary of the model
--------------------
Functional unit: diversion of 1 tonne of a given material from landfill (UK).

Baseline (what diversion avoids):
    landfill_disposal + landfill_transport

Diversion scenario:
    collection_transport + reprocessing (recycle) / reuse_processing (reuse)
        - virgin_production_avoided        (the avoided-burden credit)

Net avoided emissions = baseline - diversion   (positive = a carbon benefit)

The module is pure Python (no Flask/DB imports) so it is straightforward to unit
test and to reuse from scripts.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

FUNCTIONAL_UNIT = "Diversion of 1 tonne of a given material from landfill (UK)"

MILES_TO_KM = 1.609344

_DEFAULT_FACTORS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "lca",
    "emission_factors.csv",
)

# Stages that make up each scenario.
BASELINE_STAGES = ("landfill_disposal", "landfill_transport")
RECYCLE_STAGES = ("collection_transport", "reprocessing", "virgin_production_avoided")
REUSE_STAGES = ("collection_transport", "reuse_processing", "virgin_production_avoided")

# Stages a diversion cannot be assessed without.
REQUIRED_STAGES = ("landfill_disposal", "virgin_production_avoided")

_WILDCARD = "*"


def _norm(name: str) -> str:
    return " ".join(str(name or "").replace("\xa0", " ").strip().lower().split())


@dataclass(frozen=True)
class EmissionFactor:
    material: str
    stage: str
    value: float
    unit: str
    gwp_basis: str
    source: str
    source_year: str
    source_url: str
    geography: str
    data_quality: str
    notes: str

    def citation(self) -> Dict[str, str]:
        return {
            "stage": self.stage,
            "value": self.value,
            "unit": self.unit,
            "gwp_basis": self.gwp_basis,
            "source": self.source,
            "source_year": self.source_year,
            "source_url": self.source_url,
            "data_quality": self.data_quality,
        }


@dataclass
class StageResult:
    stage: str
    kg_co2e: float
    scenario: str  # "baseline" | "diversion"
    factor: Dict[str, str]
    detail: str = ""


@dataclass
class LcaResult:
    material: str
    mass_tonnes: float
    pathway: str  # "recycle" | "reuse"
    functional_unit: str
    baseline_kg: float
    diversion_kg: float
    net_avoided_kg: float
    stages: List[Dict] = field(default_factory=list)
    factor_provenance: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def net_avoided_per_tonne(self) -> float:
        return self.net_avoided_kg / self.mass_tonnes if self.mass_tonnes else 0.0

    def as_dict(self) -> Dict:
        data = asdict(self)
        data["net_avoided_per_tonne"] = self.net_avoided_per_tonne
        return data


class LcaDataError(ValueError):
    """Raised when the factor dataset cannot support an assessment."""


@lru_cache(maxsize=4)
def load_factors(path: Optional[str] = None) -> Dict[Tuple[str, str], EmissionFactor]:
    """Load and index the emission-factor dataset by ``(material, stage)``."""
    path = path or _DEFAULT_FACTORS_PATH
    factors: Dict[Tuple[str, str], EmissionFactor] = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            material = (row.get("material") or "").strip()
            stage = (row.get("stage") or "").strip()
            if not material or not stage:
                continue
            try:
                value = float(row.get("value"))
            except (TypeError, ValueError):
                continue
            key = (_norm(material) if material != _WILDCARD else _WILDCARD, stage)
            factors[key] = EmissionFactor(
                material=material,
                stage=stage,
                value=value,
                unit=(row.get("unit") or "").strip(),
                gwp_basis=(row.get("gwp_basis") or "").strip(),
                source=(row.get("source") or "").strip(),
                source_year=(row.get("source_year") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
                geography=(row.get("geography") or "").strip(),
                data_quality=(row.get("data_quality") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
    if not factors:
        raise LcaDataError("Emission-factor dataset is empty: {}".format(path))
    return factors


def available_materials(path: Optional[str] = None) -> List[str]:
    seen = set()
    for ef in load_factors(path).values():
        if ef.material != _WILDCARD:
            seen.add(ef.material)
    return sorted(seen)


def _lookup(factors, material: str, stage: str) -> Optional[EmissionFactor]:
    return factors.get((_norm(material), stage)) or factors.get((_WILDCARD, stage))


def assess_diversion(
    material: str,
    mass_tonnes: float,
    *,
    collection_distance_km: float,
    landfill_distance_km: float,
    pathway: str = "recycle",
    factors_path: Optional[str] = None,
) -> LcaResult:
    """Assess one diversion against its landfill counterfactual.

    Parameters
    ----------
    material: material name (matched case-insensitively against the dataset).
    mass_tonnes: diverted mass, tonnes (> 0).
    collection_distance_km: road distance from the site to the reprocessor / reuse
        destination.
    landfill_distance_km: road distance from the site to the landfill it would
        otherwise have gone to (the counterfactual haul).
    pathway: ``"recycle"`` or ``"reuse"``.
    """
    pathway = (pathway or "recycle").strip().lower()
    if pathway not in ("recycle", "reuse"):
        raise LcaDataError("pathway must be 'recycle' or 'reuse', got {!r}".format(pathway))
    if mass_tonnes is None or mass_tonnes <= 0:
        raise LcaDataError("mass_tonnes must be greater than zero.")
    collection_distance_km = max(0.0, float(collection_distance_km or 0.0))
    landfill_distance_km = max(0.0, float(landfill_distance_km or 0.0))

    factors = load_factors(factors_path)
    warnings: List[str] = []

    for stage in REQUIRED_STAGES:
        if _lookup(factors, material, stage) is None:
            raise LcaDataError(
                'No "{}" factor is configured for material "{}". Add a row to '
                "data/lca/emission_factors.csv before assessing it.".format(stage, material)
            )

    stage_results: List[StageResult] = []

    def add_transport(stage: str, distance_km: float, scenario: str):
        ef = _lookup(factors, material, stage)
        if ef is None:
            warnings.append("Missing transport factor '{}'; treated as 0.".format(stage))
            return 0.0
        kg = ef.value * mass_tonnes * distance_km
        stage_results.append(
            StageResult(
                stage=stage,
                kg_co2e=kg,
                scenario=scenario,
                factor=ef.citation(),
                detail="{:.4g} kg CO2e/t-km x {:.3g} t x {:.3g} km".format(
                    ef.value, mass_tonnes, distance_km
                ),
            )
        )
        return kg

    def add_process(stage: str, scenario: str, sign: float = 1.0, optional: bool = False):
        ef = _lookup(factors, material, stage)
        if ef is None:
            if optional:
                warnings.append("No '{}' factor for '{}'; treated as 0.".format(stage, material))
                return 0.0
            raise LcaDataError("No '{}' factor for material '{}'.".format(stage, material))
        kg = sign * ef.value * mass_tonnes
        stage_results.append(
            StageResult(
                stage=stage,
                kg_co2e=kg,
                scenario=scenario,
                factor=ef.citation(),
                detail="{}{:.4g} kg CO2e/t x {:.3g} t".format(
                    "-" if sign < 0 else "", ef.value, mass_tonnes
                ),
            )
        )
        return kg

    # --- Baseline: landfill ------------------------------------------------
    baseline_kg = 0.0
    baseline_kg += add_process("landfill_disposal", "baseline")
    baseline_kg += add_transport("landfill_transport", landfill_distance_km, "baseline")

    # --- Diversion scenario ---------------------------------------------------
    diversion_kg = 0.0
    diversion_kg += add_transport("collection_transport", collection_distance_km, "diversion")
    if pathway == "recycle":
        diversion_kg += add_process("reprocessing", "diversion", optional=True)
    else:
        diversion_kg += add_process("reuse_processing", "diversion", optional=True)
    diversion_kg += add_process("virgin_production_avoided", "diversion", sign=-1.0)

    net_avoided_kg = baseline_kg - diversion_kg

    provenance = []
    seen_sources = set()
    for sr in stage_results:
        key = (sr.factor["source"], sr.factor["source_year"])
        if key in seen_sources:
            continue
        seen_sources.add(key)
        provenance.append(
            {
                "source": sr.factor["source"],
                "source_year": sr.factor["source_year"],
                "source_url": sr.factor["source_url"],
                "gwp_basis": sr.factor["gwp_basis"],
                "data_quality": sr.factor["data_quality"],
            }
        )

    return LcaResult(
        material=material,
        mass_tonnes=mass_tonnes,
        pathway=pathway,
        functional_unit=FUNCTIONAL_UNIT,
        baseline_kg=baseline_kg,
        diversion_kg=diversion_kg,
        net_avoided_kg=net_avoided_kg,
        stages=[asdict(sr) for sr in stage_results],
        factor_provenance=provenance,
        warnings=warnings,
    )


def assess_pathways(
    material: str,
    mass_tonnes: float,
    *,
    collection_distance_km: float,
    landfill_distance_km: float,
    factors_path: Optional[str] = None,
) -> Dict[str, LcaResult]:
    """Return both the reuse and recycle assessments for a material."""
    return {
        pathway: assess_diversion(
            material,
            mass_tonnes,
            collection_distance_km=collection_distance_km,
            landfill_distance_km=landfill_distance_km,
            pathway=pathway,
            factors_path=factors_path,
        )
        for pathway in ("reuse", "recycle")
    }
