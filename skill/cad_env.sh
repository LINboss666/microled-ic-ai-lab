# Load the IC617 / MMSIM environment for non-interactive SKILL runs.
#
# Why this exists: in this image the Cadence variables are not in any login profile.
# They live inside /etc/env/virtuoso, which is a wrapper that ends by launching the
# GUI ("virtuoso&"). Running that wrapper headless would open a window and never
# return, so we take only its `export` lines and none of its launch logic.
#
# License values are read from the wrapper at run time rather than copied into this
# file, so no license material is duplicated here and it stays in sync with the image.
: "${CDS_ENV_SRC:=/etc/env/virtuoso}"

if [ ! -r "$CDS_ENV_SRC" ]; then
  echo "cad_env.sh: cannot read $CDS_ENV_SRC" >&2
  return 1
fi

# /etc/env/virtuoso contains a typo: its LD_LIBRARY_PATH line reads
# "$D_LIBRARY_PATH" (missing the leading L), so under `set -u` sourcing it aborts.
# Pre-seed that name from the real LD_LIBRARY_PATH -- which is what the line meant.
: "${D_LIBRARY_PATH:=${LD_LIBRARY_PATH:-}}"
export D_LIBRARY_PATH

eval "$(grep -E '^[[:space:]]*export[[:space:]]+(MMSIM_ROOT|OA_HOME|CDS|CDS_LIC_FILE|LM_LICENSE_FILE|CDS_AUTO_64BIT|CDS_Netlisting_Mode|PATH|LD_LIBRARY_PATH)=' "$CDS_ENV_SRC")"

unset CDS_ENV_SRC
