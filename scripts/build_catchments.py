from pathlib import Path
import pandas as pd

# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parents[1]
GEO_DIR = PROJECT_DIR / "data" / "geography"

OHID_FILE = (
    GEO_DIR
    / "nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods"
)

# ============================================================
# BUILD ELECTIVE TRUST CATCHMENT LOOKUP
# ============================================================

elective = pd.read_excel(
    OHID_FILE,
    sheet_name="Elective",
    engine="calamine",
    header=2
)

print(f"Raw elective rows: {len(elective):,}")

# Rename the columns we need
elective = elective.rename(
    columns={
        "Catchment \nyear": "catchment_year",
        "Trust \ncode": "provider_code",
        "Trust \nname": "provider_name",
        "MSOA21CD": "MSOA21CD",
        "First past \nthe post (FPTP)": "fptp",
    }
)

print()
print("Years:")
print(
    elective["catchment_year"]
    .value_counts(dropna=False)
    .sort_index()
)

# Keep the latest catchment year and only the
# first-past-the-post trust for each MSOA
catchments = (
    elective
    .loc[
        (elective["catchment_year"] == 2024)
        & (elective["fptp"] == True)
    ]
    [
        [
            "MSOA21CD",
            "provider_code",
            "provider_name",
        ]
    ]
    .drop_duplicates()
    .reset_index(drop=True)
)

print()
print(f"2024 FPTP MSOAs: {len(catchments):,}")
print(
    f"Acute trusts represented: "
    f"{catchments['provider_code'].nunique()}"
)

print()
print("Example:")
print(
    catchments
    .head(20)
    .to_string(index=False)
)

# Check that every MSOA maps to only one trust
duplicates = (
    catchments
    .groupby("MSOA21CD")
    ["provider_code"]
    .nunique()
)

print()
print(
    "MSOAs assigned to >1 trust:",
    (duplicates > 1).sum()
)

# Save lookup
catchment_file = (
    GEO_DIR
    / "elective_trust_catchments_2024.csv"
)

catchments.to_csv(
    catchment_file,
    index=False
)

print()
print(f"Saved: {catchment_file}")

# ============================================================
# LOAD MSOA 2021 BOUNDARIES
# ============================================================

import geopandas as gpd

MSOA_FILE = (
    GEO_DIR
    / "Middle_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V3_-6053051880466881041.geojson"
)

print()
print("Loading MSOA boundaries...")

msoa = gpd.read_file(MSOA_FILE)

print(f"MSOA polygons loaded: {len(msoa):,}")
print(f"CRS: {msoa.crs}")

print()
print("Boundary columns:")
print(msoa.columns.tolist())


# ============================================================
# CHECK MSOA CODE COLUMN
# ============================================================

if "MSOA21CD" not in msoa.columns:
    raise RuntimeError(
        "Could not find MSOA21CD in the boundary file."
    )


# ============================================================
# JOIN OHID CATCHMENTS TO MSOA POLYGONS
# ============================================================

catchment_msoa = msoa.merge(
    catchments,
    on="MSOA21CD",
    how="inner"
)

print()
print(
    f"MSOA polygons matched to OHID catchments: "
    f"{len(catchment_msoa):,}"
)

unmatched = set(catchments["MSOA21CD"]) - set(msoa["MSOA21CD"])

print(
    f"OHID MSOAs without a boundary match: "
    f"{len(unmatched):,}"
)


# ============================================================
# DISSOLVE MSOAs INTO TRUST CATCHMENTS
# ============================================================

print()
print("Dissolving MSOAs into trust catchments...")

trust_catchments = (
    catchment_msoa
    .dissolve(
        by=[
            "provider_code",
            "provider_name"
        ],
        as_index=False
    )
)

print(
    f"Trust catchment polygons created: "
    f"{len(trust_catchments):,}"
)


# ============================================================
# SAVE TRUST CATCHMENTS
# ============================================================

catchment_geojson = (
    GEO_DIR
    / "elective_trust_catchments_2024.geojson"
)

trust_catchments.to_file(
    catchment_geojson,
    driver="GeoJSON"
)

print()
print(f"Saved: {catchment_geojson}")