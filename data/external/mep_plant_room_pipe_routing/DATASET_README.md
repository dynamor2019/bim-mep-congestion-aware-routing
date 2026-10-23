---
pretty_name: MEP Plant Room Pipe Routing Dataset
license: cc-by-4.0
language:
  - en
tags:
  - mep
  - pipe-routing
  - plant-room
  - construction
  - building-information-modeling
  - aec
---

# MEP Plant Room Pipe Routing Dataset


This repository provides case-level data for the paper:

**Automated Multi-pipe Routing in MEP Plant Rooms: A Preference-driven Multi-objective Coordination Framework for Design Prototyping**

**DOI:** 10.1016/j.autcon.2026.107201

**Link**: https://doi.org/10.1016/j.autcon.2026.107201

## Dataset Contents

Each case folder contains:

* `input_case.json`
  Scene input, including room boundary, maintenance areas, obstacles, pipe terminal points, pipe materials/diameters, main-layer height, and preference weights.

* `output_layout.json`
  Selected routing layout, including header paths, transition paths, and riser offset paths in the internal 2D coordinate system.

* `output_cost.json`
  Construction cost, maintenance indicators, lifecycle cost, and pipe-level cost breakdown.

* `visualizationMode.rvt`
  Optional Revit visualization model reconstructed from the selected layout. It is provided only for visual inspection and is not used for metric computation.


## License

CC BY 4.0
