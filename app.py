from pathlib import Path
import json

import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# STREAMLIT PAGE
# ============================================================

st.set_page_config(
    page_title="NHS Rheumatology RTT",
    layout="wide"
)

st.title("NHS Rheumatology RTT Performance")


# ============================================================
# PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent

RTT_FILE = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "rtt_rheumatology.parquet"
)

CATCHMENT_FILE = (
    PROJECT_DIR
    / "data"
    / "geography"
    / "elective_trust_catchments_2024.geojson"
)


# ============================================================
# LOAD DATA
# ============================================================

with st.spinner("Loading RTT data..."):
    rtt = pd.read_parquet(RTT_FILE)

with st.spinner("Loading trust catchment map..."):
    catchments = gpd.read_file(CATCHMENT_FILE)


# ============================================================
# CONVERT GEOGRAPHY TO LONGITUDE / LATITUDE
# ============================================================

catchments = catchments.to_crs(
    epsg=4326
)


# ============================================================
# FILTER CONTROLS
# ============================================================

available_months = (
    rtt["month"]
    .dropna()
    .sort_values()
    .unique()
)

metric_options = {
   "% within 18 weeks": {

    "column": "pct_within_18_weeks",

    "label": "% within 18 weeks",

    "range": (0, 100),

    "format": ".1f",

    # Custom scale:

    # poor performance = red

    # approaching target = amber/yellow

    # 92%+ = green

    "color_scale": [

        [0.00, "#b2182b"],

        [0.60, "#ef8a62"],

        [0.80, "#fddbc7"],

        [0.90, "#fee08b"],

        [0.92, "#d9ef8b"],

        [1.00, "#1a9850"],

    ],

    "reverse_scale": False,

},

    "Waiting list size": {
        "column": "total_waiting",
        "label": "Waiting list",
        "range": None,
        "format": ",.0f",
        "color_scale": "RdYlGn",
        "reverse_scale": True,
    },

    "Median wait": {
        "column": "median_wait_weeks",
        "label": "Median wait (weeks)",
        "range": None,
        "format": ".1f",
        "color_scale": "RdYlGn",
        "reverse_scale": True,
    },

    "92nd percentile wait": {
        "column": "p92_wait_weeks",
        "label": "92nd percentile wait (weeks)",
        "range": None,
        "format": ".1f",
        "color_scale": "RdYlGn",
        "reverse_scale": True,
    },
}


col1, col2 = st.columns(2)

with col1:
    selected_month = st.selectbox(
        "Select RTT month",
        options=available_months,
        index=len(available_months) - 1,
        format_func=lambda x: pd.Timestamp(x).strftime("%B %Y"),
    )

with col2:
    selected_metric_name = st.selectbox(
        "Select metric",
        options=list(metric_options.keys()),
        index=0,
    )


selected_month = pd.Timestamp(selected_month)

selected_metric = metric_options[selected_metric_name]

metric_column = selected_metric["column"]
metric_label = selected_metric["label"]
metric_range = selected_metric["range"]
metric_format = selected_metric["format"]
metric_color_scale = selected_metric["color_scale"]
metric_reverse_scale = selected_metric["reverse_scale"]


selected = (
    rtt
    .loc[
        rtt["month"] == selected_month
    ]
    .copy()
)

st.caption(
    f"Showing {selected_metric_name.lower()} "
    f"for {selected_month:%B %Y}"
)

# ============================================================
# JOIN RTT TO TRUST CATCHMENTS
# ============================================================

map_data = catchments.merge(
    selected,
    on="provider_code",
    how="left",
    suffixes=("_geo", "_rtt")
)


# ============================================================
# PREPARE GEOJSON
# ============================================================

geojson_data = map_data[
    [
        "provider_code",
        "geometry"
    ]
].copy()

geojson = json.loads(
    geojson_data.to_json()
)

for feature in geojson["features"]:
    feature["id"] = feature["properties"]["provider_code"]


# ============================================================
# MAP
# ============================================================

fig = px.choropleth_map(
    map_data,
    geojson=geojson,
    locations="provider_code",
    featureidkey="id",

    color=metric_column,
    color_continuous_scale=metric_color_scale,

    hover_name="provider_name_rtt",

    hover_data={
        "provider_code": False,
        "pct_within_18_weeks":False,
        "total_waiting": False,
        "median_wait_weeks": False,
        "p92_wait_weeks": False,
    },

    map_style="carto-positron",

    center={
        "lat": 52.9,
        "lon": -1.5
    },

    zoom=5.35,
    opacity=0.75,

    range_color=metric_range,

    labels={
        "provider_code": "Trust code",
        "pct_within_18_weeks": "% within 18 weeks",
        "total_waiting": "Waiting list",
        "median_wait_weeks": "Median wait (weeks)",
        "p92_wait_weeks": "92nd percentile wait (weeks)",
    },
)

# ============================================================
# COLOUR SCALE / LEGEND
# ============================================================

if metric_column == "pct_within_18_weeks":

    fig.update_coloraxes(
        reversescale=False,
        colorbar=dict(
            title="% within<br>18 weeks",
            tickvals=[
                0,
                20,
                40,
                60,
                80,
                92,
                100,
            ],
            ticktext=[
                "0%",
                "20%",
                "40%",
                "60%",
                "80%",
                "92% target",
                "100%",
            ],
        ),
    )

else:

    fig.update_coloraxes(
        reversescale=metric_reverse_scale,
        colorbar=dict(
            title=metric_label
        ),
    )

# ============================================================
# MAP LAYOUT
# ============================================================

fig.update_layout(
    height=900,
    margin={
        "r": 0,
        "t": 0,
        "l": 0,
        "b": 0
    }
)


# ============================================================
# MAP + TRUST DETAIL PANEL
# ============================================================

detail_col, map_col = st.columns(
    [1, 2.2]
)

with map_col:

    event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="rtt_map",
    )


# ============================================================
# GET SELECTED TRUST
# ============================================================

selected_provider_code = None

if (
    event
    and event.selection
    and event.selection.points
):

    point = event.selection.points[0]

    selected_provider_code = point.get(
        "location"
    )


# ============================================================
# TRUST DETAIL PANEL
# ============================================================

with detail_col:

    st.subheader("Trust details")

    if selected_provider_code is None:

        st.info(
            "Select a trust on the map to view its "
            "rheumatology RTT performance."
        )

    else:

        trust_row = map_data.loc[
            map_data["provider_code"]
            == selected_provider_code
        ]

        if not trust_row.empty:

            trust_row = trust_row.iloc[0]

            if pd.notna(
                trust_row["provider_name_rtt"]
            ):
                trust_name = trust_row[
                    "provider_name_rtt"
                ]

            else:
                trust_name = trust_row[
                    "provider_name_geo"
                ]

            st.markdown(
                f"### {trust_name}"
            )

            st.caption(
                f"{selected_month:%B %Y}"
            )

            # --------------------------------------------
            # ACTIVE RTT WAITING LIST
            # --------------------------------------------

            if (
                pd.notna(
                    trust_row["total_waiting"]
                )
                and trust_row["total_waiting"] > 0
            ):

                st.metric(
                    "Within 18 weeks",
                    (
                        f"{trust_row['pct_within_18_weeks']:.1f}%"
                    )
                )

                st.metric(
                    "Waiting list",
                    (
                        f"{trust_row['total_waiting']:,.0f}"
                    )
                )

                st.metric(
                    "Median wait",
                    (
                        f"{trust_row['median_wait_weeks']:.1f} weeks"
                    )
                )

                st.metric(
                    "92nd percentile wait",
                    (
                        f"{trust_row['p92_wait_weeks']:.1f} weeks"
                    )
                )

            # --------------------------------------------
            # ZERO RTT PATHWAYS
            # --------------------------------------------

            elif (
                pd.notna(
                    trust_row["total_waiting"]
                )
                and trust_row["total_waiting"] == 0
            ):

                st.info(
                    "No incomplete rheumatology RTT "
                    "pathways reported for this month."
                )

            # --------------------------------------------
            # NO RTT DATA
            # --------------------------------------------

            else:

                st.warning(
                    "Rheumatology RTT data unavailable "
                    "for this month."
                )