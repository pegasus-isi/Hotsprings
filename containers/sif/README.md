# containers/sif/

`.sif` files land here when you run `../build_sif.sh` (Route A). The workflow
reads this directory when `SUBDUCTCR_USE_SIF=1` is set. Expected files:

    subductcr-mothur.sif
    subductcr-qc.sif
    subductcr-mifaser.sif
    subductcr-r.sif

These are large binaries and are not committed (see .gitignore).
