#!/usr/bin/env bash
# Export every printable part of trap_housing.scad to STL, plus preview renders.
# Needs OpenSCAD 2025 or newer (manifold backend). Usage: ./export_housing.sh [outdir]
set -euo pipefail
cd "$(dirname "$0")"
out="${1:-../print/housing}"
mkdir -p "$out"
parts=(head_box head_lid sun_shade saddle light_bar camera_cradle electronics_plate battery_cartridge battery_lid
       sht_shield knob clamp_knob card_guide lure_clip hole_template)
for p in "${parts[@]}"; do
    openscad --backend=manifold -q -D "part=\"$p\"" -o "$out/$p.stl" trap_housing.scad
    echo "$out/$p.stl"
done
render() {  # name part camera
    openscad --backend=manifold -q -D "part=\"$2\"" --imgsize=1600,1200 --viewall --autocenter --colorscheme=Tomorrow \
        --camera="$3" -o "$out/$1.png" trap_housing.scad
}
render view_assembly   assembly  0,0,0,62,0,215,0
render view_underside  assembly  0,0,0,112,0,200,0
render view_exploded   exploded  0,0,0,70,0,215,0
render view_section    section   0,0,0,90,0,0,0
echo "renders in $out"
