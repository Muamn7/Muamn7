#!/usr/bin/env bash
# Re-converts every source model into assets/imported/.
#
# Source .glb files are not in the repository (see CREDITS.md for why). Point
# ASHEN_SOURCE_DIR at wherever you keep them and run this from the repo root:
#
#     ASHEN_SOURCE_DIR=~/Downloads/models ./tools/import_assets.sh
#
# The game runs without any of these - every imported model has a procedural
# fallback - so a missing source file is a warning, not an error.

set -u

SRC="${ASHEN_SOURCE_DIR:-$HOME/models}"
OUT="assets/imported"
CONV="python3 tools/glb2g3dj.py"

convert() {
    local file="$1"; shift
    local path
    # Match on a suffix so the sandbox's hashed upload names work too.
    path=$(find "$SRC" -name "*$file" -print -quit 2>/dev/null)
    if [ -z "$path" ]; then
        echo "  skip: no source matching *$file in $SRC"
        return
    fi
    $CONV "$path" "$OUT" "$@"
}

echo "importing from $SRC"

# --- characters ---------------------------------------------------------
# A fully rigged enemy with 14 animations: idle, step, jab, charge, flinch.
convert scarecrow__ghost_rider_2007_video_game_ps2.glb \
        --name hollow_reaper --scale 0.48 --floor --center

# Static, no rig - used as a boss driven by whole-body motion.
convert bibeast_the_incredible_hulk_2008_game.glb \
        --name twin_horror --scale 0.38 --floor --center

# No animations, so flatten the rig away and keep it as an NPC statue.
convert viking_lowpoly.glb \
        --name wanderer --unskin --pitch -90 --scale 0.95 --floor --center

# --- weapons ------------------------------------------------------------
# The viking's axe, lifted out on its own and re-centred on its grip.
convert viking_lowpoly.glb \
        --name weapon_axe --unskin --only-mesh 'axe1' --pitch -90 --scale 1.0 --center --floor

# --- props --------------------------------------------------------------
convert church.glb --name chapel --scale 2.6 --floor --center
convert ree.glb    --name tree   --scale 0.047 --floor --center

echo "done - imported models are in $OUT/models"
