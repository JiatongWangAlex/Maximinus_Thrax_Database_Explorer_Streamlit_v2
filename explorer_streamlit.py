"""
Jiatong Wang | DATABASE GUI 
--------------------------------------------------------------------   
The dataset and data structure queried by this GUI is FULLY HUMAN MADE AND HUMAN DESIGNED as a supplement to my BA thesis.


Purpose: This GUI allows anyone to browse my BA thesis supplemental database (a relational database in SQLite about memory sanctions against Maximinus Thrax) .
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
This file itself is somewhat reusable for a different project as long as backend_logic.py and the schema of version_58.db stays the same.


HOWEVER the parts of the interface (Advanced Search,  List View, and Map Viewer) which contain logic flagging inscriptions according
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

--------------------------------------------------------------------
In get_inscription_report the text output for each method_id and extent_id are hardcoded, instead of being dynamically fetched from a field in the database. 
IF you reuse this, make sure to change/check the section.

                   
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

def commit_search_and_wipe_inputs():
    """Wipes text fields instantly after click, keeping only active results and mapping IDs."""
    inputs_to_clear = [
        "main_text_input", "edcs_report_input", "id_report_input", 
        "person_lookup_input", "person_report_input",
        "lit_abbr_input",    
        "lit_name_or_full_citation_input"
    ]
    for field in inputs_to_clear:
        if field in st.session_state:
            st.session_state[field] = ""
            
    if "person_select_input" in st.session_state:
        st.session_state["person_select_input"] = "PLEASE SELECT"
             
    st.session_state["person_matches"] = []
         
    for anchor in ["last_searched_text", "last_searched_edcs", "last_searched_id", "last_searched_lookup", "last_searched_person"]:
        if anchor in st.session_state:
            st.session_state[anchor] = ""
        
    st.session_state.lit_matches = []        
    st.session_state.lit_search_type = None  
    
    if "lit_display_map" in st.session_state:
        del st.session_state.lit_display_map
             
    st.session_state["show_comma_list"] = False
    st.session_state["inputs_are_dirty"] = False
    st.session_state["skip_scroll"] = False

# SEARCH CALLBACK FUNCTIONS

def callback_text_search():
    val = st.session_state.get("main_text_input", "").strip()
    if val:
        st.session_state["last_searched_text"] = val
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_has_run"] = True
        st.session_state["trigger_map_html"] = None
        st.session_state["inputs_are_dirty"] = False
        st.session_state["skip_scroll"] = False
        run_standard_search(val)
        commit_search_and_wipe_inputs()

def callback_edcs_search():
    val = st.session_state.get("edcs_report_input", "").strip()
    if val:
        st.session_state["last_searched_edcs"] = val
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_has_run"] = True
        st.session_state["trigger_map_html"] = None
        st.session_state["inputs_are_dirty"] = False
        st.session_state["skip_scroll"] = False
        run_ref_search(val)
        commit_search_and_wipe_inputs()

def callback_id_search():
    val = st.session_state.get("id_report_input", "").strip()
    if val:
        st.session_state["last_searched_id"] = val
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_has_run"] = True
        st.session_state["trigger_map_html"] = None
        st.session_state["inputs_are_dirty"] = False
        st.session_state["skip_scroll"] = False 
             
        parsed_ids = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
        
        if parsed_ids:
            st.session_state.active_inscription_ids = parsed_ids
            fetch_metadata_by_id(val)
            commit_search_and_wipe_inputs()
        else:
            st.session_state.search_results = "Please enter Inscription ID(s) as pure numbers."
            st.session_state.active_inscription_ids = []
                 
def callback_person_report_dropdown():
    selected_option = st.session_state.get("person_select_input", "PLEASE SELECT")
    if selected_option == "PLEASE SELECT":
        st.session_state["person_dropdown_error"] = True
    else:
        st.session_state["person_dropdown_error"] = False
        st.session_state["show_lookup_hint"] = False
        st.session_state["skip_scroll"] = False
        st.session_state["trigger_map_html"] = None
        st.session_state["last_searched_person"] = selected_option
        st.session_state["csv_mode"] = "ids"
        st.session_state["active_search_has_run"] = True
        st.session_state["inputs_are_dirty"] = False
        extracted_id = selected_option.split("(ID: ")[-1].replace(")", "").strip()
        generate_person_report(extracted_id)
        commit_search_and_wipe_inputs()

def callback_person_report_text():
    val = st.session_state.get("person_report_input", "").strip()
    if val:
        st.session_state["last_searched_person"] = val
        st.session_state["active_search_has_run"] = True
        st.session_state["inputs_are_dirty"] = False
        st.session_state["trigger_map_html"] = None
        st.session_state["skip_scroll"] = False
        generate_person_report(val)
        commit_search_and_wipe_inputs()

def callback_advanced_search(payload):
    """Executes the advanced search and triggers scroll behavior 

    without wiping the advanced search form fields.
    """
    st.session_state["csv_mode"] = "advanced"
    st.session_state["active_inscription_ids"] = []
    st.session_state["skip_scroll"] = False
    st.session_state["trigger_map_html"] = None

    execute_advanced_search(payload)
         
def callback_literature_search():
    selected_option = st.session_state.get("lit_dropdown_selection", "PLEASE SELECT")
    
    if selected_option != "PLEASE SELECT":
        target_unique_citation_id = st.session_state.lit_display_map.get(selected_option)
        st.session_state["skip_scroll"] = False
        st.session_state["trigger_map_html"] = None
        
        if target_unique_citation_id is None and "Ref ID: " in selected_option:
            try:
                target_unique_citation_id = int(re.search(r'\(Ref ID:\s*(\d+)\)', selected_option).group(1))
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
                    st.session_state.search_results = "No inscriptions are currently cataloged under that specific reference text."
                else:
                    st.session_state.active_inscription_ids = linked_ids
                    st.session_state.active_search_has_run = True
                    st.session_state["csv_mode"] = "ids"
                    
                    # 1. Start the visual layout structure locally
                    out_str = [
                        f"#### Found {len(linked_ids)} matching inscription(s) via Literature Search:\n", 
                        "_" * 70 + "\n\n"
                    ]
                    
                    # 2. Batch fetch ALL dossiers at once to prevent looping lag
                    batched_dossiers = get_inscription_report(cursor, linked_ids)
                    
                    # 3. Stitch the blocks together sequentially
                    for ins_id in linked_ids:
                        out_str.append(f"## Inscription ID {ins_id}\n")
                        dossier_text = batched_dossiers.get(int(ins_id))
                        
                        if dossier_text and dossier_text != "No inscription data found.":
                            out_str.append(dossier_text)
                        else:
                            out_str.append(f"_Warning: Inscription ID {ins_id} could not compile properly._")
                            
                        out_str.append("\n\n---\n\n")
                    
                    # 4. Save the single, completely stitched text asset to session state
                    st.session_state.search_results = "".join(out_str)
                
                conn.close()
                
                # RUN YOUR WIPE FUNCTION AT THE END! Exactly like the other callbacks do
                commit_search_and_wipe_inputs()
                
            except Exception as action_err:
                st.error(f"Failed sourcing linked junction table IDs: {action_err}")
                     

# ----------------------------------------------------------------------------------------------------------------------------
# UI FRONTEND



st.set_page_config(page_title="Maximinus Thrax Database Browser", layout="wide")

st.components.v1.html(
    """
    <script>
        window.parent.addEventListener('message', function(event) {
            if (event.data && event.data.type === 'scroll') {
                var target = window.parent.document.getElementById(event.data.target);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    </script>
    """,
    height=0
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
db_path = os.path.join(BASE_DIR, "maximinus_thrax.db")

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
for widget_key, anchor_key in tracked_fields.items():
    if widget_key in st.session_state:
        current_value = str(st.session_state[widget_key]).strip()
        last_executed_value = str(st.session_state.get(anchor_key, "")).strip()
        
        if current_value == "PLEASE SELECT": current_value = ""
        if last_executed_value == "PLEASE SELECT": last_executed_value = ""
            
        if current_value != last_executed_value:
            any_input_has_unsearched_changes = True

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
## How to Use | 
### DEVELOPMENT NOTE: This instruction manual was written for an earlier version of the webapp. I am working on a new one.

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
* Browsing the map and want to learn more about a specific inscription without scrolling to it in the ? Type its ID here and click **Generate Report!**
* > **NOTE:** This will clear your original . Consider opening a new window for this if you are using complex filters.
    
### Lookup Person ID by Name
* Want to search for a specific individual without using the main search bar? Insert the person's name, click the **Person Name** button, and look at the **Select Person** field to the right.
* **Select the desired individual** before clicking the **Generate Report** button.
  > **NOTE:** Please manually select an individual before generating a report. The default individual at the top of the selection bar is not guaranteed to be the person you have in mind. 
    
### Interactive Map
* Loading the map may take a second due to the size of the itiner-e roads layer.
  > **NOTE:** You must manually press the **Generate Map** button *every time* after a search or after generating a person/inscription report to display the relevant inscriptions on the map.
* Click any dot on the map to view its details.
* In all applicable cases, the **EDCS** record and the **Pleiades** record (for the findspot area) are hyperlinked.
* **For milestone inscriptions:** The details popup notes that the inscription is on a milestone, names the road segment it served, and links to that segment on the **itiner-e project.** * *Note on itiner-e:* If it shows a welcome screen, click *Explore Roman Roads* to continue to the linked segment, then click *Details* on the left for more information.
* **For non-milestone inscriptions:** The *titulorum distributio* (type of inscription) and type of support are displayed in the details popup instead of road information.
* **For multiple inscriptions on a single object:** The popup displays the total number of inscriptions on the support and the sequence ID of your selected inscription. A sequence ID of `1` means it was the earliest inscription on the object, `2` means it was the second, etc.
  * You can see all the inscriptions on the same object in chronological order if you click on the hyperlinked inscription ID. This will open a report in a new window. 

### Advanced Search
With advanced search, you can look for multiple words by connecting them with Boolean logic operators (which must be written in **UPPERCASE**):

* **AND** (e.g., `Maximinus AND legatum` to find entries containing both terms)
* **OR** (e.g., `cohors OR legio` to find entries containing either term)
* **NOT** (e.g., `Maximinus NOT Maximus` to exclude specific textual entries)

#### Available Filters:
The advanced search suite offers the following filters: 

Inscription Metadata:
Inscription Relevance to Maximinus Thrax, Province, Place, Distributio Titulorum | Type of Inscription, Support Type, Context Type, Material, Status Tituli | Preservation Status, Number of Inscriptions on Object, Start Year, End Year, Search Strategy

People and Institutions:
Advanced People Search, Institution/Group/Military Unit Search, Distributio Virorum | Type of People Mentioned, Attested Status Title, Attested Office/Military Role

Later Modifications / Reuse
Intervention Status, Intervention Relevance to Maximinus Thrax, Method of Intervention, Extent of Intervention, Target of Intervention

> **Note on the "Relevance?" field:** Some physical objects bear both an inscription created during the reign of Maximinus Thrax and an earlier or later inscription. For all inscriptions explicitly mentioning Maximinus Thrax, Gaius Iulius Verus Maximus, or a military unit bearing the honorary epithet *Maximiniana*, the relevance field resolves to `true`.

You may also download your search conditions as an sql query

### Bibliography Search
You may now search inscriptions by their bibliography (either full or abbreviated)


""")

# MAIN SEARCH AND PERSON AND INSCRIPTION REPORTS

st.markdown("### Key Word or Phrase Search")
col_text1, col_text2 = st.columns([3, 1])

if "main_text_input" in st.session_state:
    if st.session_state["main_text_input"].strip() != st.session_state.get("last_searched_text", ""):
        st.session_state["inputs_are_dirty"] = True

with col_text1:    
    text_input_var = st.text_input(
        "Enter search text:", 
        placeholder="e.g. Maximinus",
        key="main_text_input",
        label_visibility="collapsed",
        on_change=reset_map_and_search_flags
    )

with col_text2:
    st.button("Search Text", key="btn_execute_text", use_container_width=True, type="primary", on_click=callback_text_search)
        
# Full Reports Panel Layout Execution Shell
st.markdown("### Search by Inscription or Person")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

if "edcs_report_input" in st.session_state and st.session_state["edcs_report_input"].strip() != st.session_state.get("last_searched_edcs", ""):
    st.session_state["inputs_are_dirty"] = True
if "id_report_input" in st.session_state and st.session_state["id_report_input"].strip() != st.session_state.get("last_searched_id", ""):
    st.session_state["inputs_are_dirty"] = True
if "person_lookup_input" in st.session_state and st.session_state["person_lookup_input"].strip() != st.session_state.get("last_searched_lookup", ""):
    st.session_state["inputs_are_dirty"] = True

with col_s1:
    ref_input_var = st.text_input(
        "EDCS/TM number:", 
        placeholder="e.g. EDCS-12345678/TM 123456/raw number", 
        key="edcs_report_input", 
        on_change=reset_map_and_search_flags
    )
    st.button("Generate Inscription Report", use_container_width=True, type="primary", on_click=callback_edcs_search)

with col_s2:
    id_input_var = st.text_input(
        "Inscription ID or IDs:", 
        placeholder="1 or 1, 2, 3", 
        key="id_report_input",
        on_change=reset_map_and_search_flags
    )
    st.button("Generate Inscription Report(s)", use_container_width=True, type="primary", on_click=callback_id_search)

with col_s3:
    pname_input_var = st.text_input(
        "Look up Person by Name:", 
        placeholder="e.g. Quintus Decius", 
        key="person_lookup_input",
        on_change=reset_map_and_search_flags
    )
    if st.button("Find Person", use_container_width=True):
        if pname_input_var.strip():
            st.session_state["last_searched_lookup"] = pname_input_var.strip()
            lookup_person_options(pname_input_var)
            if "person_matches" in st.session_state and st.session_state.person_matches:
                st.session_state["show_lookup_hint"] = True
            st.rerun()

    if st.session_state.get("show_lookup_hint") and st.session_state.get("person_matches"):
        st.info("Please select a person from the dropdown menu in 'Select Person', then click Generate Person Report.")
                 
with col_s4:
    if st.session_state.get("person_matches"):
        options_list = ["PLEASE SELECT"] + [f"{row[1]} (ID: {row[0]})" for row in st.session_state.person_matches]
        
        selected_option = st.selectbox(
            "Select Person:", 
            options_list, 
            key="person_select_input",
            on_change=reset_map_and_search_flags
        )
        
        st.button("Generate Person Report", key="btn_person_select_submit", use_container_width=True, type="primary", on_click=callback_person_report_dropdown)
        
        if st.session_state.get("person_dropdown_error"):
            st.error("Please pick a person from the dropdown menu before generating a report!")
    else:
        pid_input_var = st.text_input(
            "Person Selector / Search by Person ID:", 
            placeholder="Select from dropdown menu/Search by ID", 
            key="person_report_input",
            on_change=reset_map_and_search_flags
        )
        st.button("Generate Person Report", key="btn_person_text_submit", use_container_width=True, type="primary", on_click=callback_person_report_text)
                     
# ADVANCED SEARCH

with st.expander("Advanced Search", expanded=False):
    st.markdown("### Advanced Search")
    st.caption("Scroll down and click 'Execute Advanced Search' to search!")
         
    st.markdown("#### Text Search")       
    f_text = st.text_input(
        "Can be combined with Filters | Boolean Logic Operators Allowed:", 
        placeholder="e.g. Maximinus AND legatum",
       on_change=reset_map_and_search_flags
    )
         
    st.caption(
        "Use 'Advanced People Search' for queries like PERSON A NOT PERSON B | See Supported logic operators", 
        help=(
            "**Supported Operators:**\n"
            "You can use **AND**, **OR**, and **NOT** in your queries; Other boolean operators are not supported by SQL \n"
        )
    )
         
    text_search_mode = st.radio(
        "Text Search Strategy:",
        options=[
            "Assisted Match",
            "Exact Match"
        ],
        index=0,
        key="adv_text_search_mode",
        on_change=reset_map_and_search_flags,
        help="'Exact Match' searches your exact string. 'Assisted Match' can find inscriptions containing non-standard spellings of your search term; it also checks whether your search term PARTIALLY matches the name of any identified individuals or groups in the corpus and pulls all inscriptions linked with those individuals or groups. We cannot automatically check all inflected forms of your search term at this moment. The search bar also CANNOT search for PERSON A NOT PERSON B because it does not know which specific person you are referring to with your search term; For such purposes it is recommended to use the ADVANCED PEOPLE SEARCH BELOW."
    )
         
    st.markdown("---")
    st.markdown("#### Filters")
    st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    # COLUMN 1: Inscription Metadata
    with col1:
        st.markdown("##### Based on Inscription Metadata")
        
        relevance_options = [
            "Relevant",
            "All inscriptions regardless of relevance",
            "Not Relevant"
        ]
        f_rel = st.selectbox("Inscription Relevance to Maximinus Thrax:", relevance_options, on_change=reset_map_and_search_flags)
        f_prov = st.multiselect("Province:", [opt for opt in get_filter_options("provinces", "province_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_in_place = st.multiselect("Place:", [opt for opt in get_filter_options("places", "place_name") if opt != "All"], on_change=reset_map_and_search_flags)
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
                "A: Search for all inscriptions whose date range overlaps with this range" if x == "overlap"
                else "B: Search for only inscriptions whose date range is fully contained within this range"
            ),
            help=(
                "• A: Returns all inscriptions dated to a time period that overlaps with your search window. "
                "For example, if you search 236–237 CE, inscriptions dated to 236 CE or 237CE or 236-237CE will appear, "
                "and so will inscriptions dated to 235–238 CE.\n\n"
                "• B: Returns only inscriptions dated to a time period that falls completely inside your search window. "
                "For example, if you search 236–236 CE, an inscription dated specifically to 236 CE will appear, "
                "but an inscription dated to 235–238 CE will be excluded."
            ),
            on_change=reset_map_and_search_flags
        )
        
    # COLUMN 2: People and Institutions
    with col2:
        st.markdown("##### Based on People and Institutions")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT person_id, person_name FROM persons ORDER BY person_name ASC;")
            db_persons = cursor.fetchall()
            conn.close()
            person_options = {row[0]: row[1] for row in db_persons}
        except Exception:
            person_options = {}

        st.markdown("**Advanced People Search**")
   
        f_person_id = st.multiselect("INCLUDE these people:", options=list(person_options.keys()), format_func=lambda x: person_options[x], on_change=reset_map_and_search_flags, key="ms_person_inc")
        raw_person_op = st.radio("Include:", options=["OR (Inscriptions mentioning any of these people)", "AND (Inscriptions mentioning all of them together)"], horizontal=True, index=0, key="rad_person_op", on_change=reset_map_and_search_flags)
        f_person_operator = "AND" if "AND" in raw_person_op else "OR"
             
        f_person_exclude = st.multiselect("EXCLUDE these people:", options=list(person_options.keys()), format_func=lambda x: person_options[x], on_change=reset_map_and_search_flags, key="ms_person_exc")
        raw_person_exc_op = st.radio("Exclude:", options=["OR (Inscriptions mentioning any of these people)", "AND (Inscriptions mentioning all of them together)"], horizontal=True, index=0, key="rad_person_exc_op", on_change=reset_map_and_search_flags)
        f_person_exclude_operator = "AND" if "AND" in raw_person_exc_op else "OR"
             
        st.write("---")
        # --- INSTITUTIONS / GROUPS ---
        f_unit = st.multiselect("Institution/Group/Military Unit:", [opt for opt in get_filter_options("collectives", "collective_name") if opt != "All"], on_change=reset_map_and_search_flags)
        f_unit_operator = st.radio("Find inscriptions mentioning:", options=["OR (Any of them)", "AND (All of them together)"], horizontal=True, index=0, key="rad_collective_op", on_change=reset_map_and_search_flags)
        
        f_vir_dist = st.multiselect("Distributio Virorum | Type of People Mentioned:", [opt for opt in get_filter_options("virorum_distributio", "virorum_distributio") if opt != "All"], on_change=reset_map_and_search_flags)
        f_status = st.multiselect("Attested Status Title", [opt for opt in get_filter_options("status_designations", "status_designation") if opt != "All"], on_change=reset_map_and_search_flags)
        f_pos = st.multiselect("Attested Office/Military Role:", [opt for opt in get_filter_options("positions", "position_description") if opt != "All"], on_change=reset_map_and_search_flags)

    # COLUMN 3: Later Modifications / Reuse
    with col3:
        st.markdown("##### Based on Later Modifications / Reuse")
        
        intervention_options = [
            "All inscriptions regardless of presence of later intervention",
            "Intervention present",
            "No later intervention"
        ]
        
        f_inter_status = st.selectbox("Intervention Status:", intervention_options, on_change=reset_map_and_search_flags)
        
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
        
        intervention_scope = None if is_scope_disabled else f_intervention_scope_raw

        f_interv_meth = st.multiselect("Method of Intervention:", [opt for opt in get_filter_options("methods", "method_description") if opt != "All"], on_change=reset_map_and_search_flags)
        f_interv_ext = st.multiselect("Extent of Intervention:", [opt for opt in get_filter_options("extent", "extent_description") if opt != "All"], on_change=reset_map_and_search_flags)
        f_interv_tgt = st.multiselect("Target of Intervention:", [opt for opt in get_filter_options("targets", "target_description") if opt != "All"], on_change=reset_map_and_search_flags)
    
    st.write("---")
    
    col_btn1, col_btn2 = st.columns([1, 1])

    with col_btn1:
        form_payload = {
            "text": f_text,
            "adv_text_search_mode": text_search_mode,
            "relevance_index": (
                "All"
                if f_rel == "All inscriptions regardless of relevance"
                else 1
                if f_rel == "Relevant"
                else 0
            ),
            "relevance_active": (
                False
                if f_rel == "All inscriptions regardless of relevance"
                else True
            ),
            "distributio_titulorum": f_dist_tit,
            "material_name": f_obj_mat,
            "support_name": f_sup_name,
            "context_name": f_in_con,
            "province_name": f_prov,
            "place_name": f_in_place,
            "number_of_inscriptions": f_num_ins,
            
            # --- PERSON INCLUSION ---
            "person_id": f_person_id,
            "person_operator": f_person_operator, 
            
            # --- PERSON EXCLUSION ---
            "person_exclude": f_person_exclude,
            "person_exclude_operator": f_person_exclude_operator, 
            
            "collective_name": f_unit,
            "collective_operator": "AND" if "AND" in f_unit_operator else "OR",
            "virorum_distributio": f_vir_dist,
            "status_designation": f_status,
            "position_description": f_pos,
            "intervention_status": (
                "All"
                if f_inter_status
                == "All inscriptions regardless of presence of later intervention"
                else 1
                if f_inter_status == "Intervention present"
                else 0
            ),
            "intervention_status_active": (
                False
                if f_inter_status
                == "All inscriptions regardless of presence of later intervention"
                else True
            ),
            "intervention_toggle": intervention_scope,
            "method_description": f_interv_meth,
            "extent_description": f_interv_ext,
            "target_description": f_interv_tgt,
            "status_tituli_name": f_status_tituli,
            "start_date": f_start_date,
            "end_date": f_end_date,
            "dating_strategy": f_dating_strategy,
        }

        st.button(
            "Execute Advanced Search",
            key="btn_advanced_filter_search",
            use_container_width=True,
            type="primary",
            on_click=callback_advanced_search,
            args=(form_payload,),
        )
             
    with col_btn2:
        if st.session_state.get("active_search_has_run"):
            dynamic_sql_query = generate_sql_query_from_filters()
                 
            sql_clicked = st.download_button(
                label="Download Filters as SQL Query",
                data=dynamic_sql_query,
                file_name="search_results_compiled_query.sql",
                mime="text/plain",
                use_container_width=True,
                key="btn_download_raw_sql_query"
            )
            
           # st.info(
              #  "Note: This query will not reflect your text input if you combined a text search with filters."
          #  )
                 
            if sql_clicked:
                st.session_state["skip_scroll"] = True
                st.rerun()
        else:
            st.button(
                label="Download Filters as SQL Query",
                key="btn_advanced_sql_disabled",
                use_container_width=True,
                disabled=True,
                help="Make a search first to unlock SQL query generation."
            )
                 
# SEARCH BY BIBLIOGRAPHY / LITERATURE SEARCH

with st.expander("Search by Bibliography / Literature Search", expanded=False):
    if "lit_matches" not in st.session_state:
        st.session_state.lit_matches = []
    if "lit_search_type" not in st.session_state:
        st.session_state.lit_search_type = None

    col1, col2 = st.columns(2)
    
    with col1:
        abbr_input = st.text_input(
            "Search by Abbreviated Citation",
            value="",
            key="lit_abbr_input"
        )
        st.markdown("Please use [EDCS style](https://edcs.hist.uzh.ch/sources) abbreviations e.g. CIL-02, 04886")
        
    with col2:
        author_input = st.text_input(
            "Search by Author / Work / Full Citation",
            value="",
            key="lit_name_or_full_citation_input"
        )

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
                    
                    def build_multi_word_query(search_text):
                        words = [w.strip() for w in search_text.split() if w.strip()]
                        if not words:
                            return None, []
                        
                        conditions = []
                        params = []
                        for word in words:
                            cleaned_upper = word.upper().replace('.', '').replace(',', '')
                            if cleaned_upper == "ILS" or cleaned_upper == "DESSAU":
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

                    query1, params1 = build_multi_word_query(raw_input)
                    if query1:
                        cursor.execute(query1, params1)
                        results = cursor.fetchall()
                    else:
                        results = []
                    
                    if not results and query1:
                        looser_query = query1.replace(" WHERE ", " WHERE ").replace(" AND ", " OR ")
                        cursor.execute(looser_query, params1)
                        results = cursor.fetchall()
                    
                    if not results:
                        converted_input = convert_roman_to_arabic_in_text(raw_input)
                        if converted_input != raw_input:
                            query2, params2 = build_multi_word_query(converted_input)
                            if query2:
                                cursor.execute(query2, params2)
                                results = cursor.fetchall()
                                
                                if not results:
                                    looser_query2 = query2.replace(" AND ", " OR ")
                                    cursor.execute(looser_query2, params2)
                                    results = cursor.fetchall()
                            
                    st.session_state.lit_matches = results
                    st.session_state.lit_search_type = "right"
                    conn.close()
                except Exception as e:
                    st.error(f"Database query error: {e}")
                         
    if st.session_state.lit_matches:
        st.markdown("---")
        res_col1, res_col2 = st.columns(2)
        
        st.session_state.lit_display_map = {}
        for uc_id, exp_cit in st.session_state.lit_matches:
            if exp_cit:
                unique_key = f"{exp_cit.strip()} (Ref ID: {uc_id})"
                st.session_state.lit_display_map[unique_key] = uc_id

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
 
            st.button(
                "Show Linked Inscriptions", 
                key="lit_action_execute", 
                disabled=is_disabled, 
                on_click=callback_literature_search
            )
                    
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
            global_csv_string = export_results_to_csv(cursor)
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
                st.session_state["last_mapped_search"] = {
                    "where": st.session_state.get("active_search_where_clauses", []),
                    "params": st.session_state.get("active_search_query_params", {}),
                    "ids_count": 0
                }
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT place_id FROM "places" WHERE "longitude" IS NULL;')
                    unmappable_place_ids = {row[0] for row in cursor.fetchall()}
                    
                    placeholders = ",".join("?" for _ in active_ids)
                    
                    query = f"""
                        SELECT m.inscription_id, m.inscription_ref, m.line_ref, m.place_id, p.province_name
                        FROM Max_Thrax m
                        LEFT JOIN provinces p ON m.province_id = p.province_id
                        WHERE m.inscription_id IN ({placeholders})
                    """
                    cursor.execute(query, tuple(active_ids))
                    all_rows = cursor.fetchall()
                    conn.close()
                    
                    unmappable_rows = [r for r in all_rows if r[3] in unmappable_place_ids]
                    valid_rows_count = len(all_rows) - len(unmappable_rows)
                    
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
            use_container_width=True, disabled=True, help="Make a search before exporting ."
        )
    with col_exp_mid:
        st.button(
            label="Generate Map", key="global_map_disabled_footer_map",
            use_container_width=True, disabled=True, help="Make a search before mapping ."
        )

# --- AUTOMATIC SEARCH COMMIT DETECTOR ---
current_search_fingerprint = {
    "where": st.session_state.get("active_search_where_clauses", []),
    "params": st.session_state.get("active_search_query_params", {}),
    "ids_count": len(st.session_state.get("active_inscription_ids", [])) if st.session_state.get("active_inscription_ids") else 0
}

if (
    st.session_state.get("last_mapped_search") is not None 
    and st.session_state.get("last_mapped_search") != current_search_fingerprint
):
    st.session_state["map_status"] = None
    st.session_state["trigger_map_html"] = None
    st.session_state["unmappable_html_notice"] = None


# SCROLL TO SEARCH RESULTS OR MAP
import time
cache_breaker = str(time.time())

if st.session_state.get("trigger_map_scroll"):
    st.session_state["trigger_map_scroll"] = False
    st.markdown('<div id="map-anchor"></div>', unsafe_allow_html=True)
    st.components.v1.html(
        f"""
        <script>
            function executeMapScroll() {{
                var target = window.parent.document.getElementById('map-anchor');
                if (target) {{
                    target.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                }} else {{
                    setTimeout(executeMapScroll, 50);
                }}
            }}
            window.addEventListener('load', executeMapScroll);
            setTimeout(executeMapScroll, 100);
        </script>
        """,
        height=0,
    )
    st.session_state["skip_scroll"] = True

elif st.session_state.get("active_search_has_run") and not st.session_state.get("skip_scroll", False):
    st.components.v1.html(
        f"""
        <script>
            // Cache breaker pass: {cache_breaker}
            var attempts = 0;
            var maxAttempts = 60; // 60 attempts * 50ms = 3 full seconds of waiting power

            function executeResultsScroll() {{
                var target = window.parent.document.getElementById('results-anchor');
                
                if (target) {{
                    // Anchor found! Wait for the paint engine to settle, then scroll smoothly
                    window.parent.requestAnimationFrame(function() {{
                        target.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                    }});
                }} else if (attempts < maxAttempts) {{
                    // Not ready yet. Increment counter, wait 50ms, and hunt again
                    attempts++;
                    setTimeout(executeResultsScroll, 50);
                }}
            }}
            
            // Start the radar hunt immediately when the component initializes
            executeResultsScroll();
        </script>
        """,
        height=0,
    )
    # Lock the scroll after it runs once, until commit_search_and_wipe_inputs drops it back to False!
    st.session_state["skip_scroll"] = True

is_map_open = st.session_state.get("map_expander_open", True)
current_version = st.session_state.get("map_version", 0)
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
            

        st.download_button(
            label="Download Map as HTML",
            data=st.session_state.trigger_map_html,
            file_name="maximinus_thrax_database_search_results_map.html",
            mime="text/html",
            key=f"download_map_html_v{current_version}"
        )
        
        st.components.v1.html(st.session_state.trigger_map_html, height=720, scrolling=True)
        
    else:
        st.info("No map generated yet. Make a search and click 'Generate Map' to plot inscriptions matching your query on a map.")

st.markdown('<div id="results-anchor" style="position: relative; top: -40px;"></div>', unsafe_allow_html=True)
# SEARCH RESULTS
st.markdown("### Search Results")

if not st.session_state.get("active_search_has_run"):
    st.info("Please make a search!")
         
# RESULTS LIST VIEW
if st.session_state.get("active_search_has_run") and st.session_state.get("active_inscription_ids"):
    
    if "list_view_expanded" not in st.session_state:
        st.session_state["list_view_expanded"] = True
        
    if "show_comma_list" not in st.session_state:
        st.session_state["show_comma_list"] = False

    matched_ids = st.session_state.active_inscription_ids
    
    try:
        conn_overview = get_db_connection()
        cursor_overview = conn_overview.cursor()
        
        placeholders = ",".join(["?"] * len(matched_ids))
        
        overview_sql = f"""
        SELECT 
            mt.inscription_id,
            mt.object_id,
            mt.inscription_ref,
            COALESCE(mt.line_ref, '') AS line_ref,
            COALESCE(pr.province_name, 'N/A') AS province_name,
            COALESCE(dt.distributio_titulorum, 'N/A') AS type_of_inscription,
            COALESCE(mt.dating, 'N/A') AS dating,
            CASE 
                WHEN mt.relevance_index = 1 
                     AND EXISTS (SELECT 1 FROM "interventions" i WHERE i.patient_inscription = mt.inscription_id AND i.method_id = 2)
                     AND mt.inscription_id NOT IN (SELECT ip.inscription_id FROM "inscriptions_and_persons" ip WHERE ip.person_id = 50)
                THEN '**Erasure relevant to Maximinus Thrax**'
                
                WHEN (mt.relevance_index = 1 
                      AND EXISTS (SELECT 1 FROM "interventions" i WHERE i.patient_inscription = mt.inscription_id AND i.method_id = 2)
                      AND mt.inscription_id IN (SELECT ip.inscription_id FROM "inscriptions_and_persons" ip WHERE ip.person_id = 50))
                     OR 
                     (mt.relevance_index = 0 
                      AND EXISTS (SELECT 1 FROM "interventions" i WHERE i.patient_inscription = mt.inscription_id AND i.method_id = 2))
                THEN '**Erasure not relevant to Maximinus Thrax**'
                
                ELSE '**No Erasure**'
            END AS erasure_status
        FROM "Max_Thrax" mt
        LEFT JOIN "provinces" pr ON mt.province_id = pr.province_id
        LEFT JOIN "distributio_titulorum" dt ON mt.distributio_titulorum_id = dt.distributio_titulorum_id
        WHERE mt.inscription_id IN ({placeholders})
        ORDER BY mt.object_id ASC;
        """
        
        cursor_overview.execute(overview_sql, [int(x) for x in matched_ids])
        overview_rows = cursor_overview.fetchall()
        
        conn_overview.close()

        with st.expander("Search Results List View", expanded=st.session_state["list_view_expanded"]):
            st.markdown(f"**Found {len(overview_rows)} record(s) matching your search:**")
            
            # Using standard native Streamlit height scroll container
            with st.container(height=200):
                for row in overview_rows:
                    ins_id, obj_id, ins_ref, line_ref, prov_name, type_of_inscription, dating_val, erasure_status = row
                    
                    ref_line = f" {line_ref}" if line_ref else ""
                    
                    app_url = f"https://maximinusthraxdatabaseui.streamlit.app/?ins_id={ins_id}"
                    obj_url = f"https://maximinusthraxdatabaseui.streamlit.app/?obj_id={obj_id}"
                    obj_display = f"[{obj_id}]({obj_url})" if obj_id is not None else "N/A"
                    
                    st.markdown(
                        f"* [Ins. ID: {ins_id}]({app_url}) | "
                        f"**Reference:** {ins_ref}{ref_line} | "
                        f"**Object ID:** {obj_display} | "
                        f"**Province:** {prov_name} | "
                        f"**Type of Inscription:** {type_of_inscription} | "
                        f"**Dating:** {dating_val} | "
                        f"*{erasure_status}*"
                    )
            
            st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
            
            # Toggle Button logic to open or close the secondary container
            if st.button(
                "Show inscription ID's as a comma separated list" if not st.session_state["show_comma_list"] else "Hide comma separated list", 
                use_container_width=True, 
                key="btn_toggle_comma_container"
            ):
                st.session_state["show_comma_list"] = not st.session_state["show_comma_list"]
                st.rerun()
                
            # Secondary dynamic sub-container that prints the formatted list within parentheses
            if st.session_state["show_comma_list"]:
                with st.container(border=True):
                    comma_separated_ids = ", ".join(str(x) for x in sorted(list(set(matched_ids))))
                    parenthesized_list = f"({comma_separated_ids})"
                    
                    st.caption("Inscription ID list formatted for SQL IN clauses:")
                    st.code(parenthesized_list, language="text")
                
    except Exception as overview_error:
        st.warning(f"Could not render the List View container: {overview_error}")
             
# MAIN RESULTS VIEW

if st.session_state.get("active_search_has_run"):
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
    import time
    cache_breaker = str(time.time())
    
    st.components.v1.html(
        f"""
        <script>
            // Cache breaker pass: {cache_breaker}
            function executeScroll() {{
                // Target the existing results anchor placed right above the results block
                var target = window.parent.document.getElementById('results-anchor');
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }} else {{
                    setTimeout(executeScroll, 50);
                }}
            }}
            window.addEventListener('load', executeScroll);
            setTimeout(executeScroll, 100);
        </script>
        """,
        height=0
    )

st.write("---") 

st.markdown(
    """
    <div style="text-align: center; color: #475569; font-size: 14px; margin-bottom: 15px; padding: 0 20px; line-height: 1.5;">
        <strong>Open Access Dataset</strong><br>
        This dataset combines data generated by my original research and data from open-access digital resources. 
        The dataset is free to download, use, and redistribute, under a <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" style="color: #1a53ff; text-decoration: none; font-weight: 600;">Creative Commons Attribution 4.0 International License (CC BY 4.0)</a>.
        However, please remember this is an UNREVIEWED dataset produced by an undergraduate student to the best of their ability. I do not guarantee it is infallible and I assume no liabilities for any damages resulting from the use of this dataset.
    </div>
    """, 
    unsafe_allow_html=True
)

st.link_button(
    label="Download the Dataset (as an SQLite database)",
    url="https://github.com/JiatongWangAlex/Maximinus_Thrax_Database_Explorer_Streamlit_v2/raw/refs/heads/main/maximinus_thrax.db", 
    help="Click to download the database file directly from GitHub",
    use_container_width=True 
)

# TODO: when thesis is ready
# st.link_button(
#     label="Download the Full Thesis (PDF)",
#     url="https://github.com/YOUR_USERNAME/YOUR_REPO/raw/main/your_thesis_filename.pdf", 
#     help="Click to download the full BA thesis PDF directly from GitHub",
#     use_container_width=True 
# )

import streamlit as st

with st.popover("Cite this Project"):
    st.markdown("**Chicago:**")
    st.code(
        'Wang, J. "Memory Sanctions against Maximinus Thrax." Supplemental website/database. '
        'BA thesis, Università degli Studi di Roma "La Sapienza", 2026. https://maximinusthraxdatabaseui.streamlit.app/.',
        language="text"
    )
    
    st.markdown("**APA:**")
    st.code(
        'Wang, J. (2026). Memory Sanctions against Maximinus Thrax [Undergraduate thesis, '
        'Università degli Studi di Roma "La Sapienza"]. Supplemental website/database. '
        'https://maximinusthraxdatabaseui.streamlit.app/.',
        language="text"
    )
    
    st.markdown("**MLA:**")
    st.code(
        'Wang, J. Memory Sanctions against Maximinus Thrax. 2026. Università degli Studi di Roma '
        '"La Sapienza", BA thesis. Supplemental website/database, '
        'maximinusthraxdatabaseui.streamlit.app/.',
        language="text"
    )
