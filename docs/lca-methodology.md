# Carbon accounting methodology — material diversion LCA

This document describes the life-cycle assessment (LCA) behind Project Divert's
carbon engine (`project_divert_lca.py`, factor dataset `data/lca/emission_factors.csv`).
It follows the four-phase framework of **ISO 14040:2006** and **ISO 14044:2006**:
goal & scope, inventory analysis, impact assessment, interpretation.

> **Status.** This is an attributional LCA built on *published secondary data*.
> It has **not** been subject to the independent critical review that ISO 14044
> §6.3 requires for a comparative assertion disclosed to the public. Results are
> intended for internal decision support and customer reporting, described as
> "ISO 14040/14044-aligned", not as a certified or critically-reviewed LCA.

---

## 1. Goal and scope

### 1.1 Goal
Quantify the **net avoided greenhouse-gas emissions** of diverting a surplus
construction or office material from landfill into reuse or recycling, so that:

- customers can report the Scope 3 benefit of a diversion, and
- operations can compare reuse vs recycling routes for a given material and site.

Intended audience: internal operations and Project Divert customers. Comparative
assertions are not disclosed to the public without prior critical review.

### 1.2 Functional unit
**Diversion of 1 tonne of a given material from landfill, in the UK.**

User inputs are converted to tonnes before assessment (`_diversion_mass_tonnes`
in `app.py`): tonnes and kilograms directly; carpet tiles by area at
~4.3 kg/m²; per-item quantities via an approximate unit-mass table.

### 1.3 System boundary
Attributional, **cradle-to-grave**, with an avoided-burden credit for displaced
virgin production.

```
                         ┌─────────────── BASELINE (what diversion avoids) ───────────────┐
   material at site ──►  haul to landfill  ──►  landfill disposal (decomposition, methane)
                         └───────────────────────────────────────────────────────────────┘

                         ┌─────────────── DIVERSION SCENARIO ────────────────────────────┐
   material at site ──►  collection transport ──►  reprocessing / reuse preparation
                                                   ──►  (−) credit: virgin production avoided
                         └───────────────────────────────────────────────────────────────┘

   Net avoided emissions  =  BASELINE  −  DIVERSION SCENARIO      (positive = a carbon benefit)
```

Life-cycle stages modelled (see `project_divert_lca.py`):

| Stage | Scenario | Description |
|---|---|---|
| `landfill_disposal` | baseline | Emissions from disposing 1 t of the material to landfill (dominated by landfill methane for biodegradable materials; near-zero for inert materials). |
| `landfill_transport` | baseline | Road haul from site to the landfill it would otherwise have used. |
| `collection_transport` | diversion | Road haul from site to the reprocessor / reuse destination. |
| `reprocessing` | diversion (recycle) | Process energy to sort, clean and re-form the recovered material. |
| `reuse_processing` | diversion (reuse) | Energy to inspect, clean and lightly refurbish for direct reuse. |
| `virgin_production_avoided` | diversion (credit) | Cradle-to-gate emissions of the virgin material displaced by the recovered material — applied as a negative term. |

### 1.4 Cut-off criteria
Excluded: capital goods (vehicles, plant, buildings), employee commuting,
packaging, and use-phase emissions (materials are assumed functionally
equivalent). Transport is modelled one-way, laden, with no allocation of the
return leg.

### 1.5 Allocation
Where a reprocessing route yields multiple outputs, published factors that
already embed the source dataset's allocation choice are used as-is
(substitution / system expansion for the avoided-virgin credit; the source is
recorded per factor in `data_quality`).

---

## 2. Life-cycle inventory (LCI)

All factors are **secondary data** from recognised published datasets. Each row
in `data/lca/emission_factors.csv` records: `value`, `unit`, `gwp_basis`,
`source`, `source_year`, `source_url`, `geography`, `data_quality`, `notes`.

| Data need | Primary source | Notes |
|---|---|---|
| Landfill disposal by material | **UK Government GHG Conversion Factors for Company Reporting (DESNZ)**, "Waste disposal" table | Inert materials (metal, glass, plastics, aggregate) ≈ 1–9 kg CO₂e/t; biodegradable (paper, wood, textiles) ≈ 400–1,200 kg CO₂e/t driven by landfill methane. Re-verify exact cells on each annual update. |
| Road transport | **DESNZ Conversion Factors**, "Freighting goods" — HGV, average laden, including well-to-tank | Applied per tonne·km to every road leg. |
| Reprocessing energy | **WRAP** recycling studies; **FEVE** for glass | Process energy only, not the avoided-burden credit. |
| Virgin production avoided | **Inventory of Carbon & Energy (ICE) database v3.0** (Circular Ecology); WRAP; sector EPDs | Cradle-to-gate embodied carbon of the displaced virgin material. |
| Legacy project values | Retained where already cited (DEFRA 2006, WARM, manufacturer analyses) | Flagged `secondary-legacy` and earmarked for refresh. |

Source links:

- UK Government GHG Conversion Factors: <https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2024>
- DESNZ 2024 methodology paper: <https://assets.publishing.service.gov.uk/media/66a9fe4ca3c2a28abb50da4a/2024-greenhouse-gas-conversion-factors-methodology.pdf>
- ICE database v3.0: <https://circularecology.com/embodied-carbon-footprint-database.html>
- WRAP resources: <https://wrap.org.uk/resources>
- FEVE glass recycling: <https://feve.org/wp-content/uploads/2016/04/FEVE-brochure-Recycling-Why-glass-always-has-a-happy-CO2-ending-.pdf>

### 2.1 Data quality
Each factor carries a `data_quality` tag: `secondary-published` (taken directly
from a named published table), `secondary-estimate` (derived/interpolated from
published work), `secondary-proxy` (a related material used as a stand-in), or
`secondary-legacy` (inherited from the original project dataset, pending
refresh). Transport distances are real road distances from the Google Maps
Distance Matrix API; where the API is unavailable the assessment fails rather
than guessing.

---

## 3. Life-cycle impact assessment (LCIA)

- **Impact category:** climate change only.
- **Indicator:** mass of CO₂-equivalent (kg CO₂e).
- **Characterisation:** IPCC GWP100. Factors sourced from DESNZ 2024 use the
  IPCC AR5 GWP100 set adopted by that dataset; the engine reports in line with
  the source dataset's GWP basis, recorded per factor in `gwp_basis`.
- No normalisation or weighting is applied (single category).

Computation (`assess_diversion`):

```
baseline_kg   = landfill_disposal·m + transport·m·d_landfill
diversion_kg  = transport·m·d_collection + (reprocessing | reuse_processing)·m
                    − virgin_production_avoided·m
net_avoided_kg = baseline_kg − diversion_kg
```

where `m` is mass in tonnes and `d` is one-way road distance in km.

---

## 4. Interpretation

### 4.1 Typical results
- **Metals** show the largest benefit: landfill disposal is negligible but the
  avoided primary-production credit is very large (steel ≈ 2.4 t CO₂e/t,
  aluminium ≈ 13 t CO₂e/t).
- **Paper, wood, textiles** benefit mainly by avoiding landfill methane.
- **Inert aggregates** show a small benefit that can be erased by a long
  collection haul — the model will show this explicitly in the stage breakdown.

### 4.2 Key limitations
1. Secondary data only; not independently critically reviewed.
2. Single impact category (climate change) — burden-shifting to other impacts
   (water, toxicity, land use) is not captured.
3. Landfill factors assume UK landfill gas capture rates from the source
   dataset; site-specific gas capture is not modelled.
4. The avoided-virgin credit assumes 1:1 functional substitution of recovered
   for virgin material, which overstates the benefit where recovered material
   substitutes at a lower rate or into a lower-grade application.
5. Biogenic carbon and sequestration in timber are excluded (conservative).
6. Transport is one-way and laden; back-haul and consolidation are not modelled.

### 4.3 Maintenance
On each annual DESNZ conversion-factor release, re-verify every row tagged
`secondary-published` against the new spreadsheet and bump `source_year`.
Replace `secondary-proxy` and `secondary-legacy` rows with material-specific
data as it becomes available. The dataset is versioned in git; changes to
factors are reviewable in history.
