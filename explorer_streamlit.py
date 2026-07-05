"""
Jiatong Wang | SAPIENZA BA THESIS DATABASE GUI
--------------------------------------------------------------------
Purpose: This GUI allows anyone to browse my BA thesis database (a relational database in SQLite about memory sanctions against Maximinus Thrax) .
         It offers an interactive map and intuitive searches & filters.
         It also offers the option to download search results as a csv file, or export advanced search settings as an sql query 
         (The WHERE clause is dynamically generated based on user input. I have provided a default SELECT statement.
         Of course the user may customize the SELECT statment based on their needs after downloading the query)

NOTES
--------------------------------------------------------------------

DEVELOPMENT HISTORY:
--------------------------------------------------------------------
Originally, I only made an SQL query list. Later, I decided to make this GUI.
To save time, this GUI reuses queries from the original query list, in a modified form.

The results window therefore displays the printed output of an SQL query, 
stitched together as plain text. All sql queries can be found in backend_logic 
under either main_report_sql or under their respective functions. 

HIDDEN DATA:
--------------------------------------------------------------------
The 'location_data_source' field, which explains the 
source of each coordinate, is only available in the database 
itself within the 'places' table.

The tables handling the imperial titulatures of Maximinus Thrax and 
his son are currently invisible to the GUI since the data they record
is very granular and I don't think it's humane to make anyone go throug
a dropdown menu of the 100ish different individual words attested inside 
the imperial titulatures.

If anyone wish to, they can be queried in the db. A query list is provided
in my thesis as an appendix and will be repo'd here soon.

PORTABILITY:
--------------------------------------------------------------------
To Future Me: This script is just the streamlit interface
This file itself is somewhat reusable for a different project as long as backend_logic.py and the schema of version_58.py stays the same.


HOWEVER the parts of the interface (Advanced Search, Search Results List View, and Map Viewer) which contain logic flagging inscriptions according
to whether they are relevant to Maximinus Thrax or whether the erasure they suffered are relevant to Maximinus Thrax need to change.

BECAUSE the logic that determines whether an erasure is relevant to Maximinus Thrax (this is hardcoded to exclude any inscription
linked to the person_id 50,i.e. Licinnius Serenianus's monuments which are erased due to a separate memory sanction against him;on the
inscriptions of Licinnius Serenianus which we have, the name of Maximinus Thrax and his name are never erased. Other than the milestones
of Licinnius Serenianus, we do not have other inscriptions relevant to Maximinus Thrax which suffered an erasure as the result of a 
different memory sanction campaign therefore for this corpus. Therefore, in this corpus, excluding all monuments linked to the person_id
person_id 50 from being counted as a relevant erasure can safely exclude ALL erasures ON monuments relevevant to Maximinus Thrax
BUT ARE NOT actually part of the memory sanction campaign against him)

SOME OF THE FUNCTIONS IN backend_logic.py also relies on this particularity of THIS corpus. Please check those too.

FURTHERMORE

PLEASE CHECK backend_logic.py for the following items which are hardcoded

HARDCODED STUFF IN BACKEND_LOGIC.PY
--------------------------------------------------------------------
In the constant main_report_sql in backend_logic.py, the text output for each method_id and extent_id are hardcoded, instead of being dynamically fetched from a field in the database. 
IF you reuse this, make sure to change/check the following section.


 Sec2_Intervention_Nested_Details AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, 
                   '* _intervention ' || COALESCE(i.intervention_index, 1) || ' :_ ' || 
                   CASE 
                       WHEN iam.method_id = 2 THEN COALESCE(e.extent_description, '') || ' ' || COALESCE(m.method_description, '') || ' of inscription, ' || COALESCE(m.method_description, '') || ' targeting ' || (SELECT GROUP_CONCAT(t.target_description, ', ') FROM "interventions_and_targets" iat JOIN "targets" t ON iat.target_id = t.target_id WHERE iat.intervention_id = i.intervention_id) 
                       WHEN iam.method_id = 3 THEN 'reuse of monument' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END 
                       WHEN iam.method_id = 4 THEN 'monument damage' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END 
                       WHEN iam.method_id = 5 THEN 'restoration of erased text' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END 
                       WHEN iam.method_id = 6 THEN 'reuse as support for new inscription' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END 
                       ELSE 'unknown intervention method (' || COALESCE(iam.method_id, 'N/A') || ')' 
                   END || char(10) AS tl 
                   
FURHTERMORE, AS AFORMENTIONED, CHECK ALL LOGIC THAT RELIES ON FILTERING BY PERSON_ID = 50 or PERSON_ID != 50

====================================================================

====================================================================
"""


import sqlite3
import os
import textwrap
import streamlit as st
import folium
import json
import re
import csv
import io
from branca.element import Element
import itertools
import time
import sys


streamlit_cloud_path = "/mount/src/maximinus_thrax_database_explorer_streamlit_v2"

if streamlit_cloud_path not in sys.path:
    sys.path.insert(0, streamlit_cloud_path)

from backend_logic import *


# ----------------------------------------------------------------------------------------------------------------------------
# UI FRONTEND



st.set_page_config(page_title="Maximinus Thrax Database Browser", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
db_path = os.path.join(BASE_DIR, "version_58.db")

optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
provinces_json_path = os.path.join(BASE_DIR, "roman_provinces.json") 


# INITIALISE SESSION STATES
if "inputs_are_dirty" not in st.session_state:
    st.session_state["inputs_are_dirty"] = False
if "active_search_has_run" not in st.session_state:
    st.session_state["active_search_has_run"] = False
if "active_search_where_clauses" not in st.session_state:
    st.session_state["active_search_where_clauses"] = []
if "active_search_query_params" not in st.session_state:
    st.session_state["active_search_query_params"] = {}
if "skip_scroll" not in st.session_state:
    st.session_state["skip_scroll"] = False
if "reset_selectbox" not in st.session_state:
    st.session_state["reset_selectbox"] = False



if 'active_inscription_ids' not in st.session_state:
    st.session_state.active_inscription_ids = []
if 'search_results' not in st.session_state:
    st.session_state.search_results = ""
if 'person_matches' not in st.session_state:
    st.session_state.person_matches = []
if 'trigger_map_html' not in st.session_state:
    st.session_state.trigger_map_html = None


# LINK SETUPS
query_params = st.query_params

should_scroll = any(k in query_params for k in ["ins_id", "person_id", "collective_id", "obj_id"])

# 1. Inscription hyperlink SETUP
if "ins_id" in query_params:
    url_id = query_params["ins_id"]
    if url_id.isdigit():
        st.session_state["active_search_has_run"] = True
        st.session_state["inputs_are_dirty"] = False
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_where_clauses"] = []
        st.session_state["active_search_query_params"] = {}
        st.session_state.active_inscription_ids = [int(url_id)]
        
        st.query_params.clear() 
        fetch_metadata_by_id(url_id)
        
# 2. Person hyperlink SETUP
elif "person_id" in query_params:
    url_per_id = query_params["person_id"]
    if url_per_id.isdigit():
        st.session_state["active_search_has_run"] = True
        st.session_state["inputs_are_dirty"] = False
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_where_clauses"] = []
        st.session_state["active_search_query_params"] = {}
        
        st.query_params.clear() 
        generate_person_report(url_per_id)
        
# 3. Institutions/Groups/Military Units hyperlink SETUP
elif "collective_id" in query_params:
    selected_collective_id = query_params["collective_id"]
    st.session_state["active_search_has_run"] = True
    st.session_state["inputs_are_dirty"] = False
    st.session_state["csv_mode"] = "ids"
    st.session_state["active_search_where_clauses"] = []
    st.session_state["active_search_query_params"] = {}
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT collective_name FROM collectives WHERE collective_id = ?;", (selected_collective_id,))
        coll_name_row = cursor.fetchone()
        collective_title = coll_name_row[0] if coll_name_row else f"ID {selected_collective_id}"
        
        cursor.execute("SELECT inscription_id FROM inscriptions_and_collectives WHERE collective_id = ?;", (selected_collective_id,))
        matched_ids = [row[0] for row in cursor.fetchall()]
        st.session_state.active_inscription_ids = matched_ids
        
        if matched_ids:
            st.session_state.search_results = f"#### Filtered by Institution/Group: **{collective_title}**\nFound {len(matched_ids)} matching inscriptions."
        else:
            st.session_state.search_results = f"No inscriptions found linked to group: **{collective_title}**."
        conn.close()
        st.query_params.clear()
    except Exception as e:
        st.error(f"Error querying collective group filter: {e}")

# Object ID hyperlink SETUP
elif "obj_id" in query_params:
    selected_obj_id = query_params["obj_id"]
    
    st.session_state["active_search_has_run"] = True
    st.session_state["inputs_are_dirty"] = False
    st.session_state["csv_mode"] = "ids"
    st.session_state["active_search_where_clauses"] = []
    st.session_state["active_search_query_params"] = {}
    
    fetch_metadata_by_object_id(selected_obj_id)
    st.query_params.clear()

# STOP PEOPLE FROM TRYING TO GENERATE MAP OR EXPORT TO CSV WITHOUT ACTUALLY CLICKING SEARCH AND GETTING MAD ABOUT HAVING THE WRONG RESULTS

tracked_fields = {
    "main_text_input": "last_searched_text",
    "edcs_report_input": "last_searched_edcs",
    "id_report_input": "last_searched_id",
    "person_lookup_input": "last_searched_lookup",
    "person_select_input": "last_searched_person",
    "person_report_input": "last_searched_person"
}

any_input_has_unsearched_changes = False

# Only check for keystroke dirtiness if the app didn't JUST execute a successful search button click
if not st.session_state.get("active_search_has_run", False) or st.session_state.get("inputs_are_dirty", False):
    for widget_key, anchor_key in tracked_fields.items():
        if widget_key in st.session_state:
            current_value = str(st.session_state[widget_key]).strip()
            last_executed_value = str(st.session_state.get(anchor_key, "")).strip()
            
            # Normalize dropdown placeholders
            if current_value == "PLEASE SELECT": current_value = ""
            if last_executed_value == "PLEASE SELECT": last_executed_value = ""
                
            if current_value != last_executed_value:
                any_input_has_unsearched_changes = True
            
            # Keystroke trigger tracker
            if widget_key != "person_select_input":
                prior_rerun_key = f"prior_{widget_key}"
                prior_value = str(st.session_state.get(prior_rerun_key, "")).strip()
                if prior_value == "PLEASE SELECT": prior_value = ""
                    
                if current_value != prior_value:
                    st.session_state["person_select_input"] = "PLEASE SELECT"
                
                st.session_state[prior_rerun_key] = current_value

    st.session_state["inputs_are_dirty"] = any_input_has_unsearched_changes


# CUSTOMIZE FONT SIZE IN ACCORDION HEADERS    

# ALL accordion headers get 20px, except the welcome text which stays at 14px

st.markdown(
    """
    <style>
    /* 1. Global rule: Make ALL expander headers large (20px) */
    div[data-testid="stExpander"] details summary p {
        font-size: 20px !important;
        font-weight: 600 !important;
    }
    
    /* 2. Exception rule: Target the specific expander inside your key container */
    [class*="st-key-welcome_instructions_expander"] div[data-testid="stExpander"] details summary p,
    .st-key-welcome_instructions_expander details summary p {
        font-size: 14px !important;
        font-weight: 400 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# SLIM DOWN SITE HEADER

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem; /* Default is usually around 6rem */
        }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    "<h2 style='margin-top: 0rem; margin-bottom: 0rem;'>Maximinus Thrax Database Βrowser</h2>", 
    unsafe_allow_html=True
)

# Welcome Text & Instructions
with st.expander("Click to View Site Instructions / Welcome Text", expanded=False, key="welcome_instructions_expander"):
    st.markdown("""
## How to Use | DEVELOPMENT NOTE: THIS INSTRUCTION MANUAL REFLECTS AN EARLIER VERSION OF THE INTERFACE; I AM GOING TO REWRITE THE MANUAL. PLEASE USE YOUR INTUITION FOR NOW

### Keyword Search
* Enter a keyword or phrase in the top bar and press the **Search Button** (note: pressing Enter alone does not work). 
* A report will be generated for every matching inscription containing relevant metadata.
* It records interventions to each inscription, as well as the target, extent, and method of each intervention.
* Every individual mentioned in an inscription is hyperlinked to their internal database record. Click on the link to explore!
* Legal reasons aside, since this entire database is smaller than one hi-res photograph, we do not host photos. Instead, almost every inscription is linked to an **EDCS** record which provides a photo when available.
* For more information on the ancient place where an inscription was discovered, click the hyperlink to **Pleiades**, the ancient world gazetteer.
* Over 80 percent of inscriptions in this corpus are milestones. For more information on the road segment a milestone belonged to, click the hyperlinked road segment to see its page on the **itiner-e project**.
* Due to the nature of the corpus, all Dates are in CE / AD / d.C. 
* Likewise, currently no separate field explaining the reason for the dating of an inscription exists due to the nature of the corpus. Every relevant inscrption is dated by internal evidence to a period during the reign of Maximinus Thrax.

### Person Reports
* This database tracks the attested office, group affiliation (e.g., specific military units, priestly colleges, etc.), and social status designation (specifically *rangtitels* and titles like *consularis*) of every individual appearing within the corpus, alongside the specific inscriptions where this information is attested. 
* Generate a detailed prosopography report by copying a person's ID into the corresponding field and pressing **Enter**. You can also search for a person's ID using the **Person Name** field.

### EDCS Number
* Have an EDCS record in mind? You can generate an inscription report using that as well, provided the inscription is in our database.
* Insert the EDCS record number formatted as `EDCS-12345678` and click **Generate Report**.

### Inscription ID
* Browsing the map and want to learn more about a specific inscription without scrolling to it in the search results? Type its ID here and click **Generate Report!**
* > **NOTE:** This will clear your original search results. Consider opening a new window for this if you are using complex filters.
    
### Lookup Person ID by Name
* Want to search for a specific individual without using the main search bar? Insert the person's name, click the **Person Name** button, and look at the **Select Person** field to the right.
* **Select the desired individual** before clicking the **Generate Report** button.
  > **NOTE:** Please manually select an individual before generating a report. The default individual at the top of the selection bar is not guaranteed to be the person you have in mind. 
    
### Interactive Map
* Loading the map may take a second due to the size of the itiner-e roads layer.
  > **NOTE:** You must manually press the **Generate Map** button *every time* after a search or after generating a person/inscription report to display the relevant inscriptions on the map.
* Click any dot on the map to view its details.
* In all applicable cases, the **EDCS** record and the **Pleiades** record (for the findspot area) are hyperlinked.
* **For milestone inscriptions:** The details popup notes that the inscription is on a milestone, names the road segment it served, and links to that segment on the **itiner-e project.** 
    * *Note on itiner-e:* If it shows a welcome screen, click *Explore Roman Roads* to continue to the linked segment, then click *Details* on the left for more information.
* **For non-milestone inscriptions:** The *titulorum distributio* (type of inscription) and type of support are displayed in the details popup instead of road information.
* **For multiple inscriptions on a single object:** The popup displays the total number of inscriptions on the support and the sequence ID of your selected inscription. A sequence ID of `1` means it was the earliest inscription on the object, `2` means it was the second, etc.
  * You can see all the inscriptions on the same object in chronological order if you click on the hyperlinked inscription ID. This will open a report in a new window. 

### Advanced Search
With advanced search, you can look for multiple words by connecting them with Boolean logic operators (which must be written in **UPPERCASE**):

* **AND** (e.g., `Maximinus AND legatus` to find entries containing both terms)
* **OR** (e.g., `cohors OR legio` to find entries containing either term)
* **NOT** (e.g., `Maximinus NOT Maximus` to exclude specific textual entries)

#### Available Filters:
The advanced search suite offers the following filters: 
* Relevance?, Material, Support, Context, Number of Inscriptions on Object, Province, Status Designation, Office/Military Role, Distributio Virorum, Distributio Titulorum, Intervention?, Method of Intervention, Extent of Intervention, Target of Intervention, and Organization/Military Unit.

> **Note on the "Relevance?" field:** Some physical objects bear both an inscription created during the reign of Maximinus Thrax and an earlier or later inscription. For all inscriptions explicitly mentioning Maximinus Thrax, Gaius Iulius Verus Maximus, or a military unit bearing the honorary epithet *Maximiniana*, the relevance field resolves to `true`.
""")

# MAIN SEARCH AND PERSON AND INSCRIPTION REPORTS

st.markdown("### Key Word or Phrase Search")
col_text1, col_text2 = st.columns([3, 1])

# Run an immediate evaluation pass at render time to catch text adjustments
if "main_text_input" in st.session_state:
    if st.session_state["main_text_input"].strip() != st.session_state.get("last_searched_text", ""):
        st.session_state["inputs_are_dirty"] = True

with col_text1:    
    text_input_var = st.text_input(
        "Enter search text:", 
        placeholder="e.g., Quintus Decius",
        key="main_text_input",
        label_visibility="collapsed",
        on_change=reset_map_and_search_flags
    )

with col_text2:
    if st.button("Search Text", key="btn_execute_text", use_container_width=True, type="primary"):
        st.session_state["last_searched_text"] = text_input_var.strip()
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_has_run"] = True
        st.session_state["trigger_map_html"] = None
        st.session_state["inputs_are_dirty"] = False
        st.session_state["skip_scroll"] = False
        run_standard_search(text_input_var)
        st.rerun()
        
# Full Reports Panel Layout Execution Shell
st.markdown("### Search by Inscription or Person")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

# Render pass validation checks to flip the trap flag if text keys don't match anchors
if "edcs_report_input" in st.session_state and st.session_state["edcs_report_input"].strip() != st.session_state.get("last_searched_edcs", ""):
    st.session_state["inputs_are_dirty"] = True
if "id_report_input" in st.session_state and st.session_state["id_report_input"].strip() != st.session_state.get("last_searched_id", ""):
    st.session_state["inputs_are_dirty"] = True
if "person_lookup_input" in st.session_state and st.session_state["person_lookup_input"].strip() != st.session_state.get("last_searched_lookup", ""):
    st.session_state["inputs_are_dirty"] = True

with col_s1:
    ref_input_var = st.text_input(
        "EDCS number:", 
        placeholder="e.g. EDCS-12345678", 
        key="edcs_report_input", 
        on_change=reset_map_and_search_flags
    )
    if st.button("Generate Inscription Report (EDCS)", use_container_width=True, type="primary"):
        if ref_input_var.strip():
            st.session_state["last_searched_edcs"] = ref_input_var.strip()
            st.session_state["csv_mode"] = "ids"
            st.session_state["active_search_has_run"] = True
            st.session_state["trigger_map_html"] = None
            st.session_state["inputs_are_dirty"] = False
            st.session_state["skip_scroll"] = False
            run_ref_search(ref_input_var)
            st.rerun()

with col_s2:
    id_input_var = st.text_input(
        "Inscription ID:", 
        placeholder="e.g. 24", 
        key="id_report_input",
        on_change=reset_map_and_search_flags
    )
    if st.button("Generate Inscription Report (ID)", use_container_width=True, type="primary"):
        if id_input_var.strip():
            st.session_state["last_searched_id"] = id_input_var.strip()
            st.session_state["csv_mode"] = "ids"
            st.session_state["active_search_has_run"] = True
            st.session_state["trigger_map_html"] = None
            st.session_state["inputs_are_dirty"] = False
            st.session_state.active_inscription_ids = [int(id_input_var.strip())]
            fetch_metadata_by_id(id_input_var)
            st.rerun()

with col_s3:
    pname_input_var = st.text_input(
        "Lookup Person ID by Name:", 
        placeholder="e.g. Maximinus", 
        key="person_lookup_input",
        on_change=reset_map_and_search_flags
    )
    if st.button("Find Person", use_container_width=True):
        if pname_input_var.strip():
            st.session_state["last_searched_lookup"] = pname_input_var.strip()
            lookup_person_options(pname_input_var)
            # 🚀 Turn on the message marker when they click Find Person
            if "person_matches" in st.session_state and st.session_state.person_matches:
                st.session_state["show_lookup_hint"] = True
            st.rerun()

    # 🚀 Show the message ONLY if names were found and it hasn't been turned off yet
    if st.session_state.get("show_lookup_hint") and st.session_state.get("person_matches"):
        st.info("Please select a person from the dropdown menu in 'Select Person', then click Generate Person Report.")
                 
with col_s4:
    if st.session_state.get("person_matches"):
        # Prepend the default "PLEASE SELECT" option to the front of the list
        options_list = ["PLEASE SELECT"] + [f"{row[1]} (ID: {row[0]})" for row in st.session_state.person_matches]
        
        selected_option = st.selectbox(
            "Select Person:", 
            options_list, 
            key="person_select_input",
            on_change=reset_map_and_search_flags
        )
        
        if st.button("Generate Person Report", key="btn_person_select_submit", use_container_width=True, type="primary"):
            if selected_option == "PLEASE SELECT":
                st.error("Please pick a person from the dropdown menu before generating a report!")
            else:
                st.session_state["show_lookup_hint"] = False
                st.session_state["skip_scroll"] = False
                st.session_state["last_searched_person"] = selected_option
                st.session_state["csv_mode"] = "ids"
                st.session_state["active_search_has_run"] = True
                st.session_state["inputs_are_dirty"] = False
                extracted_id = selected_option.split("(ID: ")[-1].replace(")", "").strip()
                generate_person_report(extracted_id)
                st.rerun()
    else:
        pid_input_var = st.text_input(
            "Person Selector / Search by Person ID:", 
            placeholder="Select from dropdown menu/Search by ID", 
            key="person_report_input",
            on_change=reset_map_and_search_flags
        )
        
        if st.button("Generate Person Report", key="btn_person_text_submit", use_container_width=True, type="primary"):
            if pid_input_var.strip():
                st.session_state["last_searched_person"] = pid_input_var.strip()
                st.session_state["active_search_has_run"] = True
                st.session_state["inputs_are_dirty"] = False
                generate_person_report(pid_input_var.strip())
                st.rerun()
                     
# ADVANCED SEARCH

with st.expander("Advanced Search", expanded=False):
    st.markdown("### Advanced Search")

    f_text = st.text_input(
        "Advanced Text Search (Boolean Logic Operators Allowed):", 
        placeholder="e.g. Maximinus AND legatus",
        on_change=reset_map_and_search_flags
    )
    
    st.caption(
        "Supported logic operators", 
        help=(
            "**Supported Operators:**\n"
            "You can use **AND**, **OR**, and **NOT** in your queries; Other boolean operators are not supported by SQL \n"
        )
    )
    
    text_search_mode = st.radio(
        "Text Search Strategy:",
        options=[
            "Match any inflected form of word or phrase", 
            "Match exact word or phrase"
        ],
        index=0,
        on_change=reset_map_and_search_flags
    )

    st.markdown("---")
    st.markdown("### Filters")
    st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)

    # COLUMN 1: Inscription Metadata
    with col1:
        st.markdown("#### Based on Inscription Metadata")
        
        relevance_options = [
            "Relevant",
            "All inscriptions regardless of relevance",
            "Not Relevant"
        ]
        f_rel = st.selectbox("Inscription Relevance to Maximinus Thrax:", relevance_options, on_change=reset_map_and_search_flags)
        f_prov = st.multiselect("Province:", [opt for opt in get_filter_options("provinces", "province_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_dist_tit = st.multiselect("Distributio Titulorum | Type of Inscription:", [opt for opt in get_filter_options("distributio_titulorum", "distributio_titulorum") if opt != "All"], on_change=reset_map_and_search_flags)
        f_sup_name = st.multiselect("Support Type:", [opt for opt in get_filter_options("support", "support_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_in_con = st.multiselect("Context Type:", [opt for opt in get_filter_options("context_types", "context_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_obj_mat = st.multiselect("Material:", [opt for opt in get_filter_options("materials", "material_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_status_tituli = st.multiselect("Status Tituli | Preservation Status:", [opt for opt in get_filter_options("status_tituli", "status_tituli_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_num_ins = st.multiselect("Number of Inscriptions on Object:", [opt for opt in get_filter_options("objects", "number_of_inscriptions") if opt != "All"], on_change=reset_map_and_search_flags)
        st.markdown("<div style='padding-top: 5px;'></div>", unsafe_allow_html=True)
        st.markdown("##### Chronological Range (CE)")
        date_col1, date_col2 = st.columns(2)
        with date_col1:
            f_start_date = st.number_input("Start Year:", value=None, step=1, placeholder="e.g. 235", on_change=reset_map_and_search_flags)
        with date_col2:
            f_end_date = st.number_input("End Year:", value=None, step=1, placeholder="e.g. 238", on_change=reset_map_and_search_flags)
        f_dating_strategy = st.radio(
            "Search Strategy:",
            options=["overlap", "strict"],
            format_func=lambda x: (
                "A: Search for all inscriptions whose date overlaps with this range" if x == "overlap"
                else "B: Search for only inscriptions whose date is fully contained within this range"
            ),
            help=(
                "• A: Returns all inscriptions dated to a time period that overlaps with your search window. "
                "For example, if you search 236–237 CE, inscriptions dated to 236 CE or 237CE or 236-237CE will appear, "
                "and so will inscriptions dated to 235–238 CE.\n\n"
                "• B: Returns only inscriptions dated to a time period that falls completely inside your search window. "
                "For example, if you search 236–236 CE, an inscription dated exactly to 236 CE will appear, "
                "but an inscription dated to 235–238 CE will be excluded."
            ),
            on_change=reset_map_and_search_flags
        )
        
    # COLUMN 2: People and Institutions
    with col2:
        st.markdown("#### Based on People and Institutions")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT person_id, person_name FROM persons ORDER BY person_name ASC;")
            db_persons = cursor.fetchall()
            conn.close()
            person_options = {row[0]: row[1] for row in db_persons}
        except Exception:
            person_options = {}
        f_vir_dist = st.multiselect("Distributio Virorum | Type of People Mentioned:", [opt for opt in get_filter_options("virorum_distributio", "virorum_distributio") if opt != "All"], on_change=reset_map_and_search_flags)
        f_unit = st.multiselect("Institution/Group/Military Unit:", [opt for opt in get_filter_options("collectives", "collective_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_unit_operator = st.radio("Match selected units using:", options=["OR (Any of these units)", "AND (All of these units)"], horizontal=True, index=0, label_visibility="collapsed", key="rad_collective_op", on_change=reset_map_and_search_flags)
        
        f_person_id = st.multiselect("Person:", options=list(person_options.keys()), format_func=lambda x: person_options[x], on_change=reset_map_and_search_flags)
        f_person_operator = st.radio("Match selected people using:", options=["OR (Any of these people)", "AND (All of these people)"], horizontal=True, index=0, label_visibility="collapsed", key="rad_person_op", on_change=reset_map_and_search_flags)
        
        f_status = st.multiselect("Attested Status Title", [opt for opt in get_filter_options("status_designations", "status_designation") if opt != "All"], on_change=reset_map_and_search_flags)
        f_pos = st.multiselect("Attested Office/Military Role:", [opt for opt in get_filter_options("positions", "position_description") if opt != "All"], on_change=reset_map_and_search_flags)

    # COLUMN 3: Later Modifications / Reuse
    with col3:
        st.markdown("#### Based on Later Modifications / Reuse")
        
        intervention_options = [
            "All inscriptions regardless of presence of later intervention",
            "Intervention present",
            "No later intervention"
        ]
        
        # 1. Grab status selection first so we can use it to determine the disabled state
        f_inter_status = st.selectbox("Intervention Status:", intervention_options, on_change=reset_map_and_search_flags)
        
        # 2. Only unlock the scope toggle if "Intervention present" is explicitly active
        is_scope_disabled = (f_inter_status != "Intervention present")
        
        f_intervention_scope_raw = st.radio(
            "Intervention Relevance to Maximinus Thrax",
            options=[
                "Interventions Relevant to Maximinus Thrax", 
                "All Interventions"
            ],
            index=0,
            disabled=is_scope_disabled,
            help="This setting only applies when 'Intervention present' is selected." if is_scope_disabled else None
        )
        
        # 3. Clean up the payload value: if disabled, force it to None or default state so it doesn't filter the data
        intervention_scope = None if is_scope_disabled else f_intervention_scope_raw

        f_interv_meth = st.multiselect("Method of Intervention:", [opt for opt in get_filter_options("methods", "method_description") if opt != "All"], on_change=reset_map_and_search_flags)
        f_interv_ext = st.multiselect("Extent of Intervention:", [opt for opt in get_filter_options("extent", "extent_description") if opt != "All"], on_change=reset_map_and_search_flags)
        f_interv_tgt = st.multiselect("Target of Intervention:", [opt for opt in get_filter_options("targets", "target_description") if opt != "All"], on_change=reset_map_and_search_flags)
    
    st.write("---")
    
    col_btn1, col_btn2 = st.columns([1, 1])

    with col_btn1:
        if st.button("Execute Advanced Search", key="btn_advanced_filter_search", use_container_width=True, type="primary"):
            st.session_state["csv_mode"] = "advanced"
            st.session_state["active_inscription_ids"] = []
            st.session_state["skip_scroll"] = False
            st.session_state["trigger_map_html"] = None  # Instantly wipe previous global map
            
            form_payload = {
                'text': f_text,
                'relevance_index': (
                    "All" if f_rel == "All inscriptions regardless of relevance" 
                    else 1 if f_rel == "Relevant" 
                    else 0
                ),
                'relevance_active': False if f_rel == "All inscriptions regardless of relevance" else True,
                'distributio_titulorum': f_dist_tit,
                'material_name': f_obj_mat,
                'support_name': f_sup_name,
                'context_name': f_in_con,
                'province_name': f_prov,
                'number_of_inscriptions': f_num_ins,
                'person_id': f_person_id,
                'person_operator': "AND" if "AND" in f_person_operator else "OR",
                'collective_name': f_unit,
                'collective_operator': "AND" if "AND" in f_unit_operator else "OR",
                'virorum_distributio': f_vir_dist,
                'status_designation': f_status,
                'position_description': f_pos,
                'intervention_status': (
                    "All" if f_inter_status == "All inscriptions regardless of presence of later intervention"
                    else 1 if f_inter_status == "Intervention present"
                    else 0
                ),
                'intervention_status_active': False if f_inter_status == "All inscriptions regardless of presence of later intervention" else True,
                'intervention_toggle': intervention_scope,
                'method_description': f_interv_meth,
                'extent_description': f_interv_ext, 
                'target_description': f_interv_tgt,
                'status_tituli_name': f_status_tituli,
                'start_date': f_start_date,  
                'end_date': f_end_date,
                'dating_strategy': f_dating_strategy
            }
            execute_advanced_search(form_payload)

    with col_btn2:
        if st.session_state.get("active_search_has_run"):
            dynamic_sql_query = generate_bulk_search_sql()
            
            # Capture the click state of the SQL download button
            sql_clicked = st.download_button(
                label="Download SQL Query",
                data=dynamic_sql_query,
                file_name="search_results_compiled_query.sql",
                mime="text/plain",
                use_container_width=True,
                key="btn_download_raw_sql_query"
            )
            
            if sql_clicked:
                st.session_state["skip_scroll"] = True
                st.rerun()
        else:
            st.button(
                label="Download SQL Query",
                key="btn_advanced_sql_disabled",
                use_container_width=True,
                disabled=True,
                help="Make a search first to unlock SQL query generation."
            )
# SEARCH BY BIBLIOGRAPHY / LITERATURE SEARCH

with st.expander("Search by Bibliography / Literature Search", expanded=False):
    # Initialize session state placeholders for tracking results between user interactions
    if "lit_matches" not in st.session_state:
        st.session_state.lit_matches = []
    if "lit_search_type" not in st.session_state:
        st.session_state.lit_search_type = None

    # Row 1: The Input Columns
    col1, col2 = st.columns(2)
    
    with col1:
        abbr_input = st.text_input(
            "Search by Abbreviated Citation",
            value=""
        )
        st.markdown("Please use [EDCS style](https://edcs.hist.uzh.ch/sources) abbreviated citations")
        
    with col2:
        author_input = st.text_input(
            "Search by Author / Work / Full Citation",
            value=""
        )

    # Row 2: Independent Triggers
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        if st.button("Show Matching Bibliography Records", key="lit_btn_left"):
            raw_input = abbr_input.strip()
            if not raw_input:
                st.warning("Please type an abbreviated citation phrase first.")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # Hardcoded Rule: Map ILS and D/Dessau interchangeably
                    cleaned_upper = raw_input.upper().replace('.', '').replace(',', '')
                    
                    if cleaned_upper == "ILS" or cleaned_upper == "D" or cleaned_upper == "DESSAU":
                        query = """
                            SELECT DISTINCT unique_citation_id, expanded_citation 
                            FROM unique_citations 
                            WHERE abbreviated_citation LIKE ? 
                               OR abbreviated_citation LIKE ?
                               OR expanded_citation LIKE ? 
                               OR expanded_citation LIKE ?
                            ORDER BY expanded_citation ASC;
                        """
                        w1, w2 = "%ILS%", "%Dessau%"
                        params = (w1, w2, w1, w2)
                    else:
                        # Standard single-term search behavior
                        query = """
                            SELECT DISTINCT unique_citation_id, expanded_citation 
                            FROM unique_citations 
                            WHERE abbreviated_citation LIKE ? 
                               OR expanded_citation LIKE ?
                            ORDER BY expanded_citation ASC;
                        """
                        search_term = f"%{raw_input}%"
                        params = (search_term, search_term)
                    
                    cursor.execute(query, params)
                    results = cursor.fetchall()
                    
                    st.session_state.lit_matches = results
                    st.session_state.lit_search_type = "left"
                    conn.close()
                except Exception as e:
                    st.error(f"Database query error: {e}")
    with btn_col2:
        if st.button("Show Matching Bibliography Records", key="lit_btn_right"):
            raw_input = author_input.strip()
            if not raw_input:
                st.warning("Please enter an author, editor, work, or full citation.")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # Helper to build an order-independent multi-word search query
                    def build_multi_word_query(search_text):
                        words = [w.strip() for w in search_text.split() if w.strip()]
                        if not words:
                            return None, []
                        
                        conditions = []
                        params = []
                        for word in words:
                            # Hardcoded Rule: Map ILS and Dessau interchangeably
                            cleaned_upper = word.upper().replace('.', '').replace(',', '')
                            if cleaned_upper == "ILS" or cleaned_upper == "DESSAU":
                                # Allow the database fields to match EITHER term dynamically
                                conditions.append(
                                    """(
                                        (uc.abbreviated_citation LIKE ? OR uc.expanded_citation LIKE ? OR m.bibliography_name LIKE ? OR m.chicago_translation LIKE ?)
                                        OR 
                                        (uc.abbreviated_citation LIKE ? OR uc.expanded_citation LIKE ? OR m.bibliography_name LIKE ? OR m.chicago_translation LIKE ?)
                                    )"""
                                )
                                w1, w2 = "%ILS%", "%Dessau%"
                                params.extend([w1, w1, w1, w1, w2, w2, w2, w2])
                            else:
                                # Normal dynamic clause for any other standard words
                                wildcard = f"%{word}%"
                                conditions.append(
                                    "(uc.abbreviated_citation LIKE ? OR uc.expanded_citation LIKE ? OR m.bibliography_name LIKE ? OR m.chicago_translation LIKE ?)"
                                )
                                params.extend([wildcard, wildcard, wildcard, wildcard])
                            
                        sql = f"""
                            SELECT DISTINCT uc.unique_citation_id, uc.expanded_citation 
                            FROM unique_citations uc
                            LEFT JOIN master_citations_raw m ON uc.bibliography_id = m.bibliography_id
                            WHERE {" AND ".join(conditions)}
                            ORDER BY uc.expanded_citation ASC;
                        """
                        return sql, params

                    # Try 1: Run strict multi-word wildcard search (All words must match via AND)
                    query1, params1 = build_multi_word_query(raw_input)
                    if query1:
                        cursor.execute(query1, params1)
                        results = cursor.fetchall()
                    else:
                        results = []
                    
                    # Try 2: General Looser Partial Match Fallback
                    if not results and query1:
                        # Dynamically flip the strict "AND" operators to "OR" operators
                        looser_query = query1.replace(" WHERE ", " WHERE ").replace(" AND ", " OR ")
                        cursor.execute(looser_query, params1)
                        results = cursor.fetchall()
                    
                    # Try 3: Fallback with Roman numeral conversion if still nothing found
                    if not results:
                        converted_input = convert_roman_to_arabic_in_text(raw_input)
                        if converted_input != raw_input:
                            query2, params2 = build_multi_word_query(converted_input)
                            if query2:
                                # Try strict with converted input
                                cursor.execute(query2, params2)
                                results = cursor.fetchall()
                                
                                # Try loose with converted input if strict converted fails
                                if not results:
                                    looser_query2 = query2.replace(" AND ", " OR ")
                                    cursor.execute(looser_query2, params2)
                                    results = cursor.fetchall()
                            
                    st.session_state.lit_matches = results
                    st.session_state.lit_search_type = "right"
                    conn.close()
                except Exception as e:
                    st.error(f"Database query error: {e}")
                         
# Row 3: Dynamic Dropdown List Area & Action Hook Trigger
    if st.session_state.lit_matches:
        st.markdown("---")
        res_col1, res_col2 = st.columns(2)
        
        # 1. Store option metadata safely using session state to protect against redrawing flushes
        st.session_state.lit_display_map = {}
        for uc_id, exp_cit in st.session_state.lit_matches:
            if exp_cit:
                unique_key = f"{exp_cit.strip()} (Ref ID: {uc_id})"
                st.session_state.lit_display_map[unique_key] = uc_id

        # 2. Extract unique keys and sort using Natural Sorting
        raw_options = list(st.session_state.lit_display_map.keys())
        natural_sort_key = lambda s: [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
        sorted_options = sorted(raw_options, key=natural_sort_key)
        
        dropdown_choices = ["PLEASE SELECT"] + sorted_options

        with res_col1:
            selected_citation = st.selectbox(
                "Matching Bibliography Records Found:",
                options=dropdown_choices,
                key="lit_dropdown_selection"
            )
            
        with res_col2:
            st.markdown("<div style='padding-top:24px;'></div>", unsafe_allow_html=True)
            is_disabled = (selected_citation == "PLEASE SELECT")
            
            if st.button("Show Linked Inscriptions", key="lit_action_execute", disabled=is_disabled):
                target_unique_citation_id = st.session_state.lit_display_map.get(selected_citation)
                st.session_state["skip_scroll"] = False
                # Backup regex parse safety strategy if map drops out
                if target_unique_citation_id is None and "Ref ID: " in selected_citation:
                    try:
                        target_unique_citation_id = int(re.search(r'\(Ref ID:\s*(\d+)\)', selected_citation).group(1))
                    except Exception:
                        target_unique_citation_id = None
                
                if target_unique_citation_id is not None:
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        cursor.execute(
                            "SELECT DISTINCT inscription_id FROM inscriptions_and_citations WHERE unique_citation_id = ?",
                            (target_unique_citation_id,)
                        )
                        linked_ids = [row[0] for row in cursor.fetchall()]
                        
                        if not linked_ids:
                            st.info("No inscriptions are currently cataloged under that specific reference text.")
                            conn.close()
                        else:
                            # Set global list tracks for any secondary tools (like CSV exports)
                            st.session_state.active_inscription_ids = linked_ids
                            st.session_state.active_search_has_run = True
                            st.session_state["csv_mode"] = "ids"
                            
                            out_str = [
                                f"#### Found {len(linked_ids)} matching inscription(s) via Literature Search:\n", 
                                "_" * 70 + "\n\n"
                            ]
                            
                            for idx, ins_id in enumerate(linked_ids, 1):
                                out_str.append(f"## Result {idx}\n")
                                
                                # Connect cleanly straight into your universal global template string variable
                                cursor.execute(main_report_sql, (int(ins_id),))
                                card_rows = cursor.fetchall()
                                
                                if card_rows:
                                    dossier_text = "\n".join([r[0] for r in card_rows if r[0] is not None])
                                    out_str.append(dossier_text)
                                else:
                                    out_str.append(f"_Warning: Inscription ID {ins_id} could not compile properly._")
                                    
                                out_str.append("\n\n---\n\n")
                            
                            st.session_state.search_results = "".join(out_str)
                            conn.close()
                            
                            st.session_state.lit_matches = []
                            st.session_state.lit_search_type = None
                            if "lit_display_map" in st.session_state:
                                del st.session_state.lit_display_map
                                
                            st.rerun()
                            
                    except Exception as action_err:
                        st.error(f"Failed sourcing linked junction table IDs: {action_err}")
                else:
                    st.error("Could not resolve reference citation ID choice. Please pick an item again.")
                    
    elif st.session_state.lit_search_type is not None:
        st.markdown("---")
        st.info("No matching bibliographies or references found inside the database columns.")
             

                 
# EXPORT TO CSV AND GENERATE MAP BUTTONS
col_exp_left, col_exp_mid, col_exp_right = st.columns([1.5, 1.5, 1.5])

has_basic_results = bool(st.session_state.get("active_inscription_ids"))
has_advanced_results = (st.session_state.get("csv_mode") == "advanced" and bool(st.session_state.get("active_search_where_clauses")))

if (
    (has_basic_results or has_advanced_results)
    and st.session_state.get("active_search_has_run")
    and not st.session_state.get("inputs_are_dirty", False)
):
    with col_exp_left:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            global_csv_string = generate_bulk_search_csv(cursor)
            conn.close()
        except Exception as e:
            global_csv_string = f"Error compiling dataset: {str(e)}"

        csv_clicked = st.download_button(
            label="Export Results to CSV",
            data=global_csv_string,
            file_name="search_results_export.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_global_results_csv_export"
        )
        
        if csv_clicked:
            st.session_state["skip_scroll"] = True
            st.rerun()
        
    with col_exp_mid:
        if st.button("Generate Map", key="global_map_btn", use_container_width=True, type="primary"):
            active_ids = st.session_state.get("active_inscription_ids", [])
            
            unmappable_place_ids = set()
            st.session_state["unmappable_html_notice"] = None
            
            if not active_ids:
                st.session_state["map_status"] = "zero_search_results"
                st.session_state["trigger_map_html"] = None
                # Lock in tracking parameters so the automatic commit detector doesn't instantly wipe this out
                st.session_state["last_mapped_search"] = {
                    "where": st.session_state.get("active_search_where_clauses", []),
                    "params": st.session_state.get("active_search_query_params", {}),
                    "ids_count": 0
                }
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # Overwrite the empty set dynamically since we have data to fetch
                    cursor.execute('SELECT place_id FROM "places" WHERE "longitude" IS NULL;')
                    unmappable_place_ids = {row[0] for row in cursor.fetchall()}
                    
                    # Build placeholders for primary search scope
                    placeholders = ",".join("?" for _ in active_ids)
                    
                    # Fetch data for ALL inscriptions in the current search scope
                    query = f"""
                        SELECT m.inscription_id, m.inscription_ref, m.line_ref, m.place_id, p.province_name
                        FROM Max_Thrax m
                        LEFT JOIN provinces p ON m.province_id = p.province_id
                        WHERE m.inscription_id IN ({placeholders})
                    """
                    cursor.execute(query, tuple(active_ids))
                    all_rows = cursor.fetchall()
                    conn.close()
                    
                    # Separate rows using precise mapping keys
                    unmappable_rows = [r for r in all_rows if r[3] in unmappable_place_ids]
                    valid_rows_count = len(all_rows) - len(unmappable_rows)
                    
                    # Scenario A Check: Are 100% of rows unmappable?
                    if len(all_rows) > 0 and valid_rows_count == 0:
                        st.session_state["map_status"] = "unmappable_coordinates"
                        st.session_state["trigger_map_html"] = None
                        st.session_state["last_mapped_search"] = {
                            "where": st.session_state.get("active_search_where_clauses", []),
                            "params": st.session_state.get("active_search_query_params", {}),
                            "ids_count": len(active_ids)
                        }
                    else:
                        st.session_state["map_status"] = "success"

                        # Scenario B Check: Are SOME rows unmappable? If yes, group and link them
                        if len(unmappable_rows) > 0:
                            province_groups = {}
                            for r in unmappable_rows:
                                ins_id, ins_ref, l_ref, place_id, p_name = r
                                p_name = p_name if p_name else "Unknown Province"
                                if p_name not in province_groups:
                                    province_groups[p_name] = []
                                province_groups[p_name].append((ins_id, ins_ref, l_ref))
                            
                            html_alerts = []
                            for p_name, items in province_groups.items():
                                count_x = len(items)
                                links = []
                                for f_id, ref, l_ref in items:
                                    report_url = f"https://maximinusthraxdatabaseui.streamlit.app/?ins_id={f_id}"
                                    display_text = f"{ref} | {l_ref}" if (ref and l_ref) else (ref if ref else l_ref)
                                    links.append(f"<a href='{report_url}' target='_blank' style='color: #b45309; font-weight: bold; text-decoration: underline;'>{display_text}</a>")
                                
                                links_str = ", ".join(links)
                                
                                alert_box = f"""
                                <div style="
                                    background-color: #fffbeb; 
                                    border-left: 4px solid #d97706; 
                                    padding: 12px 15px; 
                                    border-radius: 4px; 
                                    margin-bottom: 10px;
                                    font-family: 'Source Sans Pro', sans-serif;
                                    font-size: 13px;
                                    color: #78350f;
                                ">
                                    <strong>Warning:</strong> {count_x} inscription(s) in the province of <em>{p_name}</em> is/are not shown.<br>
                                    The following inscriptions are in {p_name} but are not linked to modern coordinates: {links_str}
                                </div>
                                """
                                html_alerts.append(alert_box)
                            
                            st.session_state["unmappable_html_notice"] = "".join(html_alerts)
                        
                        # Lock in tracking parameters and call map renderer
                        st.session_state["last_mapped_search"] = {
                            "where": st.session_state.get("active_search_where_clauses", []),
                            "params": st.session_state.get("active_search_query_params", {}),
                            "ids_count": len(active_ids)
                        }
                        generate_active_map()
                
                except Exception as e:
                    st.error(f"Database setup error inside button: {e}")
            
            st.session_state["map_expander_open"] = True
            st.session_state["map_version"] = st.session_state.get("map_version", 0) + 1
            st.session_state["trigger_map_scroll"] = True
            st.session_state["skip_scroll"] = True
            st.rerun()
else:
    with col_exp_left:
        st.button(
            label="Export Results to CSV", key="global_csv_disabled_footer_csv",
            use_container_width=True, disabled=True, help="Make a search before exporting search results."
        )
    with col_exp_mid:
        st.button(
            label="Generate Map", key="global_map_disabled_footer_map",
            use_container_width=True, disabled=True, help="Make a search before mapping search results."
        )

# --- AUTOMATIC SEARCH COMMIT DETECTOR ---
current_search_fingerprint = {
    "where": st.session_state.get("active_search_where_clauses", []),
    "params": st.session_state.get("active_search_query_params", {}),
    "ids_count": len(st.session_state.get("active_inscription_ids", [])) if st.session_state.get("active_inscription_ids") else 0
}

# Only wipe the map if last_mapped_search WAS ALREADY SET and now no longer matches
if (
    st.session_state.get("last_mapped_search") is not None 
    and st.session_state.get("last_mapped_search") != current_search_fingerprint
):
    st.session_state["map_status"] = None
    st.session_state["trigger_map_html"] = None
    st.session_state["unmappable_html_notice"] = None

# --- UNIFIED LAYOUT SCROLL INJECTOR ---
# Force scrolling to results when a standard search finishes
if st.session_state.get("active_search_has_run") and not st.session_state.get("skip_scroll", False):
    st.components.v1.html(
        """
        <script>
            window.parent.document.getElementById('results-anchor').scrollIntoView({behavior: 'smooth'});
        </script>
        """,
        height=0,
    )
    # Lock scroll so it only runs once per button click
    st.session_state["skip_scroll"] = True

# Explicit scroll for the map button
if st.session_state.get("trigger_map_scroll"):
    st.session_state["trigger_map_scroll"] = False
    st.markdown('<div id="map-anchor"></div>', unsafe_allow_html=True)
    st.components.v1.html(
        """
        <script>
            window.parent.document.getElementById('map-anchor').scrollIntoView({behavior: 'smooth'});
        </script>
        """,
        height=0,
    )

# Ensure these variables are completely unindented (aligned to the far-left margin)
is_map_open = st.session_state.get("map_expander_open", True)
current_version = st.session_state.get("map_version", 0)

# MAP VIEWER (Always Visible)
with st.expander("Expand/Collapse Interactive Map", expanded=is_map_open, key=f"interactive_map_expander_v{current_version}"):
         
# MAP VIEWER (Always Visible)
with st.expander("Expand/Collapse Interactive Map", expanded=is_map_open, key=f"interactive_map_expander_v{current_version}"):
    if st.session_state.get("map_status") == "zero_search_results":
        st.warning("No inscription matched your search")
        
    elif st.session_state.get("map_status") == "unmappable_coordinates":
        st.warning("None of the inscriptions matching your search has a findspot linked to modern coordinates")
        
    elif st.session_state.get("trigger_map_html"):
     
        st.markdown(
            """
            <div style="
                background-color: #f0f4ff; 
                border-left: 4px solid #1a53ff; 
                padding: 10px 15px; 
                border-radius: 4px; 
                margin-bottom: 12px;
                font-family: 'Source Sans Pro', sans-serif;
                font-size: 13px;
                color: #1e293b;
            ">
                Double Click anywhere on the map to toggle the control panels on/off for a cleaner view.<br>
                Since double-clicking is reserved for toggling the control panels, use your mouse scroll wheel, trackpad pinch, or the [+] and [-] buttons (when visible) to zoom.<br>
                Click on any feature to see a pop up with more information<br>
                If you click on a hyperlink to a road segment on the itiner-e project, upon being redirected, you may need to click the button Explore Roman Roads to skip their welcome screen
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        if st.session_state.get("unmappable_html_notice"):
            st.markdown(st.session_state["unmappable_html_notice"], unsafe_allow_html=True)
            
        st.components.v1.html(st.session_state.trigger_map_html, height=720, scrolling=True)
        
    else:
        st.info("No map generated yet. Make a search and click 'Generate Map' to plot inscriptions matching your query on a map.")

# SEARCH RESULTS
st.markdown("### Search Results")

# RESULTS LIST VIEW
if st.session_state.get("active_search_has_run") and st.session_state.get("active_inscription_ids"):
    
    # Extract the active IDs found by your search functions
    matched_ids = st.session_state.active_inscription_ids
    
    try:
        # Open a completely fresh connection to keep it isolated
        conn_overview = get_db_connection()
        cursor_overview = conn_overview.cursor()
        
        # Build dynamic placeholders for safety
        placeholders = ",".join(["?"] * len(matched_ids))
        
        overview_sql = f"""
        SELECT 
            mt.inscription_id,
            mt.object_id,
            mt.inscription_ref,
            COALESCE(mt.line_ref, '') AS line_ref,
            COALESCE(pr.province_name, 'N/A') AS province_name,
            COALESCE(dt.distributio_titulorum, 'N/A') AS type_of_inscription,
            CASE 
                -- 1. Erasure Relevant to Maximinus Thrax
                WHEN mt.relevance_index = 1 
                     AND EXISTS (SELECT 1 FROM "interventions" i WHERE i.patient_inscription = mt.inscription_id AND i.method_id = 2)
                     AND mt.inscription_id NOT IN (SELECT ip.inscription_id FROM "inscriptions_and_persons" ip WHERE ip.person_id = 50)
                THEN '**Erasure relevant to Maximinus Thrax**'
                
                -- 2. Erasure not relevant to Maximinus Thrax (Condition A & B)
                WHEN (mt.relevance_index = 1 
                      AND EXISTS (SELECT 1 FROM "interventions" i WHERE i.patient_inscription = mt.inscription_id AND i.method_id = 2)
                      AND mt.inscription_id IN (SELECT ip.inscription_id FROM "inscriptions_and_persons" ip WHERE ip.person_id = 50))
                     OR 
                     (mt.relevance_index = 0 
                      AND EXISTS (SELECT 1 FROM "interventions" i WHERE i.patient_inscription = mt.inscription_id AND i.method_id = 2))
                THEN '**Erasure not relevant to Maximinus Thrax**'
                
                -- 3. No Erasure
                ELSE '**No Erasure**'
            END AS erasure_status
        FROM "Max_Thrax" mt
        LEFT JOIN "provinces" pr ON mt.province_id = pr.province_id
        LEFT JOIN "distributio_titulorum" dt ON mt.distributio_titulorum_id = dt.distributio_titulorum_id
        WHERE mt.inscription_id IN ({placeholders})
        ORDER BY mt.inscription_id ASC;
        """
        
        cursor_overview.execute(overview_sql, [int(x) for x in matched_ids])
        overview_rows = cursor_overview.fetchall()
        
        conn_overview.close()

        with st.expander("Search Results List View", expanded=False):
            st.markdown(f"**Found {len(overview_rows)} records matching your search:**")
            
            with st.container(height=300, border=False):
                for row in overview_rows:
                    ins_id, obj_id, ins_ref, line_ref, prov_name, type_of_inscription, erasure_status = row
                    
                    ref_line = f" {line_ref}" if line_ref else ""
                    
                    app_url = f"https://maximinusthraxdatabaseui.streamlit.app/?ins_id={ins_id}"
                    obj_url = f"https://maximinusthraxdatabaseui.streamlit.app/?obj_id={obj_id}"
                    obj_display = f"[{obj_id}]({obj_url})" if obj_id is not None else "N/A"
                    
                    st.markdown(
                        f"* [Inscription ID: {ins_id}]({app_url}) | "
                        f"**Quick Reference:** {ins_ref}{ref_line} | "
                        f"**Object ID:** {obj_display} | "
                        f"**Province:** {prov_name} | "
                        f"**Type of Inscription:** {type_of_inscription} | "
                        f"*{erasure_status}*"
                    )
                
    except Exception as overview_error:
        st.warning(f"Could not render the List View container: {overview_error}")


# MAIN RESULTS VIEW
if st.session_state.get("active_search_has_run"):
    
    if st.session_state.get("skip_scroll"):
        st.session_state["skip_scroll"] = False
    else:
        st.markdown('<div id="results-anchor"></div>', unsafe_allow_html=True)
        teleport_to_results()

    with st.container(height=520, border=True):
        raw_results = st.session_state.search_results
        clean_text = raw_results.replace("\r\n", "\n").replace("\r", "\n")
        blocks = clean_text.split("\n\n")
        process_this_block = False

        for block in blocks:
            cleaned_block = block.strip()
            lines = cleaned_block.split("\n")
            has_dangerous_dashes = any(
                line.strip().startswith("---") for line in lines
            )

            if any(header in cleaned_block for header in ["Nonstandard Spellings:", "Context:", "Support:", "Dating:", "Material:", "Province:", "Place:", "Bibliography:", "Persons:"]):
                process_this_block = False

            if process_this_block:
                block = convert_markdown_bold_to_underline(block)
          
            if "Inscription Text:" in cleaned_block:
                process_this_block = True

            if cleaned_block == "**Inscription Text:**":
                st.markdown(cleaned_block)
                
            elif (
                "RIGHT:" in cleaned_block
                or "------ /" in cleaned_block
                or has_dangerous_dashes
                or process_this_block  
            ):
                html_block = block.replace("\n", "<br>")
                st.markdown(
                    f'<div style="font-size:16px; font-weight:normal; margin-bottom:1rem;">{html_block}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(block)
                     
# AUTOSCROLLING TO RESULTS IF USER ARRIVES FROM A LINK

if 'should_scroll' in locals() and should_scroll:
    # 1. Place the landing anchor that the smooth scroller will look for
    st.markdown('<div id="link-scroll-target"></div>', unsafe_allow_html=True)
    
    # 2. Execute the smooth glide script targeting the anchor above
    st.components.v1.html(
        """
        <script>
            function executeScroll() {
                // Look outside the iframe into the main page for our anchor element
                var target = window.parent.document.getElementById('link-scroll-target');
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } else {
                    // Retry quickly if the main DOM hasn't rendered it yet
                    setTimeout(executeScroll, 50);
                }
            }
            window.addEventListener('load', executeScroll);
            setTimeout(executeScroll, 100);
        </script>
        """,
        height=0
    )
