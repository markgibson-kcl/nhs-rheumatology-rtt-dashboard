# ============================================================
# DOWNLOAD AND PROCESS NHS ENGLAND RTT DATA
#
# Specialty:
#   Rheumatology, Treatment Function 410
#
# Period:
#   April 2024 onwards
#
# Source:
#   NHS England monthly RTT "Incomplete Provider" datasets
# ============================================================

import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# NHS ENGLAND RTT ARCHIVE PAGES
# ============================================================

RTT_PAGES = [
    "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2024-25/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2025-26/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2026-27/",
]


# ============================================================
# CLEAN COLUMN NAMES
# ============================================================

def clean_column_name(name):
    name = str(name).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def clean_columns(df):
    df = df.copy()
    df.columns = [
        clean_column_name(col)
        for col in df.columns
    ]
    return df


# ============================================================
# SCRAPE "INCOMPLETE PROVIDER" LINKS
# ============================================================

def get_incomplete_provider_links(page_url):

    print(f"Scanning: {page_url}")

    response = requests.get(
        page_url,
        timeout=60
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    rows = []

    for a in soup.find_all("a", href=True):

        text = " ".join(a.stripped_strings)

        if re.search(
            r"Incomplete Provider",
            text,
            flags=re.IGNORECASE
        ):
            rows.append(
                {
                    "text": text,
                    "url": urljoin(
                        page_url,
                        a["href"]
                    ),
                }
            )

    return pd.DataFrame(rows)


# ============================================================
# PARSE MONTH
# ============================================================

def extract_month(text):

    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\d{2}",
        text
    )

    if match is None:
        return pd.NaT

    return pd.to_datetime(
        match.group(0),
        format="%b%y"
    )


# ============================================================
# READ ONE MONTH
# ============================================================

def read_rtt_month(url, month):

    print(
        f"Processing {month:%B %Y}"
    )

    if re.search(
        r"\.xls($|\?)",
        url,
        flags=re.IGNORECASE
    ):
        extension = ".xls"
    else:
        extension = ".xlsx"

    local_file = (
        RAW_DIR
        / f"RTT_{month:%Y_%m}{extension}"
    )

    if not local_file.exists():

        print(
            f"  Downloading {local_file.name}"
        )

        response = requests.get(
            url,
            timeout=120
        )
        response.raise_for_status()

        local_file.write_bytes(
            response.content
        )

    else:
        print(
            f"  Using cached {local_file.name}"
        )

    # Row 14 in the workbook is the header.
    # pandas uses zero-based indexing, hence header=13.
    dat = pd.read_excel(
        local_file,
        header=13
    )

    dat = clean_columns(dat)
    dat["month"] = month

    return dat


# ============================================================
# FIND IMPORTANT COLUMNS
# ============================================================

def find_column(data, patterns):

    for column in data.columns:

        for pattern in patterns:

            if re.search(
                pattern,
                column,
                flags=re.IGNORECASE
            ):
                return column

    return None


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():

    # --------------------------------------------------------
    # Scrape archive pages
    # --------------------------------------------------------

    provider_links = pd.concat(
        [
            get_incomplete_provider_links(page)
            for page in RTT_PAGES
        ],
        ignore_index=True
    )

    provider_links["month"] = (
        provider_links["text"]
        .apply(extract_month)
    )

    provider_links = (
        provider_links
        .loc[
            provider_links["month"]
            >= pd.Timestamp("2024-04-01")
        ]
        .dropna(
            subset=["month"]
        )
        .drop_duplicates(
            subset=["month"]
        )
        .sort_values("month")
        .reset_index(drop=True)
    )

    print()
    print("RTT months found:")
    print(
        provider_links[
            ["month", "text"]
        ].to_string(index=False)
    )
    print()

    # --------------------------------------------------------
    # Download/read all months
    # --------------------------------------------------------

    all_months = []

    for _, row in provider_links.iterrows():

        dat = read_rtt_month(
            url=row["url"],
            month=row["month"]
        )

        all_months.append(dat)

    rtt_raw = pd.concat(
        all_months,
        ignore_index=True
    )

    print()
    print(
        f"Raw RTT dataset: "
        f"{rtt_raw.shape[0]:,} rows x "
        f"{rtt_raw.shape[1]} columns"
    )

    # --------------------------------------------------------
    # Identify important columns
    # --------------------------------------------------------

    provider_code_col = find_column(
        rtt_raw,
        [
            r"provider.*code",
            r"organisation.*code",
        ]
    )

    provider_name_col = find_column(
        rtt_raw,
        [
            r"provider.*name",
            r"organisation.*name",
        ]
    )

    treatment_code_col = find_column(
        rtt_raw,
        [
            r"treatment.*function.*code",
        ]
    )

    print()
    print("Detected columns:")
    print(
        {
            "provider_code": provider_code_col,
            "provider_name": provider_name_col,
            "treatment_code": treatment_code_col,
        }
    )

    if any(
        x is None
        for x in [
            provider_code_col,
            provider_name_col,
            treatment_code_col,
        ]
    ):
        raise RuntimeError(
            "Could not identify one or more required columns."
        )

    # --------------------------------------------------------
    # Rheumatology only: Treatment Function 410
    # --------------------------------------------------------

    treatment_code = (
        rtt_raw[treatment_code_col]
        .astype(str)
        .str.replace(
            r"^C_",
            "",
            regex=True
        )
    )

    rheum = (
        rtt_raw
        .loc[
            treatment_code == "410"
        ]
        .copy()
    )

    rheum = rheum.rename(
        columns={
            provider_code_col: "provider_code",
            provider_name_col: "provider_name",
        }
    )

    # --------------------------------------------------------
    # Select and convert RTT outcome columns
    # --------------------------------------------------------

    output = pd.DataFrame(
        {
            "month":
                rheum["month"],

            "provider_code":
                rheum["provider_code"],

            "provider_name":
                rheum["provider_name"],

            "total_waiting":
                pd.to_numeric(
                    rheum[
                        "total_number_of_incomplete_pathways"
                    ],
                    errors="coerce"
                ),

            "within_18_weeks":
                pd.to_numeric(
                    rheum[
                        "total_within_18_weeks"
                    ],
                    errors="coerce"
                ),

            "pct_within_18_weeks":

    (

        pd.to_numeric(

            rheum["total_within_18_weeks"],

            errors="coerce"

        )

        /

        pd.to_numeric(

            rheum["total_number_of_incomplete_pathways"],

            errors="coerce"

        )

        * 100

    ),

            "median_wait_weeks":
                pd.to_numeric(
                    rheum[
                        "average_median_waiting_time_in_weeks"
                    ],
                    errors="coerce"
                ),

            "p92_wait_weeks":
    pd.to_numeric(
        rheum[
            find_column(
                rheum,
                [
                    r"92nd.*percentile.*waiting.*time.*weeks",
                    r"92.*percentile.*waiting.*time.*weeks",
                ]
            )
        ],
        errors="coerce"
    ),

            "over_52_weeks":
                pd.to_numeric(
                    rheum[
                        "total_52_plus_weeks"
                    ],
                    errors="coerce"
                ),

            "over_65_weeks":
                pd.to_numeric(
                    rheum[
                        "total_65_plus_weeks"
                    ],
                    errors="coerce"
                ),

            "over_78_weeks":
                pd.to_numeric(
                    rheum[
                        "total_78_plus_weeks"
                    ],
                    errors="coerce"
                ),
        }
    )

    output = (
        output
        .dropna(
            subset=["provider_code"]
        )
        .sort_values(
            ["month", "provider_name"]
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Calculate England benchmark and provider rankings
    # --------------------------------------------------------

    england_monthly = (
        output
        .groupby("month", as_index=False)
        .agg(
            england_total_waiting=("total_waiting", "sum"),
            england_within_18_weeks=("within_18_weeks", "sum"),
        )
    )

    # England percentage is pathway-weighted
    england_monthly["england_pct_within_18_weeks"] = (
        england_monthly["england_within_18_weeks"]
        / england_monthly["england_total_waiting"]
        * 100
    )

    # Add England benchmark to each provider-month
    output = output.merge(
        england_monthly[
            [
                "month",
                "england_pct_within_18_weeks"
            ]
        ],
        on="month",
        how="left"
    )

    # Difference from England in percentage points
    output["difference_vs_england"] = (
        output["pct_within_18_weeks"]
        - output["england_pct_within_18_weeks"]
    )

    # Rank providers within each month:
    # rank 1 = highest percentage within 18 weeks
    output["rank_within_18_weeks"] = (
        output
        .groupby("month")["pct_within_18_weeks"]
        .rank(
            ascending=False,
            method="min"
        )
    )

    # --------------------------------------------------------
    # Save processed files
    # --------------------------------------------------------

    parquet_file = (
        PROCESSED_DIR
        / "rtt_rheumatology.parquet"
    )

    csv_file = (
        PROCESSED_DIR
        / "rtt_rheumatology.csv"
    )

    output.to_parquet(
        parquet_file,
        index=False
    )

    output.to_csv(
        csv_file,
        index=False
    )

    print()
    print(
        f"Rheumatology dataset: "
        f"{output.shape[0]:,} rows"
    )

    print(
        f"Providers: "
        f"{output['provider_code'].nunique()}"
    )

    print(
        f"Months: "
        f"{output['month'].nunique()}"
    )

    print()
    print("Saved:")
    print(parquet_file)
    print(csv_file)

    print()
    print("Most recent rows:")
    print(
        output
        .tail(20)
        .to_string(index=False)
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()