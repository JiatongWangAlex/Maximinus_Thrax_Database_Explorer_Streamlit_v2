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


if "inputs_are_dirty" not in st.session_state:
    st.session_state["inputs_are_dirty"] = False
if "active_search_has_run" not in st.session_state:
    st.session_state["active_search_has_run"] = False
if "active_search_where_clauses" not in st.session_state:
    st.session_state["active_search_where_clauses"] = []
if "active_search_query_params" not in st.session_state:
    st.session_state["active_search_query_params"] = {}


st.set_page_config(page_title="Maximinus Thrax Database Explorer", layout="wide")

# This calculates the folder your app is running out of (both on your PC and on GitHub)
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
db_path = os.path.join(BASE_DIR, "version_58.db")

# Path configs for your GitHub repository files
optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
provinces_json_path = os.path.join(BASE_DIR, "roman_provinces.json") 


def reset_map_and_search_flags():
    """Hides the generate map button and clears the map frame immediately when a filter changes."""
    st.session_state["active_search_has_run"] = False
    st.session_state["trigger_map_html"] = None


def generate_bulk_search_csv(cursor):
    """Generates a multi-row CSV text string matching all current search filters safely without using external variables."""
    import io
    import csv
    
    where_str = ""
    params = {}
    
    # Check exactly which search type ran LAST
    current_mode = st.session_state.get("csv_mode", "ids")
    
    if current_mode == "advanced" and st.session_state.get("active_search_where_clauses"):
        clauses = st.session_state.get("active_search_where_clauses", [])
        params = st.session_state.get("active_search_query_params", {})
        if clauses:
            where_str = " AND " + " AND ".join(clauses)
    else:
        # Fallback for Text, Person, Ref, and ID searches
        active_ids = st.session_state.get("active_inscription_ids", [])
        if active_ids:
            id_string = ", ".join(map(str, active_ids))
            where_str = f" AND mt.inscription_id IN ({id_string})"

    robust_export_query = f"""
        SELECT DISTINCT
            mt.inscription_id,
            mt.inscription_ref,
            mt.line_ref,
            COALESCE((SELECT GROUP_CONCAT(itm.TM_number, ', ') FROM "inscriptions_and_TM_numbers" itm WHERE itm.inscription_id = mt.inscription_id), 'N/A') AS tm_links,
            mt.inscription_text,
            COALESCE(mt.corrected_lemmas, 'N/A'),
            COALESCE(ct.context_name, 'N/A'),
            COALESCE(s.support_name, 'N/A'),
            COALESCE(mt.dating, 'N/A'),
            COALESCE(m.material_name, 'N/A'),
            COALESCE(st.status_tituli_name, 'N/A'),
            COALESCE(
                (
                    SELECT GROUP_CONCAT(distinct_vd, ', ') FROM (
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_persons" ip_sub
                        JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                        JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                        WHERE ip_sub.inscription_id = mt.inscription_id
                        
                        UNION
                        
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_collectives" ic_sub
                        JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                        JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                        WHERE ic_sub.inscription_id = mt.inscription_id
                    )
                ), 
                'N/A'
            ) AS virorum_distributio,
            (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') 
             FROM persons p JOIN inscriptions_and_persons ip ON p.person_id = ip.person_id 
             WHERE ip.inscription_id = mt.inscription_id) AS linked_persons,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(c.collective_name, ', ')
                    FROM "collectives" c
                    JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
                    WHERE ic.inscription_id = mt.inscription_id
                ),
                'N/A'
            ) AS linked_collectives,
            COALESCE(pr.province_name, 'N/A'),
            COALESCE((SELECT pl.place_name FROM "places" pl WHERE pl.place_id = mt.place_id), 'N/A') AS place_name,
            COALESCE((SELECT r_roads.road_name FROM "inscription_and_road" iar JOIN "itiner_e_roads" r_roads ON iar.itiner_e_road_id = r_roads.itiner_e_road_id WHERE iar.inscription_id = mt.inscription_id), 'N/A') AS road_name,
            COALESCE(o.number_of_inscriptions, 0) AS num_inscriptions,
            (
                SELECT GROUP_CONCAT(mt_sub.sequence_id || '. ' || mt_sub.inscription_ref || CASE WHEN mt_sub.line_ref IS NOT NULL AND mt_sub.line_ref <> '' THEN ' ' || mt_sub.line_ref ELSE '' END || ' (id: ' || mt_sub.inscription_id || ')', '; ')
                FROM "Max_Thrax" mt_sub
                WHERE mt_sub.object_id = mt.object_id
                ORDER BY mt_sub.sequence_id ASC
            ) AS inscriptions_list,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(
                        'intervention ' || idx || ' : ' || CASE WHEN iam.method_id = 2 THEN COALESCE(e2.extent_description, '') || ' ' || COALESCE(m2.method_description, '') || ' of inscription' WHEN iam.method_id = 3 THEN 'reuse of monument ' || COALESCE(i.note, '') WHEN iam.method_id = 4 THEN 'monument damage ' || COALESCE(i.note, '') ELSE '' END, '; '
                    )
                    FROM (SELECT intervention_id, note, row_number() over (order by intervention_id) as idx, inscription_id, role_id FROM "interventions_and_inscriptions") i
                    JOIN "interventions" iam ON i.intervention_id = iam.intervention_id
                    LEFT JOIN "extent" e2 ON iam.extent_id = e2.extent_id
                    LEFT JOIN "methods" m2 ON iam.method_id = m2.method_id
                    WHERE i.inscription_id = mt.inscription_id AND i.role_id = 1 AND iam.method_id <> 1
                ),
                'no interventions'
            ) AS interventions,
            COALESCE(mt.expanded_bibliography, 'N/A')
        FROM "Max_Thrax" mt
        LEFT JOIN "materials" m ON mt.material_id = m.material_id
        LEFT JOIN "support" s ON mt.support_id = s.support_id
        LEFT JOIN "context_types" ct ON mt.context_id = ct.context_id
        LEFT JOIN "provinces" pr ON mt.province_id = pr.province_id
        LEFT JOIN "objects" o ON mt.object_id = o.object_id
        LEFT JOIN "inscriptions_and_persons" ip_f ON mt.inscription_id = ip_f.inscription_id
        LEFT JOIN "collectives" col ON mt.inscription_id = col.collective_id
        LEFT JOIN "status_tituli" st ON mt.status_tituli_id = st.status_tituli_id
        WHERE 1=1 {where_str}
        ORDER BY mt.inscription_id DESC
    """
    
    cursor.execute(robust_export_query, params)
    rows = cursor.fetchall()
    
    if not rows:
        return "No matching search results found to export."

    headers = [
        "Inscription ID", "Quick Citation", "Line Citation", "Trismegistos Number", 
        "Inscription Text", "Nonstandard Spellings", "Context", "Support", 
        "Dating", "Material", "Status Tituli", 
        "Virorum Distributio",  # Added
        "Persons", 
        "Institutions / Groups / Military Units",  # Added
        "Province", "Place", "Associated Roman Road", "Number of Inscriptions on Object", 
        "Inscriptions on Object", "Interventions(Later modifications/reuse)", "Bibliography"
    ]
    
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    
    for row in rows:
        writer.writerow(list(row))
            
    return csv_buffer.getvalue()

def generate_bulk_search_sql():
    """Generates a comprehensive, runnable raw SQL script matching active search parameters down to the column."""
    where_str = ""
    
    current_mode = st.session_state.get("csv_mode", "ids")
    
    if current_mode == "advanced" and st.session_state.get("active_search_where_clauses"):
        clauses = st.session_state.get("active_search_where_clauses", [])
        params = st.session_state.get("active_search_query_params", {})
        
        processed_clauses = []
        for c in clauses:
            for k, v in params.items():
                target_placeholder = f":{k}"
                if target_placeholder in c:
                    c = c.replace(target_placeholder, f"'{v}'" if isinstance(v, str) else str(v))
            processed_clauses.append(c)
            
        if processed_clauses:
            where_str = " AND " + " AND ".join(processed_clauses)
    else:
        active_ids = st.session_state.get("active_inscription_ids", [])
        if active_ids:
            id_string = ", ".join(map(str, active_ids))
            where_str = f" AND mt.inscription_id IN ({id_string})"

    return f"""-- Copy and execute this query directly in your database platform to verify results
SELECT DISTINCT
    mt.inscription_id AS [Inscription ID],
    mt.inscription_ref AS [Quick Citation],
    mt.line_ref AS [Line Citation],
    COALESCE((SELECT GROUP_CONCAT(itm.TM_number, ', ') FROM "inscriptions_and_TM_numbers" itm WHERE itm.inscription_id = mt.inscription_id), 'N/A') AS [Trismegistos Number],
    mt.inscription_text AS [Inscription Text],
    COALESCE(mt.corrected_lemmas, 'N/A') AS [Nonstandard Spellings],
    COALESCE(ct.context_name, 'N/A') AS [Context],
    COALESCE(s.support_name, 'N/A') AS [Support],
    COALESCE(mt.dating, 'N/A') AS [Dating],
    COALESCE(m.material_name, 'N/A') AS [Material],
    COALESCE(st.status_tituli_name, 'N/A') AS [Status Tituli],
    COALESCE(
        (
            SELECT GROUP_CONCAT(distinct_vd, ', ') FROM (
                SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                FROM "inscriptions_and_persons" ip_sub
                JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                WHERE ip_sub.inscription_id = mt.inscription_id
                
                UNION
                
                SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                FROM "inscriptions_and_collectives" ic_sub
                JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                WHERE ic_sub.inscription_id = mt.inscription_id
            )
        ), 
        'N/A'
    ) AS [Virorum Distributio],
    (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') 
     FROM persons p JOIN inscriptions_and_persons ip ON p.person_id = ip.person_id 
     WHERE ip.inscription_id = mt.inscription_id) AS [Persons],
    COALESCE(
        (
            SELECT GROUP_CONCAT(c.collective_name, ', ')
            FROM "collectives" c
            JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
            WHERE ic.inscription_id = mt.inscription_id
        ),
        'N/A'
    ) AS [Institutions / Groups / Military Units],
    COALESCE(pr.province_name, 'N/A') AS [Province],
    COALESCE((SELECT pl.place_name FROM "places" pl WHERE pl.place_id = mt.place_id), 'N/A') AS [Place],
    COALESCE((SELECT r_roads.road_name FROM "inscription_and_road" iar JOIN "itiner_e_roads" r_roads ON iar.itiner_e_road_id = r_roads.itiner_e_road_id WHERE iar.inscription_id = mt.inscription_id), 'N/A') AS [Associated Roman Road],
    mt.object_id AS [Object ID],
    COALESCE(o.number_of_inscriptions, 0) AS [Number of Inscriptions on Object],
    COALESCE(
        (SELECT GROUP_CONCAT(mt_sub.inscription_id, ', ') 
         FROM "Max_Thrax" mt_sub 
         WHERE mt_sub.object_id = mt.object_id AND mt_sub.inscription_id <> mt.inscription_id), 
        'None'
    ) AS [Other Inscriptions on the same Object],
    COALESCE(
        (SELECT GROUP_CONCAT(i.intervention_id, ', ') 
         FROM "interventions_and_inscriptions" i 
         WHERE i.inscription_id = mt.inscription_id AND i.role_id = 1), 
        'None'
    ) AS [Linked Intervention IDs],
    COALESCE(mt.expanded_bibliography, 'N/A') AS [Bibliography]
FROM "Max_Thrax" mt
LEFT JOIN "materials" m ON mt.material_id = m.material_id
LEFT JOIN "support" s ON mt.support_id = s.support_id
LEFT JOIN "context_types" ct ON mt.context_id = ct.context_id
LEFT JOIN "provinces" pr ON mt.province_id = pr.province_id
LEFT JOIN "objects" o ON mt.object_id = o.object_id
LEFT JOIN "inscriptions_and_persons" ip_f ON mt.inscription_id = ip_f.inscription_id
LEFT JOIN "status_tituli" st ON mt.status_tituli_id = st.status_tituli_id
LEFT JOIN "distributio_titulorum" dt ON mt.distributio_titulorum_id = dt.distributio_titulorum_id
WHERE 1=1 {where_str}
ORDER BY mt.inscription_id DESC;"""


def get_db_connection():
    if not os.path.exists(db_path):
        st.error(f"Missing database file! Please place 'version_58.db' in: {BASE_DIR}")
        st.stop()
    return sqlite3.connect(db_path)
# =========================================================
# LATIN LEMMATIZATION / STEMMING DICTIONARY
# =========================================================
LATIN_LEMMA_MAP = {
    "praesidem": "praeses", "praesidis": "praeses", "praesidi": "praeses", "praeside": "praeses",
    "praefectum": "praefectus", "praefecti": "praefectus", "praefecto": "praefectus",
    "tribunum": "tribunus", "tribuni": "tribunus", "tribuno": "tribunus", 
    "legatum": "legatus", "legati": "legatus", "legato": "legatus",
    "speculatorem": "speculator", "speculatoris": "speculator", "speculatori": "speculator", "speculatore": "speculator",
    "veteranum": "veteranus", "veterani": "veteranus", "veterano": "veteranus",
    "quaestorem": "quaestor", "quaestoris": "quaestor", "quaestori": "quaestor", "quaestore": "quaestor",
    "procuratorem": "procurator", "procuratoris": "procurator", "procuratori": "procurator", "procuratore": "procurator",
    "imperatorem": "imperator", "imperatoris": "imperator", "imperatori": "imperator", "imperatore": "imperator",
    "consulem": "consul", "consulis": "consul", "consuli": "consul", "consule": "consul",
    "centurionem": "centurio", "centurionis": "centurio", "centurioni": "centurio", "centurione": "centurio",
    "augustum": "augustus", "augusti": "augustus", "augusto": "augustus",
    "caesarem": "caesar", "caesaris": "caesar", "caesari": "caesar", "caesare": "caesar",
    "immunem": "immunis", "immuni": "immunis", "immune": "immunis",
    "restituit": "restituo", "restituerunt": "restituo", "restituitque": "restituo", "restituo": "restituo",
    "cooptaverunt": "coopto", "cooptatus": "coopto", "cooptavit": "coopto", "cooptati": "coopto", "coopto": "coopto"
}


def convert_markdown_bold_to_edh(text):
    """Tracks asterisks across lines exactly like a Markdown parser,

    converting **text** into text(!), even if it straddles lines.
    """
    output = []
    i = 0
    n = len(text)
    in_bold = False

    while i < n:
        if i < n - 1 and text[i] == "*" and text[i + 1] == "*":
            if not in_bold:
                in_bold = True
            else:
                output.append("(!)")
                in_bold = False
            i += 2
        else:
            output.append(text[i])
            i += 1
    if in_bold:
        output.append("(!)")
    return "".join(output)


def lemmatize_query(text):
    if not text: return ""
    words = text.lower().split()
    return " ".join([LATIN_LEMMA_MAP.get(word, word) for word in words])

def clean_epigraphic_text(text):
    if not text: return ""
    text = text.lower()
    cleaned_text = re.sub(r'[\[\]\(\)\.\?\-\/\u0323⟦⟧〚〛\d!\{\}]', '', text)
    return re.sub(r'\s+', ' ', cleaned_text).strip()


def convert_roman_to_arabic_in_text(text):
    if not text: return ""
    roman_map = {
        'xxxv': '35', 'xxx4': '34', 'xxxiiii': '34', 'xxxiii': '33', 'xxxii': '32', 'xxxi': '31', 'xxx': '30',
        'xxix': '29', 'xxviiiii': '29', 'xxviii': '28', 'xxvii': '27', 'xxvi': '26', 'xxv': '25', 'xxiv': '24',
        'xxiiii': '24', 'xxiii': '23', 'xxii': '22', 'xxi': '21', 'xx': '20', 'xix': '19', 'viiiii': '19',
        'xviii': '18', 'xvii': '17', 'xvi': '16', 'xv': '15', 'xiv': '14', 'xiiii': '14', 'xiii': '13',
        'xii': '12', 'xi': '11', 'x': '10', 'ix': '9', 'viiii': '9', 'viii': '8', 'vii': '7', 'vi': '6',
        'v': '5', 'iv': '4', 'iiii': '4', 'iii': '3', 'ii': '2', 'i': '1'
    }
    words = text.split()
    converted_words = []
    for word in words:
        cleaned_word = re.sub(r'[^\w]', '', word).lower()
        if cleaned_word in roman_map:
            converted_words.append(word.lower().replace(cleaned_word, roman_map[cleaned_word]))
        else:
            converted_words.append(word)
    return " ".join(converted_words)

# Initialize Session Engine Parameters Safely
if 'active_inscription_ids' not in st.session_state:
    st.session_state.active_inscription_ids = []
if 'search_results' not in st.session_state:
    st.session_state.search_results = ""
if 'person_matches' not in st.session_state:
    st.session_state.person_matches = []
if 'trigger_map_html' not in st.session_state:
    st.session_state.trigger_map_html = None

# =========================================================
# SYSTEM SEARCH UTILITY ENGINES
# =========================================================
def run_standard_search(user_input):
    if not user_input.strip():
        st.session_state.search_results = "Please enter a search term."
        return

    converted_input = convert_roman_to_arabic_in_text(user_input)
    is_unit_query = bool(re.search(r'\b(legio|cohors|ala|numerus|classis)\b', user_input, re.IGNORECASE) and re.search(r'\d+|[ivxl]+', user_input, re.IGNORECASE))
    
    text_rows = []
    fallback_rows = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        sql = """
        WITH TargetInscription AS (SELECT ? AS selected_id),
        TargetObject AS (SELECT object_id AS selected_obj_id FROM "Max_Thrax" WHERE inscription_id = (SELECT selected_id FROM TargetInscription)),
        Metadata_Joined AS (
            SELECT mt.inscription_id, mt.inscription_ref, mt.line_ref, 
                   mt.inscription_text_formatted, mt.corrected_lemmas, mt.dating, mt.expanded_bibliography,
                   ct.context_name, s.support_name, m.material_name, pr.province_name, pl.place_name, pl.pleiades_id,
                   r_roads.road_name, r_roads.itinere_id,
                   st.status_tituli_name,
                   -- Subquery to pull and build comma-separated Markdown hyperlinks for all TM Numbers linked to this Inscription
                   COALESCE(
                       (SELECT GROUP_CONCAT('[' || itm.TM_number || '](https://www.trismegistos.org/text/' || itm.TM_number || ')', ', ')
                        FROM "inscriptions_and_TM_numbers" itm 
                        WHERE itm.inscription_id = mt.inscription_id), 
                       'N/A'
                   ) AS tm_hyperlinks
            FROM "Max_Thrax" mt CROSS JOIN TargetInscription
            LEFT JOIN "context_types" ct        ON mt.context_id = ct.context_id
            LEFT JOIN "support" s                ON mt.support_id = s.support_id
            LEFT JOIN "materials" m              ON mt.material_id = m.material_id
            LEFT JOIN "provinces" pr            ON mt.province_id = pr.province_id
            LEFT JOIN "places" pl                ON mt.place_id = pl.place_id
            LEFT JOIN "inscription_and_road" iar ON mt.inscription_id = iar.inscription_id
            LEFT JOIN "itiner_e_roads" r_roads  ON iar.itiner_e_road_id = r_roads.itiner_e_road_id
            LEFT JOIN "status_tituli" st         ON mt.status_tituli_id = st.status_tituli_id
            WHERE mt.inscription_id = TargetInscription.selected_id
        ),
        Sec0_Metadata AS (
            SELECT 0 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '**Quick Reference:** ' || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL THEN '[' || inscription_ref || '](https://edcs.hist.uzh.ch/en/search?edcs-id=' || inscription_ref || ')' 
                       ELSE '' 
                   END || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL AND line_ref IS NOT NULL THEN ' ' || line_ref
                       WHEN line_ref IS NOT NULL THEN line_ref
                       WHEN inscription_ref IS NULL AND line_ref IS NULL THEN 'N/A'
                       ELSE ''
                   END || 
                   ' | **TM Number:** ' || tm_hyperlinks ||
                   ' | **Inscription ID:** [' || inscription_id || '](?ins_id=' || inscription_id || ')' || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 3 AS inner_lo, '**Nonstandard Spellings:** ' || COALESCE(corrected_lemmas, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 4 AS inner_lo, '**Context:** ' || COALESCE(context_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 5 AS inner_lo, '**Support:** ' || COALESCE(support_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 6 AS inner_lo, '**Dating:** ' || COALESCE(dating, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7 AS inner_lo, '**Material:** ' || COALESCE(material_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.5 AS inner_lo, '**Status Tituli:** ' || COALESCE(status_tituli_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            
           
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.9 AS inner_lo, '**Distributio Virorum:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT(distinct_vd, ', ') FROM (
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_persons" ip_sub
                        JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                        JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                        WHERE ip_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                        
                        UNION
                        
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_collectives" ic_sub
                        JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                        JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                        WHERE ic_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                    )
                ), 
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            

            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription

            -- 3. INSTITUTIONS / GROUPS / MILITARY UNITS (Placed below Persons at inner_lo 8.1)
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8.1 AS inner_lo, '**Institutions / Groups / Military Units:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT('[' || c.collective_name || '](?collective_id=' || c.collective_id || ')', ', ')
                    FROM "collectives" c
                    JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
                    WHERE ic.inscription_id = (SELECT selected_id FROM TargetInscription)
                ),
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 9 AS inner_lo, '**Province:** ' || COALESCE(province_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 10 AS inner_lo, '**Place:** ' || CASE WHEN pleiades_id IS NOT NULL THEN '[' || place_name || '](https://pleiades.stoa.org/places/' || pleiades_id || ')' ELSE COALESCE(place_name, 'N/A') END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 11 AS inner_lo, '**Associated Roman Road (Itinere):** ' || CASE WHEN itinere_id IS NOT NULL THEN '[' || COALESCE(road_name, 'Unnamed Road') || '](https://itiner-e.org/?id=' || itinere_id || ')' ELSE 'N/A' END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 12 AS inner_lo, '**Bibliography:** ' || char(10) || '* ' || replace(COALESCE(expanded_bibliography, 'N/A'), char(10), char(10) || '* ') || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Header AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.5 AS inner_lo, '**Inscription Text:**' || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Body AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.6 AS inner_lo, 
                   CASE 
                       WHEN COALESCE(inscription_text_formatted, 'N/A') LIKE '-%' 
                       THEN '' 
                       ELSE '' 
                   END ||
                   replace(
                       replace(COALESCE(inscription_text_formatted, 'N/A'), char(10), '  ' || char(10)),
                       '  ' || char(10) || '-', 
                       '  ' || char(10) || '' || '-'
                   ) || '  ' || char(10) || char(10) AS tl 
            FROM Metadata_Joined
        ),
        Sec0_Spacer AS (SELECT 0 AS sg, 999999 AS seq_id, 1 AS inner_lo, '' AS tl),
        
        Sec1_Header AS (
            SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '#### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
        Sec1_List AS (
            SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, 
                   '* ' || mt.sequence_id || '. ' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        
        Sec2_Header AS (
            SELECT 2 AS sg, 0 AS seq_id, 0 AS inner_lo,
                   '#### Interventions (Later Modifications / Reuse)' || char(10) || char(10) AS tl
        ),
        
        Sec2_Summary AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, 
                   '**' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' :** ' || 
                   CASE 
                       WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 
                       THEN '_no interventions_' 
                       ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' intervention(s)' 
                   END || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
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
            FROM "interventions_and_inscriptions" i 
            JOIN "interventions" iam ON i.intervention_id = iam.intervention_id 
            LEFT JOIN "extent" e ON iam.extent_id = e.extent_id 
            LEFT JOIN "methods" m ON iam.method_id = m.method_id 
            JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id 
              AND i.role_id = 1 
              AND iam.method_id <> 1
        ),
        Sec2_Spacer AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 999998 AS inner_lo, char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        )
        SELECT tl FROM (
            SELECT sg, seq_id, inner_lo, tl FROM Sec0_Metadata 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Body 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_List 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Header
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Summary 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Intervention_Nested_Details 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Spacer
        ) ORDER BY sg ASC, seq_id ASC, inner_lo ASC;
        """
        if is_unit_query:
            search_terms = re.findall(r'\w+', converted_input.lower())
            cursor.execute("SELECT collective_id, collective_name_search FROM collectives;")
            all_collectives = cursor.fetchall()
            c_ids = [col_id for col_id, col_search in all_collectives if col_search and all(re.search(r'\b' + re.escape(term) + r'\b', col_search.lower()) for term in search_terms)]
            
            if c_ids:
                c_sql = f"""
                    SELECT mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
                    (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') FROM persons p JOIN inscriptions_and_persons ip ON p.person_id = ip.person_id WHERE ip.inscription_id = mt.inscription_id)
                    FROM "Max_Thrax" mt JOIN "inscriptions_and_collectives" ic ON mt.inscription_id = ic.inscription_id
                    WHERE ic.collective_id IN ({','.join(['?']*len(c_ids))});
                """
                cursor.execute(c_sql, c_ids)
                text_rows = cursor.fetchall()
        else:
            clean_query = clean_epigraphic_text(user_input).strip().lower()
            root_lemma = LATIN_LEMMA_MAP.get(clean_query, clean_query)
            synonyms = list(set([k for k, v in LATIN_LEMMA_MAP.items() if v == root_lemma] + [root_lemma, clean_query]))
            
            like_clauses = " OR ".join(["mt.inscription_text_stripped LIKE ?"] * len(synonyms))
            text_sql = f"""
                SELECT mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
                       (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = mt.inscription_id) AS linked_persons,
                       mt.inscription_text_stripped
                FROM "Max_Thrax" mt WHERE {like_clauses} ORDER BY mt.inscription_id DESC;
            """
            cursor.execute(text_sql, [f"%{syn}%" for syn in synonyms])
            for row in cursor.fetchall():
                ins_id, ins_text, ins_ref, line_ref, further_bib, linked_persons, text_stripped = row
                base_data = (ins_id, ins_text, ins_ref, line_ref, further_bib, linked_persons)
                if text_stripped and clean_query in text_stripped.lower():
                    text_rows.append(base_data)
                else:
                    fallback_rows.append(base_data + ("lemma_cluster", root_lemma))
            # =================================================================
            # NEW FALLBACK: Continuous Substring Search
            # Triggered ONLY if Phase 1 found nothing in text_rows or fallback_rows
            # =================================================================
            if not text_rows and not fallback_rows:
                # Lowercase, smash out ALL spaces, and strip out epigraphic brackets/punctuation
                continuous_term = user_input.lower().replace(" ", "")
                continuous_term = re.sub(r'[\[\]\(\)\.\?\-\/\u0323⟦⟧〚〛\d!\{\}<>´`\^~]', '', continuous_term)
                
                if continuous_term:
                    continuous_sql = """
                        SELECT mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
                               (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = mt.inscription_id) AS linked_persons
                        FROM "Max_Thrax" mt 
                        WHERE mt.reconstituted_text LIKE ? 
                           OR mt.cleaned_text LIKE ?
                        ORDER BY mt.inscription_id DESC;
                    """
                    cursor.execute(continuous_sql, (f"%{continuous_term}%", f"%{continuous_term}%"))
                    for row in cursor.fetchall():
                        ins_id, ins_text, ins_ref, line_ref, further_bib, linked_persons = row
                        text_rows.append((ins_id, ins_text, ins_ref, line_ref, further_bib, linked_persons))
            # =================================================================
            smart_meta_input = lemmatize_query(user_input.strip())
            like_query = f"%{re.sub(r'\s+', '%', smart_meta_input)}%"
            
            cursor.execute("SELECT person_id FROM persons WHERE person_name LIKE ?;", (like_query,))
            p_ids = [r[0] for r in cursor.fetchall()]
            if p_ids:
                p_sql = f"""SELECT mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
                           (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') FROM persons p JOIN inscriptions_and_persons ip ON p.person_id = ip.person_id WHERE ip.inscription_id = mt.inscription_id),
                           'person', 'Person names match' FROM "Max_Thrax" mt JOIN "inscriptions_and_persons" ip ON mt.inscription_id = ip.inscription_id WHERE ip.person_id IN ({','.join(['?']*len(p_ids))});"""
                cursor.execute(p_sql, p_ids)
                fallback_rows.extend(cursor.fetchall())
                
       
        
        seen_text_ids = {row[0] for row in text_rows}
        unique_fallback_rows = []
        seen_fallback_ids = set()
        search_clean = user_input.strip().lower()
        base_word = lemmatize_query(search_clean)
        
        for row in fallback_rows:
            ins_id = row[0]
            if ins_id not in seen_text_ids and ins_id not in seen_fallback_ids:
                if row[6] == "position" and (search_clean not in (row[1].lower() if row[1] else "")) and (base_word not in (row[1].lower() if row[1] else "")):
                    continue
                unique_fallback_rows.append(row)
                seen_fallback_ids.add(ins_id)
                
        st.session_state.active_inscription_ids = list(seen_text_ids.union(seen_fallback_ids))
        all_matched_ids = st.session_state.active_inscription_ids

        st.session_state["active_search_where_clauses"] = []  # Tells exporter: Mode 2 Active
        st.session_state["active_search_has_run"] = True      # Lights up the button
        
        if not all_matched_ids:
            st.session_state.search_results = f'No inscriptions found matching string "{user_input}"'
            conn.close()
            return
            
        # -----------------------------------------
        object_count = 0
        if all_matched_ids:
            obj_cursor = conn.cursor()
            chunk_size = 900
            unique_objects = set()
            
            # Split IDs into safe chunks to prevent SQLite parameter limits from crashing
            for i in range(0, len(all_matched_ids), chunk_size):
                chunk = all_matched_ids[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                
                obj_cursor.execute(
                    f'SELECT DISTINCT object_id FROM "Max_Thrax" WHERE inscription_id IN ({placeholders});', 
                    chunk
                )
                for row in obj_cursor.fetchall():
                    unique_objects.add(row[0])
            
            object_count = len(unique_objects)
        # -----------------------------------------
            
        out_str = []
        
        # 1. Create the header for the entire search results
        header = f"## Search Results\nFound {len(text_rows)} direct match(es) and {len(unique_fallback_rows)} indirect match(es)!\n"
        header += f"**Key Word:** {user_input}\n\n"
        header += f"Compiled dossiers for all **{len(all_matched_ids)}** matching inscriptions on **{object_count}** objects:\n\n"
        out_str.append(header)
        
        # 2. LOOP THROUGH EVERY SINGLE MATCHING ID AND STITCH THEM TOGETHER
        for rank, ins_id in enumerate(all_matched_ids, 1):
            out_str.append(f"## Result {rank}\n")
            
            # Execute the giant query uniquely for THIS inscription ID in the loop
            cursor.execute(sql, (int(ins_id),))
            card_rows = cursor.fetchall()
            
            if card_rows:
                # Join all the metadata rows for this specific card
                dossier_text = "\n".join([r[0] for r in card_rows if r[0] is not None])
                out_str.append(dossier_text)
            else:
                out_str.append(f"_Warning: Could not compile dossier data for ID: {ins_id}_")
                
            # Add a clear visual divider between separate inscription dossiers
            out_str.append("\n\n---\n\n")
            
        # 3. Stitch every single compiled card together into the final display state
        st.session_state.search_results = "\n\n".join(out_str)
        conn.close()
    except Exception as e:
        st.error(f"An unexpected database error occurred: {e}")
        
def run_ref_search(ref_query):
    if not ref_query.strip():
        st.session_state.search_results = "Please enter an Inscription Reference code."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Comprehensive query pulling all related metadata matching the Reference search string
        sql = """
        WITH TargetInscription AS (SELECT ? AS selected_id),
        TargetObject AS (SELECT object_id AS selected_obj_id FROM "Max_Thrax" WHERE inscription_id = (SELECT selected_id FROM TargetInscription)),
        Metadata_Joined AS (
            SELECT mt.inscription_id, mt.inscription_ref, mt.line_ref, 
                   mt.inscription_text_formatted, mt.corrected_lemmas, mt.dating, mt.expanded_bibliography,
                   ct.context_name, s.support_name, m.material_name, pr.province_name, pl.place_name, pl.pleiades_id,
                   r_roads.road_name, r_roads.itinere_id,
                   st.status_tituli_name,
                   -- Subquery to pull and build comma-separated Markdown hyperlinks for all TM Numbers linked to this Inscription
                   COALESCE(
                       (SELECT GROUP_CONCAT('[' || itm.TM_number || '](https://www.trismegistos.org/text/' || itm.TM_number || ')', ', ')
                        FROM "inscriptions_and_TM_numbers" itm 
                        WHERE itm.inscription_id = mt.inscription_id), 
                       'N/A'
                   ) AS tm_hyperlinks
            FROM "Max_Thrax" mt CROSS JOIN TargetInscription
            LEFT JOIN "context_types" ct        ON mt.context_id = ct.context_id
            LEFT JOIN "support" s                ON mt.support_id = s.support_id
            LEFT JOIN "materials" m              ON mt.material_id = m.material_id
            LEFT JOIN "provinces" pr            ON mt.province_id = pr.province_id
            LEFT JOIN "places" pl                ON mt.place_id = pl.place_id
            LEFT JOIN "inscription_and_road" iar ON mt.inscription_id = iar.inscription_id
            LEFT JOIN "itiner_e_roads" r_roads  ON iar.itiner_e_road_id = r_roads.itiner_e_road_id
            LEFT JOIN "status_tituli" st         ON mt.status_tituli_id = st.status_tituli_id
            WHERE mt.inscription_id = TargetInscription.selected_id
        ),
        Sec0_Metadata AS (
            SELECT 0 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '**Quick Reference:** ' || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL THEN '[' || inscription_ref || '](https://edcs.hist.uzh.ch/en/search?edcs-id=' || inscription_ref || ')' 
                       ELSE '' 
                   END || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL AND line_ref IS NOT NULL THEN ' ' || line_ref
                       WHEN line_ref IS NOT NULL THEN line_ref
                       WHEN inscription_ref IS NULL AND line_ref IS NULL THEN 'N/A'
                       ELSE ''
                   END || 
                   ' | **TM Number:** ' || tm_hyperlinks ||
                   ' | **Inscription ID:** [' || inscription_id || '](?ins_id=' || inscription_id || ')' || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 3 AS inner_lo, '**Nonstandard Spellings:** ' || COALESCE(corrected_lemmas, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 4 AS inner_lo, '**Context:** ' || COALESCE(context_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 5 AS inner_lo, '**Support:** ' || COALESCE(support_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 6 AS inner_lo, '**Dating:** ' || COALESCE(dating, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7 AS inner_lo, '**Material:** ' || COALESCE(material_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.5 AS inner_lo, '**Status Tituli:** ' || COALESCE(status_tituli_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined

            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.9 AS inner_lo, '**Distributio Virorum:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT(distinct_vd, ', ') FROM (
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_persons" ip_sub
                        JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                        JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                        WHERE ip_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                        
                        UNION
                        
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_collectives" ic_sub
                        JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                        JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                        WHERE ic_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                    )
                ), 
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription

            -- 3. INSTITUTIONS / GROUPS / MILITARY UNITS (Placed below Persons at inner_lo 8.1)
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8.1 AS inner_lo, '**Institutions / Groups / Military Units:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT('[' || c.collective_name || '](?collective_id=' || c.collective_id || ')', ', ')
                    FROM "collectives" c
                    JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
                    WHERE ic.inscription_id = (SELECT selected_id FROM TargetInscription)
                ),
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 9 AS inner_lo, '**Province:** ' || COALESCE(province_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 10 AS inner_lo, '**Place:** ' || CASE WHEN pleiades_id IS NOT NULL THEN '[' || place_name || '](https://pleiades.stoa.org/places/' || pleiades_id || ')' ELSE COALESCE(place_name, 'N/A') END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 11 AS inner_lo, '**Associated Roman Road (Itinere):** ' || CASE WHEN itinere_id IS NOT NULL THEN '[' || COALESCE(road_name, 'Unnamed Road') || '](https://itiner-e.org/?id=' || itinere_id || ')' ELSE 'N/A' END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 12 AS inner_lo, '**Bibliography:** ' || char(10) || '* ' || replace(COALESCE(expanded_bibliography, 'N/A'), char(10), char(10) || '* ') || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Header AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.5 AS inner_lo, '**Inscription Text:**' || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Body AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.6 AS inner_lo, 
                   CASE 
                       WHEN COALESCE(inscription_text_formatted, 'N/A') LIKE '-%' 
                       THEN '' 
                       ELSE '' 
                   END ||
                   replace(
                       replace(COALESCE(inscription_text_formatted, 'N/A'), char(10), '  ' || char(10)),
                       '  ' || char(10) || '-', 
                       '  ' || char(10) || '' || '-'
                   ) || '  ' || char(10) || char(10) AS tl 
            FROM Metadata_Joined
        ),
        Sec0_Spacer AS (SELECT 0 AS sg, 999999 AS seq_id, 1 AS inner_lo, '' AS tl),
        
        Sec1_Header AS (
            SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '#### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
        Sec1_List AS (
            SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, 
                   '* ' || mt.sequence_id || '. ' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        
        Sec2_Header AS (
            SELECT 2 AS sg, 0 AS seq_id, 0 AS inner_lo,
                   '#### Interventions (Later Modifications / Reuse)' || char(10) || char(10) AS tl
        ),
        
        Sec2_Summary AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, 
                   '**' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' :** ' || 
                   CASE 
                       WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 
                       THEN '_no interventions_' 
                       ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' intervention(s)' 
                   END || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
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
            FROM "interventions_and_inscriptions" i 
            JOIN "interventions" iam ON i.intervention_id = iam.intervention_id 
            LEFT JOIN "extent" e ON iam.extent_id = e.extent_id 
            LEFT JOIN "methods" m ON iam.method_id = m.method_id 
            JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id 
              AND i.role_id = 1 
              AND iam.method_id <> 1
        ),
        Sec2_Spacer AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 999998 AS inner_lo, char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        )
        SELECT tl FROM (
            SELECT sg, seq_id, inner_lo, tl FROM Sec0_Metadata 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Body 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_List 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Header
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Summary 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Intervention_Nested_Details 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Spacer
        ) ORDER BY sg ASC, seq_id ASC, inner_lo ASC;
        """
        
        cursor.execute(sql, (f"%{ref_query.strip()}%",))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            st.session_state.search_results = f"No inscriptions found matching reference: {ref_query}"
            st.session_state.active_inscription_ids = []
            return

        # Securely lock found IDs into tracking state & update CSV target mode instantly
        st.session_state.active_inscription_ids = [row[0] for row in rows]
        st.session_state["csv_mode"] = "ids"
        
        # Build out clean formatting structure mirroring your metadata presentation loops
        out_str = [
            f"#### Found {len(rows)} matching inscription(s):\n", 
            "_" * 70 + "\n\n"
        ]
        for idx, row in enumerate(rows, 1):
            (ins_id, ins_ref, line_ref, text_fmt, lemmas, context, support, dating, 
             material, status_tit, province, place, road, biblio, tm_links, persons) = row
            
            block = [
                f"[{idx}] **Quick Reference:** {ins_ref} {line_ref if line_ref else ''} | **TM Number:** {tm_links} | **Inscription ID:** {ins_id}\n",
                f"**Inscription Text:**\n{text_fmt if text_fmt else 'N/A'}\n",
                f"**Nonstandard Spellings:** {lemmas}",
                f"**Context:** {context}",
                f"**Support:** {support}",
                f"**Dating:** {dating}",
                f"**Material:** {material}",
                f"**Status Tituli:** {status_tit}",
                f"**Persons:** {persons}",
                f"**Province:** {province}",
                f"**Place:** {place}",
                f"**Associated Roman Road (Itinere):** {road}",
                f"**Bibliography:**\n* " + str(biblio).replace('\n', '\n* ') if biblio else "**Bibliography:** N/A",
                "\n" + "-"*70 + "\n"
            ]
            out_str.append("\n".join(block))
            
        st.session_state.search_results = "".join(out_str)
        
    except Exception as e:
        st.session_state.search_results = f"Reference Search Error: {e}"
        
def lookup_person_options(name_query):
    if not name_query.strip():
        st.warning("Please enter a name to match.")
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT person_id, person_name FROM "persons" WHERE person_name LIKE ? ORDER BY person_name ASC;', (f"%{name_query.strip()}%",))
        st.session_state.person_matches = cursor.fetchall()
        conn.close()
        if not st.session_state.person_matches:
            st.session_state.search_results = "No individuals matching that name found in database records."
    except Exception as e:
        st.error(f"Person parsing failure: {e}")

def generate_person_report(p_id):
    if not str(p_id).strip().isdigit():
        st.session_state.search_results = "Please enter a valid numerical Person ID."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Keep track of active inscriptions linked to this person for the map component
        cursor.execute("""
            SELECT mt.inscription_id 
            FROM "Max_Thrax" mt 
            JOIN "inscriptions_and_persons" ip ON mt.inscription_id = ip.inscription_id 
            WHERE ip.person_id = ?;
        """, (int(p_id),))
        st.session_state.active_inscription_ids = [r[0] for r in cursor.fetchall()]
        
        st.session_state["active_search_where_clauses"] = []  # Tells exporter: Mode 2 Active
        st.session_state["active_search_has_run"] = True      # Lights up the button globally
        
        sql = """
        WITH TargetPerson AS (
            SELECT ? AS selected_person_id
        )
        SELECT 
            'Name: ' || p.person_name || ' | person id: ' || p.person_id || char(10) || char(10) ||
            
            '**Attested positions in inscriptions:**' || char(10) || 
                COALESCE((
                    SELECT GROUP_CONCAT(pos_grp.pos_summary, char(10) || char(10))
                    FROM (
                        SELECT '• **' || pos.position_description || ':**' || char(10) || '  ' || 
                               GROUP_CONCAT(inner_pos.ref_with_id, ', ') AS pos_summary
                        FROM (
                            SELECT DISTINCT ip2.person_id, pa2.position_id, m2.inscription_ref || ' (id: [' || m2.inscription_id || '](?ins_id=' || m2.inscription_id || '))' AS ref_with_id
                            FROM inscriptions_and_persons ip2
                            JOIN Max_Thrax m2 ON ip2.inscription_id = m2.inscription_id
                            JOIN position_attestations pa2 ON ip2.inscription_person_id = pa2.inscription_person_id
                        ) inner_pos
                        JOIN positions pos ON inner_pos.position_id = pos.position_id
                        CROSS JOIN TargetPerson
                        WHERE inner_pos.person_id = TargetPerson.selected_person_id
                        GROUP BY pos.position_id
                    ) pos_grp
                ), 'None') || char(10) || char(10) ||
                
            CASE 
                WHEN EXISTS (
                    SELECT 1 
                    FROM inscriptions_and_persons ip3
                    JOIN status_designation_attestations sda2 ON ip3.inscription_person_id = sda2.inscription_person_id
                    CROSS JOIN TargetPerson
                    WHERE ip3.person_id = TargetPerson.selected_person_id
                ) THEN 
                    '**Attested status in inscriptions:**' || char(10) ||
                    (
                        SELECT GROUP_CONCAT(sd_grp.sd_summary, char(10) || char(10))
                        FROM (
                            SELECT '• **' || sd.status_designation || ':**' || char(10) || '  ' || 
                                   GROUP_CONCAT(inner_sd.ref_with_id, ', ') AS sd_summary
                            FROM (
                                SELECT DISTINCT ip3.person_id, sda2.status_designation_id, m3.inscription_ref || ' (id: [' || m3.inscription_id || '](?ins_id=' || m3.inscription_id || '))' AS ref_with_id
                                FROM inscriptions_and_persons ip3
                                JOIN Max_Thrax m3 ON ip3.inscription_id = m3.inscription_id
                                JOIN status_designation_attestations sda2 ON ip3.inscription_person_id = sda2.inscription_person_id
                            ) inner_sd
                            JOIN status_designations sd ON inner_sd.status_designation_id = sd.status_designation_id
                            CROSS JOIN TargetPerson
                            WHERE inner_sd.person_id = TargetPerson.selected_person_id
                            GROUP BY sd.status_designation_id
                        ) sd_grp
                    ) || char(10) || char(10)
                ELSE ''
            END ||

            CASE 
                WHEN EXISTS (
                    SELECT 1 
                    FROM inscriptions_and_persons ip4
                    JOIN unit_affiliation_attestations uaa ON ip4.inscription_person_id = uaa.inscription_person_id
                    CROSS JOIN TargetPerson
                    WHERE ip4.person_id = TargetPerson.selected_person_id
                ) THEN 
                    '**Attested unit in inscription:**' || char(10) ||
                    (
                        SELECT GROUP_CONCAT(unit_grp.unit_summary, char(10) || char(10))
                        FROM (
                            SELECT '• **' || col.collective_name || ':**' || char(10) || '  ' || 
                                   GROUP_CONCAT(inner_unit.ref_with_id, ', ') AS unit_summary
                            FROM (
                                SELECT DISTINCT ip4.person_id, uaa.collective_id, m4.inscription_ref || ' (id: [' || m4.inscription_id || '](?ins_id=' || m4.inscription_id || '))' AS ref_with_id
                                FROM inscriptions_and_persons ip4
                                JOIN Max_Thrax m4 ON ip4.inscription_id = m4.inscription_id
                                JOIN unit_affiliation_attestations uaa ON ip4.inscription_person_id = uaa.inscription_person_id
                            ) inner_unit
                            JOIN collectives col ON inner_unit.collective_id = col.collective_id
                            CROSS JOIN TargetPerson
                            WHERE inner_unit.person_id = TargetPerson.selected_person_id
                            GROUP BY col.collective_id
                        ) unit_grp
                    ) || char(10) || char(10)
                ELSE ''
            END ||
                
            '**Notes:** ' || COALESCE(p.person_notes, 'None') AS "Dossier Card"

        FROM persons p
        LEFT JOIN persons_and_virorum_distributio pvd ON p.person_id = pvd.person_id
        LEFT JOIN virorum_distributio vd ON pvd.virorum_distributio_id = vd.virorum_distributio_id
        CROSS JOIN TargetPerson
        WHERE p.person_id = TargetPerson.selected_person_id
        GROUP BY p.person_id;
        """
        
        # Executing the exact logic block using native positional bindings (?) compatible with standard python sqlite3 bindings
        cursor.execute(sql, (int(p_id),))
        result = cursor.fetchone()
        
        if result and result[0]:
            st.session_state.search_results = result[0]
        else:
            st.session_state.search_results = f"No person dossier card compiled for Person ID {p_id}."
    except Exception as e:
        st.session_state.search_results = f"Dossier production error: {e}"
    finally:
        if conn:
            conn.close()

def get_filter_options(table, col):
    options = ["All"]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Select distinct unique entries that aren't empty strings or nulls
        query = f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL AND "{col}" <> "" ORDER BY "{col}" ASC;'
        cursor.execute(query)
        
        for row in cursor.fetchall():
            val = str(row[0])
            
            
            if col == 'relevance_index':
                if val == '0': val = "False"
                elif val == '1': val = "True"
                    
            if col == 'intervention_status':
                if val == '0': val = "False"
                elif val == '1': val = "True"
                
            options.append(val)
            
        conn.close()
    except Exception as e:
        pass
    return options
        
def execute_advanced_search(f_dict):
    global active_inscription_ids
    applied_criteria_summary = []
    where_clauses = []
    query_params = {}
    
    st.session_state["active_search_where_clauses"] = where_clauses
    st.session_state["active_search_query_params"] = query_params
    st.session_state["active_search_has_run"] = True

    # 1. Search Filters
    base_sql = """
        SELECT DISTINCT
            mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
            (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') 
             FROM persons p JOIN inscriptions_and_persons ip ON p.person_id = ip.person_id 
             WHERE ip.inscription_id = mt.inscription_id) AS linked_persons
        FROM "Max_Thrax" mt
        LEFT JOIN "materials" m ON mt.material_id = m.material_id
        LEFT JOIN "support" s ON mt.support_id = s.support_id
        LEFT JOIN "context_types" ct ON mt.context_id = ct.context_id
        LEFT JOIN "provinces" pr ON mt.province_id = pr.province_id
        LEFT JOIN "distributio_titulorum" dt ON mt.distributio_titulorum_id = dt.distributio_titulorum_id
        LEFT JOIN "objects" o ON mt.object_id = o.object_id
        LEFT JOIN "inscriptions_and_persons" ip_f ON mt.inscription_id = ip_f.inscription_id
        LEFT JOIN "status_designation_attestations" sda ON ip_f.inscription_person_id = sda.inscription_person_id
        LEFT JOIN "status_designations" sd ON sda.status_designation_id = sd.status_designation_id
        LEFT JOIN "position_attestations" pa ON ip_f.inscription_person_id = pa.inscription_person_id
        LEFT JOIN "positions" pos ON pa.position_id = pos.position_id
        LEFT JOIN "persons_and_virorum_distributio" pvd ON ip_f.person_id = pvd.person_id
        LEFT JOIN "virorum_distributio" vd ON pvd.virorum_distributio_id = vd.virorum_distributio_id
        LEFT JOIN "interventions_and_inscriptions" iai ON mt.inscription_id = iai.inscription_id
        LEFT JOIN "interventions" inter ON iai.intervention_id = inter.intervention_id
        LEFT JOIN "methods" meth ON inter.method_id = meth.method_id
        LEFT JOIN "extent" ext ON inter.extent_id = ext.extent_id
        LEFT JOIN "interventions_and_targets" iat ON inter.intervention_id = iat.intervention_id
        LEFT JOIN "targets" targ ON iat.target_id = targ.target_id
        LEFT JOIN "inscriptions_and_collectives" ic ON mt.inscription_id = ic.inscription_id
        LEFT JOIN "collectives" col ON ic.collective_id = col.collective_id
        LEFT JOIN "status_tituli" st ON mt.status_tituli_id = st.status_tituli_id
        WHERE 1=1
    """

    # 2. Text Search with Boolean, Fallbacks, AND Latin Lemmatization Parser
    phrase = f_dict.get('text', '').strip()
    if phrase:
        applied_criteria_summary.append(f"  • Keyword/Phrase: '{phrase}'")
        
        # Check for boolean operators regardless of case
        upper_phrase = phrase.upper()
        if " AND " in upper_phrase or " OR " in upper_phrase or " NOT " in upper_phrase:
            
            # Normalize spaces around operators and force them to uppercase
            norm_phrase = phrase
            norm_phrase = re.sub(r'\s+[aA][nN][dD]\s+', ' AND ', norm_phrase)
            norm_phrase = re.sub(r'\s+[oO][rR]\s+', ' OR ', norm_phrase)
            norm_phrase = re.sub(r'\s+[nN][oO][tT]\s+', ' NOT ', norm_phrase)
            
            tokens = re.split(r'( AND | OR | NOT )', norm_phrase)
            
            bool_clause = "("
            current_op = "AND"
            is_first_term = True
            
            for token in tokens:
                t_clean = token.strip()
                if not t_clean: 
                    continue
                
                if t_clean in ("AND", "OR", "NOT"):
                    current_op = t_clean
                else:
                    # --- LATIN PARSER INTEGRATION ---
                    clean_word = clean_epigraphic_text(t_clean).lower()
                    root_lemma = LATIN_LEMMA_MAP.get(clean_word, clean_word)
                    synonyms = list(set([k for k, v in LATIN_LEMMA_MAP.items() if v == root_lemma] + [root_lemma, clean_word]))
                    
                    continuous_words = []
                    for syn in synonyms:
                        cw = syn.lower().replace(" ", "")
                        cw = re.sub(r'[\[\]\(\)\.\?\-\/\u0323⟦⟧〚〛\d!\{\}<>´`\^~]', '', cw)
                        if cw:
                            continuous_words.append(cw)
                    continuous_words = list(set(continuous_words))
                    
                    syn_stripped_pnames = []
                    for idx, syn in enumerate(synonyms):
                        pname = f"b_syn_str_{len(query_params)}"
                        query_params[pname] = f"%{syn}%"
                        syn_stripped_pnames.append(pname)
                        
                    syn_recon_pnames = []
                    for idx, cw in enumerate(continuous_words):
                        pname = f"b_syn_rec_{len(query_params)}"
                        query_params[pname] = f"%{cw}%"
                        syn_recon_pnames.append(pname)
                    
                    meta_word = f"%{t_clean}%"
                    p_pers = f"bool_pers_{len(query_params)}"
                    p_col = f"bool_col_{len(query_params)}"
                    query_params[p_pers] = meta_word
                    query_params[p_col] = meta_word
                    
                    stripped_likes = " OR ".join([f"mt.inscription_text_stripped LIKE :{p}" for p in syn_stripped_pnames])
                    recon_likes = " OR ".join([f"mt.reconstituted_text LIKE :{p}" for p in syn_recon_pnames])
                    clean_likes = " OR ".join([f"mt.cleaned_text LIKE :{p}" for p in syn_recon_pnames])
                    
                    sub_clause = (
                        f"({stripped_likes} "
                        f"OR {recon_likes} "
                        f"OR {clean_likes} "
                        f"OR (SELECT GROUP_CONCAT(p2.person_name) FROM persons p2 JOIN inscriptions_and_persons ip2 ON p2.person_id = ip2.person_id WHERE ip2.inscription_id = mt.inscription_id) LIKE :{p_pers} "
                        f"OR col.collective_name LIKE :{p_col})"
                    )
                    
                    if current_op == "NOT":
                        prefix = "" if is_first_term else " AND "
                        bool_clause += f"{prefix}NOT {sub_clause}"
                        current_op = "AND"
                    elif is_first_term:
                        bool_clause += sub_clause
                    else:
                        bool_clause += f" {current_op} {sub_clause}"
                    
                    is_first_term = False
                    
            bool_clause += ")"
            where_clauses.append(bool_clause)
            
        else:
            # --- SIMPLE ADVANCED SEARCH WORD (NO BOOLEANS) ---
            clean_phrase = clean_epigraphic_text(phrase).lower()
            root_lemma = LATIN_LEMMA_MAP.get(clean_phrase, clean_phrase)
            synonyms = list(set([k for k, v in LATIN_LEMMA_MAP.items() if v == root_lemma] + [root_lemma, clean_phrase]))
            
            continuous_words = []
            for syn in synonyms:
                cw = syn.lower().replace(" ", "")
                cw = re.sub(r'[\[\]\(\)\.\?\-\/\u0323⟦⟧〚〛\d!\{\}<>´`\^~]', '', cw)
                if cw:
                    continuous_words.append(cw)
            continuous_words = list(set(continuous_words))
            
            syn_stripped_pnames = []
            for idx, syn in enumerate(synonyms):
                pname = f"p_syn_str_{len(query_params)}"
                query_params[pname] = f"%{syn}%"
                syn_stripped_pnames.append(pname)
                
            syn_recon_pnames = []
            for idx, cw in enumerate(continuous_words):
                pname = f"p_syn_rec_{len(query_params)}"
                query_params[pname] = f"%{cw}%"
                syn_recon_pnames.append(pname)
                
            meta_phrase = f"%{phrase}%"
            p_pers = f"phrase_pers_{len(query_params)}"
            p_col = f"phrase_col_{len(query_params)}"
            query_params[p_pers] = meta_phrase
            query_params[p_col] = meta_phrase
            
            stripped_likes = " OR ".join([f"mt.inscription_text_stripped LIKE :{p}" for p in syn_stripped_pnames])
            recon_likes = " OR ".join([f"mt.reconstituted_text LIKE :{p}" for p in syn_recon_pnames])
            clean_likes = " OR ".join([f"mt.cleaned_text LIKE :{p}" for p in syn_recon_pnames])
            
            where_clauses.append(
                f"({stripped_likes} "
                f"OR {recon_likes} "
                f"OR {clean_likes} "
                f"OR (SELECT GROUP_CONCAT(p2.person_name) FROM persons p2 JOIN inscriptions_and_persons ip2 ON p2.person_id = ip2.person_id WHERE ip2.inscription_id = mt.inscription_id) LIKE :{p_pers} "
                f"OR col.collective_name LIKE :{p_col})"
            )
   # --- DATE RANGE FILTER LOGIC ---
    req_start = f_dict.get('start_date')
    req_end = f_dict.get('end_date')
    dating_strategy = f_dict.get('dating_strategy', 'overlap') # Defaults to overlap if not specified

    if req_start is not None and req_end is not None:
        if dating_strategy == 'strict':
            applied_criteria_summary.append(f"  • Date Span: Strictly fully contained within {req_start} to {req_end} CE")
            where_clauses.append("mt.start_date >= :req_start AND mt.end_date <= :req_end")
        else:
            applied_criteria_summary.append(f"  • Date Span: Overlapping anywhere within {req_start} to {req_end} CE")
            where_clauses.append("mt.end_date >= :req_start AND mt.start_date <= :req_end")
            
        query_params['req_start'] = int(req_start)
        query_params['req_end'] = int(req_end)
        
    elif req_start is not None:
        # Fallback if only start date was provided
        applied_criteria_summary.append(f"  • Start Date Bound: >= {req_start} CE")
        where_clauses.append("mt.end_date >= :req_start")
        query_params['req_start'] = int(req_start)
        
    elif req_end is not None:
        # Fallback if only end date was provided
        applied_criteria_summary.append(f"  • End Date Bound: <= {req_end} CE")
        where_clauses.append("mt.start_date <= :req_end")
        query_params['req_end'] = int(req_end)
        
   # 3. Mapping Configuration
    mapping = [
        ('relevance_index', 'mt.relevance_index', 'Relevance'),
        ('distributio_titulorum', 'dt.distributio_titulorum', 'Distributio Titulorum'),
        ('material_name', 'm.material_name', 'Material'),
        ('support_name', 's.support_name', 'Support Type'),
        ('context_name', 'ct.context_name', 'Context Type'),
        ('province_name', 'pr.province_name', 'Province'),
        ('number_of_inscriptions', 'o.number_of_inscriptions', 'Inscriptions on Object'),
        ('status_designation', 'sd.status_designation', 'Status Designation'),
        ('position_description', 'pos.position_description', 'Office/Military Role'),
        ('intervention_status', 'mt.intervention_status', 'Intervention Status'),
        ('method_description', 'meth.method_description', 'Method of Intervention'),
        ('extent_description', 'ext.extent_description', 'Extent of Intervention'),
        ('target_description', 'targ.target_description', 'Target of Intervention'),
        ('status_tituli_name', 'st.status_tituli_name', 'Status Tituli (Conservation)')
   ]

  # --- THE AUTOMATIC SQL BUILDER ---
    # This loop looks at each filter box you have filled in. 
    # It automatically skips any empty boxes or boxes set to "All". 
    # For everything else, it figures out if you picked one item or a list of items,
    # and writes the WHERE clause accordingly
    
    for key, column_sql, display_name in mapping:
        val = f_dict.get(key, [])
        
        # FIX 1: Relevance Check (0 vs 1)
        if key == 'relevance_index' and f_dict.get('relevance_active'):
            applied_criteria_summary.append(f"  • {display_name}: {'Relevant' if val == 1 else 'Not Relevant'}")
            p_name = f"param_{key}"
            where_clauses.append(f"mt.relevance_index = :{p_name}")
            query_params[p_name] = val
            continue

        # FIX 2: Intervention Status Check (0 vs 1)
        if key == 'intervention_status' and f_dict.get('intervention_status_active'):
            applied_criteria_summary.append(f"  • {display_name}: {'Intervention present' if val == 1 else 'No later intervention'}")
            p_name = f"param_{key}"
            where_clauses.append(f"mt.intervention_status = :{p_name}")
            query_params[p_name] = val
            continue
            
        if val == "All" or val == ["All"] or (not val and val != 0):
            continue

        if not isinstance(val, list):
            val_str = str(val).strip()
            if not val_str and val_str != "0":
                continue
                
            applied_criteria_summary.append(f"  • {display_name}: '{val_str}'")
            if key in ('relevance_index', 'intervention_status'):
                val = 1 if val_str in ("True", "1") else 0
                
            p_name = f"param_{key}"
            where_clauses.append(f"{column_sql} = :{p_name}")
            query_params[p_name] = val
        else:
            applied_criteria_summary.append(f"  • {display_name}: {', '.join(map(str, val))}")
            
            param_names = []
            for idx, item in enumerate(val):
                p_name = f"param_{key}_{idx}"
                param_names.append(f":{p_name}")
                query_params[p_name] = item
            
            where_clauses.append(f"{column_sql} IN ({', '.join(param_names)})")
            
    # --- PERSON FILTER LOGIC (HANDLES AND vs OR) ---
    person_ids = f_dict.get('person_id', [])
    person_op = f_dict.get('person_operator', 'OR')

    if person_ids and person_ids != "All" and person_ids != ["All"]:
        applied_criteria_summary.append(f"  • Person ({person_op}): {', '.join(map(str, person_ids))}")
        
        # Create dedicated parameters for the selected people
        person_params = []
        for idx, p_id in enumerate(person_ids):
            p_param_name = f"param_person_id_{idx}"
            query_params[p_param_name] = p_id
            person_params.append(f":{p_param_name}")

        if person_op == "AND":
            # Requires a sub-query checking that the count of matched target IDs matches the total selected
            where_clauses.append(f"""
                (SELECT COUNT(DISTINCT ip_sub.person_id) 
                 FROM "inscriptions_and_persons" ip_sub 
                 WHERE ip_sub.inscription_id = mt.inscription_id 
                 AND ip_sub.person_id IN ({', '.join(person_params)})) = {len(person_ids)}
            """)
        else:
            # Traditional OR mapping logic using simple inclusion matching
            where_clauses.append(f"ip_f.person_id IN ({', '.join(person_params)})")

    # --- COLLECTIVE FILTER LOGIC (HANDLES AND vs OR) ---
    collective_names = f_dict.get('collective_name', [])
    collective_op = f_dict.get('collective_operator', 'OR')

    if collective_names and collective_names != "All" and collective_names != ["All"]:
        applied_criteria_summary.append(f"  • Collective/Military Unit ({collective_op}): {', '.join(map(str, collective_names))}")
        
        # Create dedicated parameters for the selected collectives
        collective_params = []
        for idx, col_name in enumerate(collective_names):
            c_param_name = f"param_collective_name_{idx}"
            query_params[c_param_name] = col_name
            collective_params.append(f":{c_param_name}")

        if collective_op == "AND":
            # Requires a sub-query checking that the count of matched collective names matches the total selected
            where_clauses.append(f"""
                (SELECT COUNT(DISTINCT col_sub.collective_name) 
                 FROM "inscriptions_and_collectives" ic_sub
                 JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                 WHERE ic_sub.inscription_id = mt.inscription_id 
                 AND col_sub.collective_name IN ({', '.join(collective_params)})) = {len(collective_names)}
            """)
        else:
            # Traditional OR mapping logic using simple inclusion matching
            where_clauses.append(f"col.collective_name IN ({', '.join(collective_params)})")

    # --- VIRORUM DISTRIBUTIO FILTER LOGIC (CHECKS PERSONS OR COLLECTIVES) ---
    vd_vals = f_dict.get('virorum_distributio', [])
    if vd_vals and vd_vals != "All" and vd_vals != ["All"]:
        if not isinstance(vd_vals, list):
            vd_vals = [vd_vals]
            
        applied_criteria_summary.append(f"  • Distributio Virorum: {', '.join(map(str, vd_vals))}")
        
        vd_params = []
        for idx, vd_val in enumerate(vd_vals):
            p_name = f"param_vd_custom_{idx}"
            query_params[p_name] = vd_val
            vd_params.append(f":{p_name}")
            
        vd_placeholders = ", ".join(vd_params)
        
        # Check if the inscription has any linked person or collective matching the virorum_distributio
        where_clauses.append(f"""
            (
                EXISTS (
                    SELECT 1 
                    FROM "inscriptions_and_persons" ip_sub
                    JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                    JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                    WHERE ip_sub.inscription_id = mt.inscription_id 
                      AND vd_sub.virorum_distributio IN ({vd_placeholders})
                )
                OR
                EXISTS (
                    SELECT 1 
                    FROM "inscriptions_and_collectives" ic_sub
                    JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                    JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                    WHERE ic_sub.inscription_id = mt.inscription_id 
                      AND vd_sub.virorum_distributio IN ({vd_placeholders})
                )
            )
        """)

    # --- STANDARD LOOP FOR ALL REMAINING CRITERIA FIELDS ---
    for key, column_sql, display_name in mapping:
        val = f_dict.get(key, [])
        
        if not val or val == "All" or val == ["All"]:
            continue

        if not isinstance(val, list):
            val_str = str(val).strip()
            if not val_str:
                continue
                
            applied_criteria_summary.append(f"  • {display_name}: '{val_str}'")
            if key in ('relevance_index', 'intervention_status'):
                val = 1 if val_str in ("True", "1") else 0
                
            p_name = f"param_{key}"
            where_clauses.append(f"{column_sql} = :{p_name}")
            query_params[p_name] = val
        else:
            applied_criteria_summary.append(f"  • {display_name}: {', '.join(map(str, val))}")
            
            param_names = []
            for idx, item in enumerate(val):
                p_name = f"param_{key}_{idx}"
                param_names.append(f":{p_name}")
                query_params[p_name] = item
            
            where_clauses.append(f"{column_sql} IN ({', '.join(param_names)})")
            
    # Assemble complete sql string
    if where_clauses:
        final_sql = base_sql + " AND " + " AND ".join(where_clauses) + " ORDER BY mt.inscription_id DESC;"
    else:
        final_sql = base_sql + " ORDER BY mt.inscription_id DESC;"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(final_sql, query_params)
        rows = cursor.fetchall()
        st.session_state.active_inscription_ids = [row[0] for row in rows]
        all_matched_ids = st.session_state.active_inscription_ids

        st.session_state["active_search_where_clauses"] = where_clauses
        st.session_state["active_search_query_params"] = query_params
        st.session_state["active_search_has_run"] = True
        
        out_str = []
        
        object_count = 0
        if all_matched_ids:
            obj_cursor = conn.cursor()
            chunk_size = 900
            unique_objects = set()
            
            # Split IDs into safe chunks to prevent SQLite parameter limits (999) from crashing
            for i in range(0, len(all_matched_ids), chunk_size):
                chunk = all_matched_ids[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                
                obj_cursor.execute(
                    f'SELECT DISTINCT object_id FROM "Max_Thrax" WHERE inscription_id IN ({placeholders});', 
                    chunk
                )
                for row in obj_cursor.fetchall():
                    unique_objects.add(row[0])
            
            object_count = len(unique_objects)
        # -----------------------------------------
        header_lines = ["## Advanced Search Results\n"]
        header_lines.append("**Filters Applied:**\n")
        if applied_criteria_summary:
            header_lines.extend([f"{c}\n" for c in applied_criteria_summary])
        else:
            header_lines.append("  • *[None - Broad Query Execution Mode]*\n")
            
        header_lines.append(f"\n**Results:** Found **{len(all_matched_ids)}** matching inscriptions on **{object_count}** objects.\n\n---\n\n")
        out_str.append("".join(header_lines))
        
        if not all_matched_ids:
            out_str.append("No inscriptions found matching the specified advanced filter criteria.\n")
            st.session_state.search_results = "".join(out_str)
            conn.close()
            return

        # 2. Generate full reports for everyone
        sql = """
        WITH TargetInscription AS (SELECT ? AS selected_id),
        TargetObject AS (SELECT object_id AS selected_obj_id FROM "Max_Thrax" WHERE inscription_id = (SELECT selected_id FROM TargetInscription)),
        Metadata_Joined AS (
            SELECT mt.inscription_id, mt.inscription_ref, mt.line_ref, 
                   mt.inscription_text_formatted, mt.corrected_lemmas, mt.dating, mt.expanded_bibliography,
                   ct.context_name, s.support_name, m.material_name, pr.province_name, pl.place_name, pl.pleiades_id,
                   r_roads.road_name, r_roads.itinere_id,
                   st.status_tituli_name,
                   -- Subquery to pull and build comma-separated Markdown hyperlinks for all TM Numbers linked to this Inscription
                   COALESCE(
                       (SELECT GROUP_CONCAT('[' || itm.TM_number || '](https://www.trismegistos.org/text/' || itm.TM_number || ')', ', ')
                        FROM "inscriptions_and_TM_numbers" itm 
                        WHERE itm.inscription_id = mt.inscription_id), 
                       'N/A'
                   ) AS tm_hyperlinks
            FROM "Max_Thrax" mt CROSS JOIN TargetInscription
            LEFT JOIN "context_types" ct        ON mt.context_id = ct.context_id
            LEFT JOIN "support" s                ON mt.support_id = s.support_id
            LEFT JOIN "materials" m              ON mt.material_id = m.material_id
            LEFT JOIN "provinces" pr            ON mt.province_id = pr.province_id
            LEFT JOIN "places" pl                ON mt.place_id = pl.place_id
            LEFT JOIN "inscription_and_road" iar ON mt.inscription_id = iar.inscription_id
            LEFT JOIN "itiner_e_roads" r_roads  ON iar.itiner_e_road_id = r_roads.itiner_e_road_id
            LEFT JOIN "status_tituli" st         ON mt.status_tituli_id = st.status_tituli_id
            WHERE mt.inscription_id = TargetInscription.selected_id
        ),
        Sec0_Metadata AS (
            SELECT 0 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '**Quick Reference:** ' || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL THEN '[' || inscription_ref || '](https://edcs.hist.uzh.ch/en/search?edcs-id=' || inscription_ref || ')' 
                       ELSE '' 
                   END || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL AND line_ref IS NOT NULL THEN ' ' || line_ref
                       WHEN line_ref IS NOT NULL THEN line_ref
                       WHEN inscription_ref IS NULL AND line_ref IS NULL THEN 'N/A'
                       ELSE ''
                   END || 
                   ' | **TM Number:** ' || tm_hyperlinks ||
                   ' | **Inscription ID:** [' || inscription_id || '](?ins_id=' || inscription_id || ')' || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 3 AS inner_lo, '**Nonstandard Spellings:** ' || COALESCE(corrected_lemmas, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 4 AS inner_lo, '**Context:** ' || COALESCE(context_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 5 AS inner_lo, '**Support:** ' || COALESCE(support_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 6 AS inner_lo, '**Dating:** ' || COALESCE(dating, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7 AS inner_lo, '**Material:** ' || COALESCE(material_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.5 AS inner_lo, '**Status Tituli:** ' || COALESCE(status_tituli_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined

            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.9 AS inner_lo, '**Distributio Virorum:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT(distinct_vd, ', ') FROM (
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_persons" ip_sub
                        JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                        JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                        WHERE ip_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                        
                        UNION
                        
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_collectives" ic_sub
                        JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                        JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                        WHERE ic_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                    )
                ), 
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription

            -- 3. INSTITUTIONS / GROUPS / MILITARY UNITS (Placed below Persons at inner_lo 8.1)
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8.1 AS inner_lo, '**Institutions / Groups / Military Units:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT('[' || c.collective_name || '](?collective_id=' || c.collective_id || ')', ', ')
                    FROM "collectives" c
                    JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
                    WHERE ic.inscription_id = (SELECT selected_id FROM TargetInscription)
                ),
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 9 AS inner_lo, '**Province:** ' || COALESCE(province_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 10 AS inner_lo, '**Place:** ' || CASE WHEN pleiades_id IS NOT NULL THEN '[' || place_name || '](https://pleiades.stoa.org/places/' || pleiades_id || ')' ELSE COALESCE(place_name, 'N/A') END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 11 AS inner_lo, '**Associated Roman Road (Itinere):** ' || CASE WHEN itinere_id IS NOT NULL THEN '[' || COALESCE(road_name, 'Unnamed Road') || '](https://itiner-e.org/?id=' || itinere_id || ')' ELSE 'N/A' END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 12 AS inner_lo, '**Bibliography:** ' || char(10) || '* ' || replace(COALESCE(expanded_bibliography, 'N/A'), char(10), char(10) || '* ') || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Header AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.5 AS inner_lo, '**Inscription Text:**' || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Body AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.6 AS inner_lo, 
                   CASE 
                       WHEN COALESCE(inscription_text_formatted, 'N/A') LIKE '-%' 
                       THEN '' 
                       ELSE '' 
                   END ||
                   replace(
                       replace(COALESCE(inscription_text_formatted, 'N/A'), char(10), '  ' || char(10)),
                       '  ' || char(10) || '-', 
                       '  ' || char(10) || '' || '-'
                   ) || '  ' || char(10) || char(10) AS tl 
            FROM Metadata_Joined
        ),
        Sec0_Spacer AS (SELECT 0 AS sg, 999999 AS seq_id, 1 AS inner_lo, '' AS tl),
        
        Sec1_Header AS (
            SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '#### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
        Sec1_List AS (
            SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, 
                   '* ' || mt.sequence_id || '. ' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        
        Sec2_Header AS (
            SELECT 2 AS sg, 0 AS seq_id, 0 AS inner_lo,
                   '#### Interventions (Later Modifications / Reuse)' || char(10) || char(10) AS tl
        ),
        
        Sec2_Summary AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, 
                   '**' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' :** ' || 
                   CASE 
                       WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 
                       THEN '_no interventions_' 
                       ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' intervention(s)' 
                   END || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
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
            FROM "interventions_and_inscriptions" i 
            JOIN "interventions" iam ON i.intervention_id = iam.intervention_id 
            LEFT JOIN "extent" e ON iam.extent_id = e.extent_id 
            LEFT JOIN "methods" m ON iam.method_id = m.method_id 
            JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id 
              AND i.role_id = 1 
              AND iam.method_id <> 1
        ),
        Sec2_Spacer AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 999998 AS inner_lo, char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        )
        SELECT tl FROM (
            SELECT sg, seq_id, inner_lo, tl FROM Sec0_Metadata 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Body 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_List 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Header
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Summary 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Intervention_Nested_Details 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Spacer
        ) ORDER BY sg ASC, seq_id ASC, inner_lo ASC;
        """
        
        # 3. Stitch every matching custom card together sequentially
        for rank, ins_id in enumerate(all_matched_ids, 1):
            out_str.append(f"## Result {rank}\n")
            
            cursor.execute(sql, (int(ins_id),))
            card_rows = cursor.fetchall()
            
            if card_rows:
                dossier_text = "\n".join([r[0] for r in card_rows if r[0] is not None])
                out_str.append(dossier_text)
            else:
                out_str.append(f"_Warning: Could not compile advanced dossier data for ID: {ins_id}_")
                
            out_str.append("\n\n---\n\n")
            
        st.session_state.search_results = "\n\n".join(out_str)
        
        conn.close()
    except Exception as e:
        st.session_state.search_results = f"Advanced Search System Failure: {e}"

def fetch_metadata_by_id(inscription_id):
    if not inscription_id.strip().isdigit():
        st.session_state.search_results = "Please enter a valid numerical Inscription ID."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
        WITH TargetInscription AS (SELECT ? AS selected_id),
        TargetObject AS (SELECT object_id AS selected_obj_id FROM "Max_Thrax" WHERE inscription_id = (SELECT selected_id FROM TargetInscription)),
        Metadata_Joined AS (
            SELECT mt.inscription_id, mt.inscription_ref, mt.line_ref, 
                   mt.inscription_text_formatted, mt.corrected_lemmas, mt.dating, mt.expanded_bibliography,
                   ct.context_name, s.support_name, m.material_name, pr.province_name, pl.place_name, pl.pleiades_id,
                   r_roads.road_name, r_roads.itinere_id,
                   st.status_tituli_name,
                   -- Subquery to pull and build comma-separated Markdown hyperlinks for all TM Numbers linked to this Inscription
                   COALESCE(
                       (SELECT GROUP_CONCAT('[' || itm.TM_number || '](https://www.trismegistos.org/text/' || itm.TM_number || ')', ', ')
                        FROM "inscriptions_and_TM_numbers" itm 
                        WHERE itm.inscription_id = mt.inscription_id), 
                       'N/A'
                   ) AS tm_hyperlinks
            FROM "Max_Thrax" mt CROSS JOIN TargetInscription
            LEFT JOIN "context_types" ct        ON mt.context_id = ct.context_id
            LEFT JOIN "support" s                ON mt.support_id = s.support_id
            LEFT JOIN "materials" m              ON mt.material_id = m.material_id
            LEFT JOIN "provinces" pr            ON mt.province_id = pr.province_id
            LEFT JOIN "places" pl                ON mt.place_id = pl.place_id
            LEFT JOIN "inscription_and_road" iar ON mt.inscription_id = iar.inscription_id
            LEFT JOIN "itiner_e_roads" r_roads  ON iar.itiner_e_road_id = r_roads.itiner_e_road_id
            LEFT JOIN "status_tituli" st         ON mt.status_tituli_id = st.status_tituli_id
            WHERE mt.inscription_id = TargetInscription.selected_id
        ),
        Sec0_Metadata AS (
            SELECT 0 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '**Quick Reference:** ' || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL THEN '[' || inscription_ref || '](https://edcs.hist.uzh.ch/en/search?edcs-id=' || inscription_ref || ')' 
                       ELSE '' 
                   END || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL AND line_ref IS NOT NULL THEN ' ' || line_ref
                       WHEN line_ref IS NOT NULL THEN line_ref
                       WHEN inscription_ref IS NULL AND line_ref IS NULL THEN 'N/A'
                       ELSE ''
                   END || 
                   ' | **TM Number:** ' || tm_hyperlinks ||
                   ' | **Inscription ID:** [' || inscription_id || '](?ins_id=' || inscription_id || ')' || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 3 AS inner_lo, '**Nonstandard Spellings:** ' || COALESCE(corrected_lemmas, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 4 AS inner_lo, '**Context:** ' || COALESCE(context_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 5 AS inner_lo, '**Support:** ' || COALESCE(support_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 6 AS inner_lo, '**Dating:** ' || COALESCE(dating, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7 AS inner_lo, '**Material:** ' || COALESCE(material_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.5 AS inner_lo, '**Status Tituli:** ' || COALESCE(status_tituli_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined

            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 7.9 AS inner_lo, '**Distributio Virorum:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT(distinct_vd, ', ') FROM (
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_persons" ip_sub
                        JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
                        JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
                        WHERE ip_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                        
                        UNION
                        
                        SELECT DISTINCT vd_sub.virorum_distributio AS distinct_vd
                        FROM "inscriptions_and_collectives" ic_sub
                        JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                        JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
                        WHERE ic_sub.inscription_id = (SELECT selected_id FROM TargetInscription)
                    )
                ), 
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription

            -- 3. INSTITUTIONS / GROUPS / MILITARY UNITS (Placed below Persons at inner_lo 8.1)
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8.1 AS inner_lo, '**Institutions / Groups / Military Units:** ' || COALESCE(
                (
                    SELECT GROUP_CONCAT('[' || c.collective_name || '](?collective_id=' || c.collective_id || ')', ', ')
                    FROM "collectives" c
                    JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
                    WHERE ic.inscription_id = (SELECT selected_id FROM TargetInscription)
                ),
                'N/A'
            ) || char(10) || char(10) AS tl FROM TargetInscription
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 9 AS inner_lo, '**Province:** ' || COALESCE(province_name, 'N/A') || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 10 AS inner_lo, '**Place:** ' || CASE WHEN pleiades_id IS NOT NULL THEN '[' || place_name || '](https://pleiades.stoa.org/places/' || pleiades_id || ')' ELSE COALESCE(place_name, 'N/A') END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 11 AS inner_lo, '**Associated Roman Road (Itinere):** ' || CASE WHEN itinere_id IS NOT NULL THEN '[' || COALESCE(road_name, 'Unnamed Road') || '](https://itiner-e.org/?id=' || itinere_id || ')' ELSE 'N/A' END || char(10) || char(10) AS tl FROM Metadata_Joined
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 12 AS inner_lo, '**Bibliography:** ' || char(10) || '* ' || replace(COALESCE(expanded_bibliography, 'N/A'), char(10), char(10) || '* ') || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Header AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.5 AS inner_lo, '**Inscription Text:**' || char(10) || char(10) AS tl FROM Metadata_Joined
        ),
        Sec0_Text_Body AS (
            SELECT 0 AS sg, 0 AS seq_id, 1.6 AS inner_lo, 
                   CASE 
                       WHEN COALESCE(inscription_text_formatted, 'N/A') LIKE '-%' 
                       THEN '' 
                       ELSE '' 
                   END ||
                   replace(
                       replace(COALESCE(inscription_text_formatted, 'N/A'), char(10), '  ' || char(10)),
                       '  ' || char(10) || '-', 
                       '  ' || char(10) || '' || '-'
                   ) || '  ' || char(10) || char(10) AS tl 
            FROM Metadata_Joined
        ),
        Sec0_Spacer AS (SELECT 0 AS sg, 999999 AS seq_id, 1 AS inner_lo, '' AS tl),
        
        Sec1_Header AS (
            SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, 
                   '#### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
        Sec1_List AS (
            SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, 
                   '* ' || mt.sequence_id || '. ' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        
        Sec2_Header AS (
            SELECT 2 AS sg, 0 AS seq_id, 0 AS inner_lo,
                   '#### Interventions (Later Modifications / Reuse)' || char(10) || char(10) AS tl
        ),
        
        Sec2_Summary AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, 
                   '**' || mt.inscription_ref || 
                   CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || 
                   CASE WHEN mt.inscription_id = (SELECT selected_id FROM TargetInscription) THEN '[current inscription]' ELSE '' END ||
                   ' :** ' || 
                   CASE 
                       WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 
                       THEN '_no interventions_' 
                       ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' intervention(s)' 
                   END || char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        ),
        
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
            FROM "interventions_and_inscriptions" i 
            JOIN "interventions" iam ON i.intervention_id = iam.intervention_id 
            LEFT JOIN "extent" e ON iam.extent_id = e.extent_id 
            LEFT JOIN "methods" m ON iam.method_id = m.method_id 
            JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id 
              AND i.role_id = 1 
              AND iam.method_id <> 1
        ),
        Sec2_Spacer AS (
            SELECT 2 AS sg, mt.sequence_id AS seq_id, 999998 AS inner_lo, char(10) AS tl 
            FROM "Max_Thrax" mt 
            CROSS JOIN TargetObject 
            WHERE mt.object_id = TargetObject.selected_obj_id
        )
        SELECT tl FROM (
            SELECT sg, seq_id, inner_lo, tl FROM Sec0_Metadata 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Text_Body 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec0_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Header 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_List 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec1_Spacer 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Header
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Summary 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Intervention_Nested_Details 
            UNION ALL SELECT sg, seq_id, inner_lo, tl FROM Sec2_Spacer
        ) ORDER BY sg ASC, seq_id ASC, inner_lo ASC;
        """
        cursor.execute(sql, (int(inscription_id),))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            
            st.session_state.active_inscription_ids = [int(inscription_id.strip())]
            st.session_state["active_search_where_clauses"] = []  # Mode 2 explicit ID handling
            st.session_state["active_search_has_run"] = True      # Displays the button

            st.session_state.search_results = f"No metadata entries discovered for ID: {inscription_id}"
            
        else:
            st.session_state.search_results = "\n".join([row[0] for row in rows if row[0] is not None])
    except Exception as e:
        st.session_state.search_results = f"Error fetching metadata: {e}"


# =========================================================
# Map Generator
# =========================================================
def generate_active_map():
    ids_to_map = st.session_state.active_inscription_ids
    if not ids_to_map:
        st.warning("No active search or report results are currently loaded to map.")
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in ids_to_map)
        
        # Select all normal inscription and place attributes, including our custom flags
        query = f"""
            SELECT m.inscription_id, p.latitude, p.longitude, m.inscription_ref, m.sequence_id, 
                   m.support_id, s.support_name, dt.distributio_titulorum, o.number_of_inscriptions, pr.province_name,
                   p.place_name, p.pleiades_id, p.approximate_location, p.approximate_area
            FROM "Max_Thrax" m
            INNER JOIN "places" p ON m.place_id = p.place_id
            LEFT JOIN "support" s ON m.support_id = s.support_id
            LEFT JOIN "distributio_titulorum" dt ON m.distributio_titulorum_id = dt.distributio_titulorum_id
            LEFT JOIN "objects" o ON m.object_id = o.object_id
            LEFT JOIN "provinces" pr ON m.province_id = pr.province_id
            WHERE m.inscription_id IN ({placeholders});
        """
        cursor.execute(query, ids_to_map)
        matched_points = cursor.fetchall()

        road_links_dict = {row[0]: {'roads': []} for row in matched_points}
        if ids_to_map:
            road_query = f"""
                SELECT iar.inscription_id, ier.road_name, ier.itinere_id
                FROM "inscription_and_road" iar
                INNER JOIN "itiner_e_roads" ier ON iar.itiner_e_road_id = ier.itiner_e_road_id
                WHERE iar.inscription_id IN ({placeholders});
            """
            cursor.execute(road_query, ids_to_map)
            for ins_id, r_name, i_id in cursor.fetchall():
                if ins_id in road_links_dict:
                    road_links_dict[ins_id]['roads'].append((r_name, i_id))
        conn.close()
    except Exception as e:
        st.error(f"Map rendering fault: {e}")
        return

    if not matched_points:
        st.info("None of the inscriptions have known geographic coordinates in the database.")
        return

    # Seed map center
    valid_center = [41.807100, 14.919200]  # Centered at Larino
    
    mymap = folium.Map(location=valid_center, zoom_start=4.5, tiles=None,zoom_snap=0.125, wheel_px_per_zoom_level=150)
    folium.TileLayer(tiles="https://cawm.lib.uiowa.edu/tiles/{z}/{x}/{y}.png", name="AWMC", overlay=False, control=True, attr="AWMC").add_to(mymap)
    folium.TileLayer(tiles="https://dh.gu.se/tiles/imperium/{z}/{x}/{y}.png", name="DARE", overlay=False, control=True, attr="DARE").add_to(mymap)

    # -------------------------------------------------------------
    # BASE ROADS & PROVINCES OVERLAYS
    # -------------------------------------------------------------
    optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
    if os.path.exists(optimized_json_path):
        with open(optimized_json_path, "r", encoding="utf-8") as f:
            roads_data = json.load(f)
        folium.GeoJson(roads_data, name="Itinere Land Roads", show=True, overlay=True, control=True,
                       style_function=lambda feature: {"color": "#ff33a1", "weight": 1.0, "opacity": 0.8}).add_to(mymap)
        
   # 1. Tally up the search result provinces right out of your matched_points list
    from collections import Counter
    search_counts = Counter([row[9].strip() for row in matched_points if len(row) > 9 and row[9]])
        
    # 2. Process and load the province boundary lines in memory
    if os.path.exists(provinces_json_path):
        with open(provinces_json_path, "r", encoding="utf-8") as f:
            provinces_data = json.load(f)
        
        # In-memory loop to add the numeric tallies to the shape copy
        features = provinces_data.get("features", [provinces_data] if isinstance(provinces_data, dict) else [])
        for feature in features:
            props = feature.setdefault("properties", {})
            geo_name = props.get("Name") or props.get("province_name")
            if geo_name:
                count = search_counts.get(geo_name.strip(), 0)
                # QUICK & DIRTY TRICK: Bake a line break right into the string value!
                props["search_count"] = f"<br>{count}"
            else:
                props["search_count"] = "<br>0"
                
        # Pass to Folium
        folium.GeoJson(
            provinces_data, 
            name="Provinces (200CE)", 
            show=True, 
            overlay=True, 
            control=True,
            style_function=lambda feature: {"color": "#544CA4", "weight": 2, "fillColor": "#1a53ff", "fillOpacity": 0.05},
            tooltip=folium.GeoJsonTooltip(
                fields=["Name", "search_count"], 
                # The line-break forces the table column to collapse, snapping the numbers closer!
                aliases=["Province:", "Matching<br>Inscriptions:"], 
                localize=True,
                style="font-family: sans-serif; font-size: 13px; padding: 8px;"
            )
        ).add_to(mymap)

        # -------------------------------------------------------------
        # THE MAGIC INJECTOR FOR THE TABLE CELLS
        # -------------------------------------------------------------
        # Folium writes a specific ID for its tooltips. We inject a quick CSS patch 
        # to guarantee the data cells are aligned left and not spaced miles apart.
        mymap.get_root().header.add_child(folium.Element("""
            <style>
                .leaflet-tooltip table td {
                    text-align: left !important;
                    padding-right: 15px !important;
                }
            </style>
        """))
    # -------------------------------------------------------------
    # FIND AREA LAYER AND FIND SPOT LAYER
    # -------------------------------------------------------------
    # Layer 1: OFF BY DEFAULT (show=False) for the GeoJSON shapes
    range_layer = folium.FeatureGroup(name="Show Find Area for Approximate Findspots", show=False)
    
    # Layer 2: ON BY DEFAULT (show=True) for the standard pins
    inscriptions_layer = folium.FeatureGroup(name="Inscriptions", show=True)

    # -------------------------------------------------------------
    # CLUSTER & POPULATE COORD BUCKETS FOR PINS
    # -------------------------------------------------------------
    coord_buckets = {}
    for row in matched_points:
        lat, lon = row[1], row[2]
        if lat is not None and lon is not None:
            try:
                coord_key = (float(lat), float(lon))
                if coord_key not in coord_buckets:
                    coord_buckets[coord_key] = []
                coord_buckets[coord_key].append(row)
            except (ValueError, TypeError):
                continue 

        # -------------------------------------------------------------
        # PASS 1: POPULATE THE INDEPENDENT RANGE LAYER (IF GEOJSON EXISTS)
        # -------------------------------------------------------------
        geo_json_str = row[13]
        f_id = row[0]
        if geo_json_str:
            try:
                polygon_geometry = json.loads(geo_json_str)
                folium.GeoJson(
                    polygon_geometry,
                    style_function=lambda feature: {
                        "color": "#7f8c8d",       # Muted slate gray border
                        "weight": 2,
                        "dashArray": "6, 6",      # Clear dashes to signify uncertainty bounds
                        "fillColor": "#95a5a6",   # Soft transparent center fill
                        "fillOpacity": 0.15,
                    },
                    tooltip=f"Uncertainty Bounds for Inscription ID: {f_id}"
                ).add_to(range_layer)
            except Exception:
                pass
    # -------------------------------------------------------------
    # PASS 2: GENERATE THE PINS FOR THE INSCRIPTION LAYER
    # -------------------------------------------------------------
    for (lat, lon), rows in coord_buckets.items():
        overlap_count = len(rows)
        popup_html = ""
        
        is_bucket_approximate = any(row[12] == 1 for row in rows)
        
       # Global Warning Banner for approximate coordinates
        if is_bucket_approximate:
            popup_html += """
            <h3 style="
                color: #000000; 
                margin: 0 0 10px 0; 
                font-weight: bold; 
                text-align: center; 
                font-size: 13px;
            ">
                WARNING: APPROXIMATE FINDSPOT
            </h3>
            """
        if overlap_count > 1:
            bg_color = "#f2f4f4" if is_bucket_approximate else "#f0f4ff"
            text_color = "#2c3e50" if is_bucket_approximate else "#001140"
            border_color = "#bdc3c7" if is_bucket_approximate else "#d0daff"
            popup_html += f"<div style='background-color:{bg_color}; color:{text_color}; padding:5px; margin-bottom:8px; border:1px solid {border_color}; border-radius:4px; font-weight:bold; text-align:center; font-size:12px;'>{overlap_count} Inscriptions at this Location</div>"
        
        for idx, row in enumerate(rows, 1):
            f_id, _, _, ref_text, seq_id, support_id, support_name, dist_tit, num_ins = row[:9]
            province_name = row[9] if len(row) > 9 else "N/A"
            place_name_val = row[10] if len(row) > 10 else None
            pleiades_id_val = row[11] if len(row) > 11 else None
            is_approx = row[12]

            ins_count = num_ins if num_ins is not None else "N/A"
            sequence = seq_id if seq_id is not None else "N/A"
            province = province_name if province_name is not None else "N/A"
            place = place_name_val if place_name_val is not None else "N/A"
            
            if pleiades_id_val and str(pleiades_id_val).strip():
                clean_pleiades_id = str(pleiades_id_val).strip()
                pleiades_link = f'<a href="https://pleiades.stoa.org/places/{clean_pleiades_id}" target="_blank">{clean_pleiades_id}</a>'
            else:
                pleiades_link = 'N/A'
                
            ref_link = f'<a href="https://edcs.hist.uzh.ch/en/search?edcs-id={ref_text}" target="_blank">{ref_text}</a>' if ref_text else 'N/A'
            report_url = f"https://maximinusthraxdatabaseui.streamlit.app/?ins_id={f_id}"

            if overlap_count > 1:
                item_border = "#7f8c8d" if is_approx == 1 else "#001140"
                popup_html += f"<div style='border-left: 3px solid {item_border}; padding-left: 8px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed #ccc;'> "
                popup_html += f"<span style='font-size:11px; font-weight:bold; color:#555;'>Record {idx} of {overlap_count}</span>"
                if is_approx == 1:
                    popup_html += " <span style='font-size:10px; color:#000000; font-weight:bold;'>(APPROXIMATE)</span>"
                popup_html += "<br>"

            if overlap_count == 1 and is_approx == 1:
                popup_html += "<span style='font-size: 11px; color: #000000; font-weight: bold;'>Coordinates represent the geometric center of the area in which the findspot is located </span><br><br>"

            popup_html += (
                f"<b>Inscription ID:</b> <a href='{report_url}' target='_blank'>{f_id}</a> | <b>Ref:</b> {ref_link}<br>"
                f"<b>Number of Inscriptions:</b> {ins_count} | <b>Sequence ID:</b> {sequence}<br>"
                f"<b>Province:</b> {province}<br>"
                f"<b>Place:</b> {place} | <b>Pleiades:</b> {pleiades_link}"
            )
            
            if support_id in (1, 2):
                popup_html += "<br><b>Milestone</b>"
                info = road_links_dict.get(f_id, {'roads': []})
                if info['roads']:
                    road_name = ", ".join(list(set(r[0] for r in info['roads'] if r[0])))
                    popup_html += f"<br><b>road segment:</b> {road_name if road_name else 'N/A'}"
                    links = [f'<a href="https://itiner-e.org/?id={r[1]}" target="_blank">itiner-e.org/?id={r[1]}</a>' for r in info['roads'] if r[1]]
                    popup_html += f"<br><b>itiner-e link to road:</b> {', '.join(links) if links else 'N/A'}"
                else:
                    popup_html += "<br><b>road segment:</b> N/A<br><b>itiner-e link to road:</b> N/A"
            else:
                popup_html += f"<br><b>distributio titulorum:</b> {dist_tit if dist_tit else 'N/A'}<br><b>support:</b> {support_name if support_name else 'N/A'}"
            
            if overlap_count > 1:
                popup_html += "</div>"

        # Tooltip tracking label
        if overlap_count > 1:
            tooltip_label = f"{overlap_count} entries here (Contains Approximate Locations)" if is_bucket_approximate else f"{overlap_count} inscriptions here"
        else:
            tooltip_label = f"ID: {rows[0][0]} (Approximate Location)" if is_bucket_approximate else f"ID: {rows[0][0]}"

        # -------------------------------------------------------------
        # COLOR ASSIGNMENT (Grey vs Classic Blue Pins based on approximate_location)
        # -------------------------------------------------------------
        if overlap_count > 1:
            size = 22
            border_color = "#2c3e50" if is_bucket_approximate else "#001140"
            fill_color = "#7f8c8d" if is_bucket_approximate else "#1a53ff"
            
            icon_html = f"""
                <div style="background-color: {fill_color}; border: 2px solid {border_color}; color: #ffffff; 
                            border-radius: 50%; width: {size}px; height: {size}px; font-size: 11px; font-weight: bold; 
                            display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 5px rgba(0,0,0,0.4);">
                    {overlap_count}
                </div>
            """
        else:
            size = 14
            border_color = "#34495e" if is_bucket_approximate else "#002fa7"
            fill_color = "#95a5a6" if is_bucket_approximate else "#33b5e5"
            
            icon_html = f"""
                <div style="background-color: {fill_color}; border: 2px solid {border_color}; 
                            border-radius: 50%; width: {size}px; height: {size}px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);"></div>
            """

        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(icon_size=(size, size), icon_anchor=(size // 2, size // 2), html=icon_html),
            popup=folium.Popup(f"<div style='max-height: 280px; overflow-y: auto;'>{popup_html}</div>", min_width=340, max_width=480),
            tooltip=tooltip_label
        ).add_to(inscriptions_layer)

    # Add both layers separately to the map canvas
    range_layer.add_to(mymap)
    inscriptions_layer.add_to(mymap)

    # Render Layer Control Panel
    if not st.session_state.get("map_screenshot_mode", False):
        folium.LayerControl(collapsed=False).add_to(mymap)
    else:
        # If snapshot mode is on, tell the map object itself to drop the zoom buttons
        mymap.options['zoomControl'] = False

    st.session_state.trigger_map_html = mymap._repr_html_()
    
# =========================================================
# APPLICATION CORE GRAPHICAL INTERFACE
# =========================================================

query_params = st.query_params

# Inscription hyperlink
if "ins_id" in query_params:
    url_id = query_params["ins_id"]
    if url_id.isdigit():
        st.query_params.clear() 
        fetch_metadata_by_id(url_id)
        
# Person hyperlink
elif "person_id" in query_params:
    url_per_id = query_params["person_id"]
    if url_per_id.isdigit():
        st.query_params.clear() 
        generate_person_report(url_per_id)
        
# Institutions/Groups/Military Units hyperlink
if "collective_id" in st.query_params:
    selected_collective_id = st.query_params["collective_id"]
    
    # Optional: Clear other search states so they don't clash
    st.session_state["active_search_has_run"] = True
    st.session_state["csv_mode"] = "ids"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pull the Collective Name so you can notify the user what they searched for
        cursor.execute("SELECT collective_name FROM collectives WHERE collective_id = ?;", (selected_collective_id,))
        coll_name_row = cursor.fetchone()
        collective_title = coll_name_row[0] if coll_name_row else f"ID {selected_collective_id}"
        
        # Pull all Inscription IDs that belong to this specific group
        cursor.execute("""
            SELECT inscription_id 
            FROM inscriptions_and_collectives 
            WHERE collective_id = ?;
        """, (selected_collective_id,))
        
        # Save these IDs into session state so your dashboard updates automatically!
        matched_ids = [row[0] for row in cursor.fetchall()]
        st.session_state.active_inscription_ids = matched_ids
        
        # Define what displays in your main reports frame
        if matched_ids:
            st.session_state.search_results = f"#### Filtered by Institution/Group: **{collective_title}**\nFound {len(matched_ids)} matching inscriptions."
        else:
            st.session_state.search_results = f"No inscriptions found linked to group: **{collective_title}**."
            
        conn.close()
    except Exception as e:
        st.error(f"Error querying collective group filter: {e}")
        
st.markdown("## Maximinus Thrax Database Βrowser")
# Welcome Text & Instructions
with st.expander("Click to View Site Instructions / Welcome Text", expanded=False, key="welcome_instructions_expander"):
    st.markdown("""
## How to Use

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

# =========================================================
# MAIN SEARCH FUNCTIONS
# =========================================================
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
        st.session_state["inputs_are_dirty"] = False  # Clear the dirty flag!
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
            st.rerun()

with col_s4:
    if st.session_state.person_matches:
        options_list = [f"{row[1]} (ID: {row[0]})" for row in st.session_state.person_matches]
        selected_option = st.selectbox(
            "Select Person:", 
            options_list, 
            key="person_select_input",
            on_change=reset_map_and_search_flags
        )
        
        if st.button("Generate Person Report", key="btn_person_select_submit", use_container_width=True, type="primary"):
            st.session_state["last_searched_person"] = selected_option
            st.session_state["csv_mode"] = "ids"
            st.session_state["active_search_has_run"] = True
            st.session_state["inputs_are_dirty"] = False
            extracted_id = selected_option.split("(ID: ")[-1].replace(")", "").strip()
            generate_person_report(extracted_id)
            st.rerun()
    else:
        pid_input_var = st.text_input(
            "Person Selector:", 
            placeholder="Select from the list", 
            key="person_report_input",
            on_change=reset_map_and_search_flags
        )
        
        if st.button("Generate Person Report", key="btn_person_text_submit", use_container_width=True, type="primary"):
            if pid_input_var.strip():
                st.session_state["last_searched_person"] = pid_input_var.strip()
                st.session_state["active_search_has_run"] = True
                st.session_state["inputs_are_dirty"] = False
                generate_person_report(pid_input_var)
                st.rerun()
                
# =========================================================
# ADVANCED SEARCH
# =========================================================
with st.expander("Expand/Collapse Advanced Search", expanded=False):
    st.markdown("### Advanced Search")
    
   # Text search assigned to its own private, isolated row context
    f_text = st.text_input(
        "Advanced Text Search (Boolean Logic Operators Allowed):", 
        placeholder="e.g. Maximinus AND legatus",
        on_change=reset_map_and_search_flags
    )
    
    st.markdown("---")
    st.markdown("### Filters")
    st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    # =========================================================================
    # COLUMN 1: Inscription Metadata
    # =========================================================================
    with col1:
        st.markdown("#### Based on Inscription Metadata")
        
        relevance_options = [
            "All inscriptions regardless of relevance",
            "Relevant",
            "Not Relevant"
        ]
        f_rel = st.selectbox("Relevance to Maximinus Thrax:", relevance_options, on_change=reset_map_and_search_flags)
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
    # =========================================================================
    # COLUMN 2: People and Institutions
    # =========================================================================
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

    # =========================================================================
    # COLUMN 3: Later Modifications / Reuse
    # =========================================================================
    with col3:
        st.markdown("#### Based on Later Modifications / Reuse")
        
        intervention_options = [
            "All inscriptions regardless of presence of later intervention",
            "Intervention present",
            "No later intervention"
        ]
        f_inter_status = st.selectbox("Intervention Status:", intervention_options, on_change=reset_map_and_search_flags)
        f_interv_meth = st.multiselect("Method of Intervention:", [opt for opt in get_filter_options("methods", "method_description") if opt != "All"], on_change=reset_map_and_search_flags)
        f_interv_ext = st.multiselect("Extent of Intervention:", [opt for opt in get_filter_options("extent", "extent_description") if opt != "All"], on_change=reset_map_and_search_flags)
        f_interv_tgt = st.multiselect("Target of Intervention:", [opt for opt in get_filter_options("targets", "target_description") if opt != "All"], on_change=reset_map_and_search_flags)
    # =========================================================================
    # ACTION BUTTONS ROW (Streamlined: Execution & Standalone SQL Compilation)
    # =========================================================================
    col_btn1, col_btn2 = st.columns([1, 1])

    with col_btn1:
        if st.button("Execute Advanced Search", key="btn_advanced_filter_search", use_container_width=True, type="primary"):
            st.session_state["csv_mode"] = "advanced"
            st.session_state["active_inscription_ids"] = []
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
            st.download_button(
                label="Download SQL Query",
                data=dynamic_sql_query,
                file_name="search_results_compiled_query.sql",
                mime="text/plain",
                use_container_width=True,
                key="btn_download_raw_sql_query"
            )
        else:
            st.button(
                label="Download SQL Query",
                key="btn_advanced_sql_disabled",
                use_container_width=True,
                disabled=True,
                help="Make a search first to unlock SQL query generation."
            )
# =========================================================
# UNIVERSAL INPUT MATCH VALIDATION (ANTI-IDIOT GUARDRAIL)
# =========================================================
# Pair each live widget key with its corresponding "officially searched" anchor
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
    # Only evaluate if the widget currently exists in the live session state pass
    if widget_key in st.session_state:
        current_value = str(st.session_state[widget_key]).strip()
        last_executed_value = str(st.session_state.get(anchor_key, "")).strip()
        
        # If the user has typed/selected something but skipped hitting its execution button
        if current_value != last_executed_value:
            any_input_has_unsearched_changes = True
            break


# =========================================================
# RENDER CSV AND MAP BUTTONS
# =========================================================
col_exp_left, col_exp_mid, col_exp_right = st.columns([1.5, 1.5, 1.5])

# Check if ANY valid search results are ready (either basic list or advanced search state)
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

        st.download_button(
            label="Export Results to CSV",
            data=global_csv_string,
            file_name="search_results_export.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_global_results_csv_export"
        )
        
    with col_exp_mid:
        if st.button("Generate Map", key="global_map_btn", use_container_width=True, type="primary"):
            generate_active_map()
            st.rerun()

else:
    with col_exp_left:
        st.button(
            label="Export Results to CSV",
            key="global_csv_disabled_footer_csv",
            use_container_width=True,
            disabled=True,
            help="Make a search before exporting search results."
        )
        
    with col_exp_mid:
        st.button(
            label="Generate Map",
            key="global_map_disabled_footer_map",
            use_container_width=True,
            disabled=True,
            help="Make a search before mapping search results."
        )

# =========================================================
# MAP VIEWER (Always Visible)
# =========================================================

with st.expander("Expand/Collapse Interactive Map", expanded=True):
    # 1. By setting vertical_alignment="center", Streamlit forces the center line of both columns to match perfectly
    btn_col, chk_col, spacer = st.columns([1.3, 1.5, 5], vertical_alignment="center")
    
    with btn_col:
        # Export button comes first on the far left
        export_clicked = st.button("💾 Export to PNG", use_container_width=True)
    with chk_col:
        # Checkbox follows immediately right after it, styled with the matching button font stack
        st.markdown(
            """
            <style>
                .matching-font-label [data-testid="stCheckbox"] label p {
                    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
                    font-size: 14px !important;
                    color: #31333F !important;
                }
            </style>
            <div class="matching-font-label">
            """, 
            unsafe_allow_html=True
        )
        screenshot_mode = st.checkbox("Hide map controls")
        st.markdown('</div>', unsafe_allow_html=True)
        
    # Force map data regeneration behind the scenes when the checkbox changes state
    if "map_screenshot_mode" not in st.session_state or st.session_state.map_screenshot_mode != screenshot_mode:
        st.session_state.map_screenshot_mode = screenshot_mode
        if st.session_state.get("trigger_map_html"):
            generate_active_map()

    # 2. Inject the html2canvas engine if the export button is pressed
    if export_clicked and st.session_state.get("trigger_map_html"):
        st.markdown(
            """
            <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
            <script>
                var iframe = document.querySelector('iframe');
                if (iframe) {
                    var mapCanvas = iframe.contentWindow.document.body;
                    html2canvas(mapCanvas, {
                        useCORS: true,
                        allowTaint: true,
                        backgroundColor: null
                    }).then(function(canvas) {
                        var link = document.createElement('a');
                        link.download = 'historical_map_export.png';
                        link.href = canvas.toDataURL('image/png');
                        link.click();
                    });
                }
            </script>
            """,
            unsafe_allow_html=True
        )

    # 3. Output the map payload frame
    if st.session_state.get("trigger_map_html"):
        st.components.v1.html(st.session_state.trigger_map_html, height=700, scrolling=True)
    else:
        st.info("No map generated yet. If you have yet to make a search, do so. Then click the 'Generate Map' button to plot inscriptions matching your query on a map.")


# =========================================================
# SEARCH RESULTS LIGHTBOX CONTAINER
# =========================================================
with st.container(height=520, border=True):
    raw_results = st.session_state.search_results

    # 1. Clean standard line breaks
    clean_text = raw_results.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Break the results apart by double-newlines to isolate the text blocks
    blocks = clean_text.split("\n\n")

    # This is our light switch. It starts turned OFF.
    process_this_block = False

    for block in blocks:
        cleaned_block = block.strip()
        
        # Check if the block contains any lines starting with 3+ dashes
        lines = cleaned_block.split("\n")
        has_dangerous_dashes = any(
            line.strip().startswith("---") for line in lines
        )

        # 1. KILL switch: Turn processing OFF if we hit any downstream metadata or spelling section
        if any(header in cleaned_block for header in ["Nonstandard Spellings:", "Context:", "Support:", "Dating:", "Material:", "Province:", "Place:", "Bibliography:", "Persons:"]):
            process_this_block = False

        # 2. Run the formatting ONLY on the inner epigraphic text blocks
        if process_this_block:
            block = convert_markdown_bold_to_edh(block)
      
        # 3. START switch: Turn processing ON for the NEXT loop iteration
        if "Inscription Text:" in cleaned_block:
            process_this_block = True

        # 4. EXPLICIT INTERCEPTION: Is this block JUST the header itself?
        if cleaned_block == "**Inscription Text:**":
            # Force standard markdown rendering so the asterisks naturally bold!
            st.markdown(cleaned_block)
            
        # 5. Handle all other epigraphic display blocks
        elif (
            "RIGHT:" in cleaned_block
            or "------ /" in cleaned_block
            or has_dangerous_dashes
            or process_this_block  # This catches the raw text lines cleanly
        ):
            html_block = block.replace("\n", "<br>")
            st.markdown(
                f'<div style="font-size:16px; font-weight:normal; margin-bottom:1rem;">{html_block}</div>',
                unsafe_allow_html=True,
                )
        else:
            # For everything else (Context, Material, etc.), keep regular Markdown active
            st.markdown(block)

