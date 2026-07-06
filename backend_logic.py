"""
Jiatong Wang | SAPIENZA BA THESIS DATABASE GUI BACKEND
--------------------------------------------------------------------
Purpose: This file contains the constants and functions called in the GUI; they query a relational database in SQLite. 
        
NOTES
--------------------------------------------------------------------


PORTABILITY:
--------------------------------------------------------------------
To Future Me: This script provides the db queries and other constants and functions for the streamlit interface
It is somewhat reusable as long as the db schema that those queries rely on stay the same...

EXCEPT FOR the logic that determines whether an erasure is relevant to Maximinus Thrax (this is hardcoded to exclude any inscription
linked to the person_id 50,i.e. Licinnius Serenianus's monuments which are erased due to a separate memory sanction against him;on the
inscriptions of Licinnius Serenianus which we have, the name of Maximinus Thrax and his name are never erased. Other than the milestones
of Licinnius Serenianus, we do not have other inscriptions relevant to Maximinus Thrax which suffered an erasure as the result of a 
different memory sanction campaign therefore for this corpus. Therefore, in this corpus, excluding all monuments linked to the person_id
person_id 50 from being counted as a relevant erasure can safely exclude ALL erasures ON monuments relevevant to Maximinus Thrax
BUT ARE NOT actually part of the memory sanction campaign against him)

AND EXCEPT FOR the following items which ARE hardcoded

HARDCODED STUFF
--------------------------------------------------------------------
In get_inscription_report the text output for each method_id and extent_id are hardcoded, instead of being dynamically fetched from a field in the database. 
IF you reuse this, make sure to change/check the section.


FURHTERMORE, AS AFORMENTIONED, CHECK ALL LOGIC THAT RELIES ON FILTERING BY PERSON_ID = 50 or PERSON_ID != 50

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
db_path = os.path.join(BASE_DIR, "maximinus_thrax.db")

optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
provinces_json_path = os.path.join(BASE_DIR, "roman_provinces.json") 





def get_inscription_report(cursor, inscription_id):

    sql_main = """
        SELECT 
            mt.inscription_id, mt.inscription_ref, mt.line_ref, 
            mt.inscription_text_formatted, mt.corrected_lemmas, mt.dating, mt.expanded_bibliography,
            mt.object_id, ct.context_name, s.support_name, m.material_name, pr.province_name, 
            pl.place_name, pl.pleiades_id, r_roads.road_name, r_roads.itinere_id, st.status_tituli_name
        FROM "Max_Thrax" mt
        LEFT JOIN "context_types" ct         ON mt.context_id = ct.context_id
        LEFT JOIN "support" s                 ON mt.support_id = s.support_id
        LEFT JOIN "materials" m              ON mt.material_id = m.material_id
        LEFT JOIN "provinces" pr             ON mt.province_id = pr.province_id
        LEFT JOIN "places" pl                ON mt.place_id = pl.place_id
        LEFT JOIN "inscription_and_road" iar ON mt.inscription_id = iar.inscription_id
        LEFT JOIN "itiner_e_roads" r_roads   ON iar.itiner_e_road_id = r_roads.itiner_e_road_id
        LEFT JOIN "status_tituli" st         ON mt.status_tituli_id = st.status_tituli_id
        WHERE mt.inscription_id = ?;
    """
    
    sql_tm = 'SELECT TM_number FROM "inscriptions_and_TM_numbers" WHERE inscription_id = ?;'
    
    sql_distributio = """
        SELECT DISTINCT vd_sub.virorum_distributio
        FROM "inscriptions_and_persons" ip_sub
        JOIN "persons_and_virorum_distributio" pvd_sub ON ip_sub.person_id = pvd_sub.person_id
        JOIN "virorum_distributio" vd_sub ON pvd_sub.virorum_distributio_id = vd_sub.virorum_distributio_id
        WHERE ip_sub.inscription_id = ?
        UNION
        SELECT DISTINCT vd_sub.virorum_distributio
        FROM "inscriptions_and_collectives" ic_sub
        JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
        JOIN "virorum_distributio" vd_sub ON col_sub.virorum_distributio = vd_sub.virorum_distributio_id
        WHERE ic_sub.inscription_id = ?;
    """
    
    sql_persons = """
        SELECT p.person_id, p.person_name 
        FROM "persons" p 
        JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id 
        WHERE ip.inscription_id = ?;
    """
    
    sql_collectives = """
        SELECT c.collective_id, c.collective_name 
        FROM "collectives" c
        JOIN "inscriptions_and_collectives" ic ON c.collective_id = ic.collective_id
        WHERE ic.inscription_id = ?;
    """
    
    sql_siblings = 'SELECT inscription_id, sequence_id, inscription_ref, line_ref FROM "Max_Thrax" WHERE object_id = ? ORDER BY sequence_id ASC;'
    
    sql_interventions = """
        SELECT i.inscription_id, i.intervention_id, i.intervention_index, i.note, 
               iam.method_id, e.extent_description, m.method_description
        FROM "interventions_and_inscriptions" i
        JOIN "interventions" iam ON i.intervention_id = iam.intervention_id
        LEFT JOIN "extent" e ON iam.extent_id = e.extent_id
        LEFT JOIN "methods" m ON iam.method_id = m.method_id
        WHERE i.inscription_id IN (SELECT inscription_id FROM "Max_Thrax" WHERE object_id = ?)
          AND i.role_id = 1
          AND iam.method_id <> 1;
    """

    cursor.execute(sql_main, (inscription_id,))
    main_row = cursor.fetchone()
    if not main_row:
        return "No inscription data found."

    (ins_id, ins_ref, line_ref, text_formatted, lemmas, dating, biblio,
     obj_id, context, support, material, province, place, pleiades_id, 
     road_name, itinere_id, status_tituli) = main_row

    cursor.execute(sql_tm, (inscription_id,))
    tm_numbers = [r[0] for r in cursor.fetchall() if r[0]]
    
    cursor.execute(sql_distributio, (inscription_id, inscription_id))
    distributio_items = [r[0] for r in cursor.fetchall() if r[0]]

    cursor.execute(sql_persons, (inscription_id,))
    persons = cursor.fetchall()

    cursor.execute(sql_collectives, (inscription_id,))
    collectives = cursor.fetchall()

    # --- 3. STRING COMPOSITION ---
    report = []

    # HEADING
    edcs_link = f"[{ins_ref}](https://edcs.hist.uzh.ch/monument/{ins_ref.replace('EDCS-', '')})" if ins_ref else ""
    line_display = f" {line_ref}" if (ins_ref and line_ref) else (line_ref if line_ref else "")
    ref_segment = f"{edcs_link}{line_display}" if (ins_ref or line_ref) else "N/A"
    tm_links = ", ".join([f"[{tm}](https://www.trismegistos.org/text/{tm})" for tm in tm_numbers]) if tm_numbers else "N/A"
    obj_link = f"[{obj_id}](?obj_id={obj_id})" if obj_id else "N/A"
    
    report.append(f"**Quick Reference:** {ref_segment} | **TM Number:** {tm_links} | **Inscription ID:** [{ins_id}](?ins_id={ins_id}) | **Object ID:** {obj_link}\n")

    report.append("**Inscription Text:**\n")
    report.append(f"{text_formatted.strip() if text_formatted else 'N/A'}\n")

    report.append(f"**Nonstandard Spellings:** {lemmas if lemmas else 'N/A'}\n")
    report.append(f"**Context:** {context if context else 'N/A'}\n")
    report.append(f"**Support:** {support if support else 'N/A'}\n")
    report.append(f"**Dating:** {dating if dating else 'N/A'}\n")
    report.append(f"**Material:** {material if material else 'N/A'}\n")
    report.append(f"**Status Tituli:** {status_tituli if status_tituli else 'N/A'}\n")
    
    report.append(f"**Distributio Virorum:** {', '.join(distributio_items) if distributio_items else 'N/A'}\n")
    
    p_links = ", ".join([f"[{p_name}](?person_id={p_id}) (id: {p_id})" for p_id, p_name in persons]) if persons else "N/A"
    report.append(f"**Persons:** {p_links}\n")

    c_links = ", ".join([f"[{c_name}](?collective_id={c_id})" for c_id, c_name in collectives]) if collectives else "N/A"
    report.append(f"**Institutions / Groups / Military Units:** {c_links}\n")
    
    report.append(f"**Province:** {province if province else 'N/A'}\n")

    place_display = f"[{place}](https://pleiades.stoa.org/places/{pleiades_id})" if pleiades_id else (place if place else "N/A")
    report.append(f"**Place:** {place_display}\n")

    road_display = f"[{road_name if road_name else 'Unnamed Road'}](https://itiner-e.org/?id={itinere_id})" if itinere_id else "N/A"
    report.append(f"**Associated Roman Road (Itinere):** {road_display}\n")

    biblio_clean = f"\n* {biblio.strip().replace('\n', '\n* ')}" if biblio else " N/A"
    report.append(f"**Bibliography:** {biblio_clean}\n")

    # OBJECTS AND INSCRIPTIONS
    if obj_id:
        report.append("\n---\n\n")  # Push the divider to cleanly isolate metadata from linked layout details
        cursor.execute(sql_siblings, (obj_id,))
        siblings = cursor.fetchall()
        
        report.append(f"#### {len(siblings)} inscriptions on object:\n")
        for s_id, s_seq, s_ref, s_lref in siblings:
            curr_tag = " [current inscription]" if s_id == ins_id else ""
            line_tag = f" {s_lref}" if s_lref else ""
            report.append(f"* {s_seq}. {s_ref}{line_tag}{curr_tag} (id: [{s_id}](?ins_id={s_id}))")
        report.append("\n")

        # INTERVENTIONS
        cursor.execute(sql_interventions, (obj_id,))
        interventions = cursor.fetchall()
        
        report.append("#### Interventions (Later Modifications / Reuse)\n")
        
        for sib_id, _, sib_ref, sib_lref in siblings:
            sib_line = f" {sib_lref}" if sib_lref else ""
            curr_tag = " [current inscription]" if sib_id == ins_id else ""
            item_interv = [i for i in interventions if i[0] == sib_id]
            
            if not item_interv:
                report.append(f"**{sib_ref}{sib_line}{curr_tag} :** _no interventions_")
            else:
                report.append(f"**{sib_ref}{sib_line}{curr_tag} :** {len(item_interv)} intervention(s)")
                for _, interv_id, idx, note, m_id, ext_desc, meth_desc in item_interv:
                    idx_lbl = idx if idx else 1
                    note_str = f" {note}" if note else ""
                    
                    if m_id == 2:
                        # Safely extracted string block to prevent compilation failures
                        sql_targets = """
                            SELECT t.target_description 
                            FROM interventions_and_targets iat 
                            JOIN targets t ON iat.target_id = t.target_id 
                            WHERE iat.intervention_id = ?
                        """
                        cursor.execute(sql_targets, (interv_id,))
                        targets = ", ".join([r[0] for r in cursor.fetchall()])
                        report.append(f"  * _intervention {idx_lbl} :_ {ext_desc or ''} {meth_desc or ''} of inscription, targeting {targets}")
                    elif m_id == 3:
                        report.append(f"  * _intervention {idx_lbl} :_ reuse of monument{note_str}")
                    elif m_id == 4:
                        report.append(f"  * _intervention {idx_lbl} :_ monument damage{note_str}")
                    elif m_id == 5:
                        report.append(f"  * _intervention {idx_lbl} :_ restoration of erased text{note_str}")
                    elif m_id == 6:
                        report.append(f"  * _intervention {idx_lbl} :_ reuse as support for new inscription{note_str}")
                    else:
                        report.append(f"  * _intervention {idx_lbl} :_ unknown intervention method ({m_id})")
        report.append("\n")

    return "\n".join(report)



#SETUP FOR STOPPING PEOPLE FROM TRYING TO GENERATE A MAP OR EXPORT CSV BEFORE CLICKING SEARCH AGAIN AND BEING MAD ABOUT HAVING WRONG RESULTS
def reset_map_and_search_flags():
    st.session_state["active_search_has_run"] = False
    st.session_state["trigger_map_html"] = None

#SETUP FOR CSV EXPORT
def generate_bulk_search_csv(cursor):
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
                    FROM (SELECT intervention_id, note, intervention_index as idx, inscription_id, role_id FROM "interventions_and_inscriptions") i
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
         
    
#SETUP FOR SQL QUERY EXPORT

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

    return f"""
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
    COALESCE(
                (
                    SELECT GROUP_CONCAT(
                        'intervention ' || idx || ' : ' || CASE WHEN iam.method_id = 2 THEN COALESCE(e2.extent_description, '') || ' ' || COALESCE(m2.method_description, '') || ' of inscription' WHEN iam.method_id = 3 THEN 'reuse of monument ' || COALESCE(i.note, '') WHEN iam.method_id = 4 THEN 'monument damage ' || COALESCE(i.note, '') ELSE '' END, '; '
                    )
                    FROM (SELECT intervention_id, note, intervention_index as idx, inscription_id, role_id FROM "interventions_and_inscriptions") i
                    JOIN "interventions" iam ON i.intervention_id = iam.intervention_id
                    LEFT JOIN "extent" e2 ON iam.extent_id = e2.extent_id
                    LEFT JOIN "methods" m2 ON iam.method_id = m2.method_id
                    WHERE i.inscription_id = mt.inscription_id AND i.role_id = 1 AND iam.method_id <> 1
                ),
                'no interventions'
            ) AS interventions,
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



def convert_markdown_bold_to_underline(text):
    """Tracks asterisks across lines exactly like a Markdown parser,

    converting **text** into underlined text(!), even if it straddles lines.
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
                # Underline each character of the EDH mark too
                for char in "(!)":
                    output.append(char + "\u0332")
                in_bold = False
            i += 2
        else:
            if in_bold:
                output.append(text[i] + "\u0332")
            else:
                output.append(text[i])
            i += 1
    if in_bold:
        for char in "(!)":
            output.append(char + "\u0332")
    return "".join(output)

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


# KEY WORD OR PHRASE SEARCH
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

        # SEE IF ANY GROUP/INSTITUTION/MILITARY UNIT NAME MATCHES THE QUERY EXACTLY AND OUTPUT ALL INSCRIPTIONS LINKED TO IT
        if is_unit_query:
            raw_tokens = re.findall(r'\w+', converted_input.lower())

            expanded_token_clusters = []
            for token in raw_tokens:
                # Direct string normalization for accurate orthography matches
                token_u = token.replace('v', 'u')
                token_v = token.replace('u', 'v')
                token_variants = list(set([token, token_u, token_v]))
                expanded_token_clusters.append(token_variants)
    
            possible_phrases = []
            for combination in itertools.product(*expanded_token_clusters):
                phrase_regex = r'\b' + r'\s+'.join(re.escape(word) for word in combination) + r'\b'
                possible_phrases.append(phrase_regex)
                
            cursor.execute("SELECT collective_id, collective_name_search FROM collectives;")
            all_collectives = cursor.fetchall()
            
            c_ids = []
            for col_id, col_search in all_collectives:
                if not col_search:
                    continue
                    
                col_search_lower = col_search.lower()
                
                if any(re.search(pattern, col_search_lower) for pattern in possible_phrases):
                    c_ids.append(col_id)
                    
            if c_ids:
                c_sql = f"""
                    SELECT mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
                    (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') 
                     FROM persons p JOIN inscriptions_and_persons ip ON p.person_id = ip.person_id 
                     WHERE ip.inscription_id = mt.inscription_id)
                    FROM "Max_Thrax" mt 
                    JOIN "inscriptions_and_collectives" ic ON mt.inscription_id = ic.inscription_id
                    WHERE ic.collective_id IN ({','.join(['?']*len(c_ids))});
                """
                cursor.execute(c_sql, c_ids)
                text_rows = cursor.fetchall()
        
        # SEARCH FOR OTHER INFLECTED FORMS OF THE QUERY
        else:
            clean_query = clean_epigraphic_text(user_input).strip().lower()
            
            # Formulate variants natively to guarantee cross-matching over orthographical differences
            query_u = clean_query.replace('v', 'u')
            query_v = clean_query.replace('u', 'v')
            synonyms = list(set([clean_query, query_u, query_v]))
            
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
                
                # Check for hits in raw variants
                if text_stripped and any(syn in text_stripped.lower() for syn in synonyms):
                    text_rows.append(base_data)
                else:
                    fallback_rows.append(base_data + ("spelling_variant_cluster", clean_query))
            
            if not text_rows and not fallback_rows:
                continuous_term = user_input.lower().replace(" ", "")
                continuous_term = re.sub(r'[\[\]\(\)\.\?\-\/\u0323⟦⟧〚〛\d!\{\}<>´`\^~]', '', continuous_term)
                
                if continuous_term:
                    continuous_term_u = continuous_term.replace('v', 'u')
                    continuous_term_v = continuous_term.replace('u', 'v')
                    
                    continuous_sql = """
                        SELECT mt.inscription_id, mt.inscription_text, mt.inscription_ref, mt.line_ref, mt.further_bibliography,
                               (SELECT GROUP_CONCAT(p.person_name || ' (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = mt.inscription_id) AS linked_persons
                        FROM "Max_Thrax" mt 
                        WHERE mt.reconstituted_text LIKE ? 
                           OR mt.cleaned_text LIKE ?
                           OR mt.reconstituted_text LIKE ? 
                           OR mt.cleaned_text LIKE ?
                        ORDER BY mt.inscription_id DESC;
                    """
                    cursor.execute(continuous_sql, (
                        f"%{continuous_term_u}%", f"%{continuous_term_u}%",
                        f"%{continuous_term_v}%", f"%{continuous_term_v}%"
                    ))
                    for row in cursor.fetchall():
                        ins_id, ins_text, ins_ref, line_ref, further_bib, linked_persons = row
                        text_rows.append((ins_id, ins_text, ins_ref, line_ref, further_bib, linked_persons))
                        
            # SEE IF ANY PERSON KINDA MATCHES THE QUERY AND OUTPUT ALL INSCRIPTIONS LINKED TO THAT PERSON
            like_query = f"%{re.sub(r'\s+', '%', clean_query)}%"
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
        
        for row in fallback_rows:
            ins_id = row[0]
            if ins_id not in seen_text_ids and ins_id not in seen_fallback_ids:
                unique_fallback_rows.append(row)
                seen_fallback_ids.add(ins_id)
                
        st.session_state.active_inscription_ids = list(seen_text_ids.union(seen_fallback_ids))
        all_matched_ids = st.session_state.active_inscription_ids

        st.session_state["active_search_where_clauses"] = [] 
        st.session_state["active_search_has_run"] = True
        
        if not all_matched_ids:
            st.session_state.search_results = f'No inscriptions found matching string "{user_input}"'
            conn.close()
            return
            
        object_count = 0
        if all_matched_ids:
            obj_cursor = conn.cursor()
            chunk_size = 900
            unique_objects = set()
            
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
            
        out_str = []
    
        header = f"## Search Results\nFound {len(text_rows)} direct match(es) and {len(unique_fallback_rows)} indirect match(es)!\n"
        header += f"**Key Word:** {user_input}\n\n"
        header += f"Compiled dossiers for all **{len(all_matched_ids)}** matching inscriptions on **{object_count}** objects:\n\n"
        out_str.append(header)
        
        for ins_id in all_matched_ids:
            out_str.append(f"## Inscription ID {ins_id}\n")
            dossier_text = get_inscription_report(cursor, int(ins_id))
            
            if dossier_text == "No inscription data found.":
                out_str.append(f"_Warning: This ID does not exist: {ins_id}_")
            else:
                out_str.append(dossier_text)
                
            out_str.append("\n\n---\n\n")
            
        st.session_state.search_results = "\n\n".join(out_str)
        conn.close()
    except Exception as e:
        st.error(f"An unexpected database error occurred: {e}")

# LOOK UP INSCRIPTION BY EDCS NUMBER OR TM NUMBER

def run_ref_search(ref_query):
    if not ref_query.strip():
        st.session_state.search_results = "Please enter an EDCS ID or TM Number."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        clean_digits = "".join(filter(str.isdigit, ref_query))
        
        if not clean_digits:
            st.session_state.search_results = f"No valid identification digits found in query: {ref_query}"
            st.session_state.active_inscription_ids = []
            conn.close()
            return
                
        scout_sql = '''
            SELECT DISTINCT m.inscription_id 
            FROM "Max_Thrax" m
            LEFT JOIN "inscriptions_and_TM_numbers" tm ON m.inscription_id = tm.inscription_id
            WHERE m.inscription_ref LIKE ? 
               OR tm.TM_number = ?;
        '''
        
        edcs_param = f"%{clean_digits}%"
        tm_param = int(clean_digits)
        
        cursor.execute(scout_sql, (edcs_param, tm_param))
        rows = cursor.fetchall()
        
        if not rows:
            st.session_state.search_results = f"No inscriptions match reference/TM ID: {clean_digits}"
            st.session_state.active_inscription_ids = []
            conn.close()
            return

        matched_ids = [row[0] for row in rows]
        st.session_state.active_inscription_ids = matched_ids
        st.session_state["csv_mode"] = "ids"
        
        out_str = [
            f"#### Found {len(matched_ids)} matching inscription(s) by identification lookup:\n", 
            "_" * 70 + "\n\n"
        ]
        
        for ins_id in matched_ids:
            out_str.append(f"## Inscription ID {ins_id}\n")
            
            dossier_text = get_inscription_report(cursor, int(ins_id))
            
            if dossier_text != "No inscription data found.":
                out_str.append(dossier_text)
            else:
                out_str.append(f"_Warning: Inscription ID {ins_id} could not compile properly._")
                
            out_str.append("\n\n---\n\n")
            
        st.session_state.search_results = "".join(out_str).rstrip("-\n ")
        conn.close()
        
    except Exception as e:
        st.error(f"An error occurred during lookup: {e}")
        if 'conn' in locals():
            conn.close()

def process_attestation_rows(rows):
    """
    Groups raw SQL data entries by item name and tracks occurrences per inscription.
    Output format: { item_name: { inscription_id: frequency_count } }
    """
    grouped = {}
    for item_name, ref, ins_id in rows:
        if item_name is None or ins_id is None:
            continue
        if item_name not in grouped:
            grouped[item_name] = {}
        grouped[item_name][ins_id] = grouped[item_name].get(ins_id, 0) + 1
    return grouped
                
# LOOK UP PERSON BY NAME (to see if the user query matches any individual logged in the database so they may select the correct individual in the next box)

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
            st.session_state.search_results = "" 
    except Exception as e:
        st.error(f"Person search failed: {e}")

# PERSON REPORT FUNCTION
def generate_person_report(p_id):
    # SQL QUERIES FOR PERSON REPORT
    sql_get_person_details = "SELECT person_name, person_notes FROM persons WHERE person_id = ?;"

    sql_get_all_person_inscriptions = """
        SELECT DISTINCT mt.inscription_id, mt.inscription_ref
        FROM "Max_Thrax" mt 
        JOIN "inscriptions_and_persons" ip ON mt.inscription_id = ip.inscription_id 
        WHERE ip.person_id = ?;
    """

    sql_get_positions = """
        SELECT pos.position_description, m2.inscription_ref, m2.inscription_id
        FROM inscriptions_and_persons ip2
        JOIN Max_Thrax m2 ON ip2.inscription_id = m2.inscription_id
        JOIN position_attestations pa2 ON ip2.inscription_person_id = pa2.inscription_person_id
        JOIN positions pos ON pa2.position_id = pos.position_id
        WHERE ip2.person_id = ?;
    """

    sql_get_status = """
        SELECT sd.status_designation, m3.inscription_ref, m3.inscription_id
        FROM inscriptions_and_persons ip3
        JOIN Max_Thrax m3 ON ip3.inscription_id = m3.inscription_id
        JOIN status_designation_attestations sda2 ON ip3.inscription_person_id = sda2.inscription_person_id
        JOIN status_designations sd ON sda2.status_designation_id = sd.status_designation_id
        WHERE ip3.person_id = ?;
    """

    sql_get_units = """
        SELECT col.collective_name, m4.inscription_ref, m4.inscription_id
        FROM inscriptions_and_persons ip4
        JOIN Max_Thrax m4 ON ip4.inscription_id = m4.inscription_id
        JOIN unit_affiliation_attestations uaa ON ip4.inscription_person_id = uaa.inscription_person_id
        JOIN collectives col ON uaa.collective_id = col.collective_id
        WHERE ip4.person_id = ?;
    """

    if not str(p_id).strip().isdigit():
        st.session_state.search_results = "Please enter a valid numerical Person ID."
        return
        
    person_id_int = int(p_id)
    conn = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Fetch Name and Notes
        cursor.execute(sql_get_person_details, (person_id_int,))
        name_row = cursor.fetchone()
        if not name_row:
            st.session_state.search_results = f"### **Person ID {p_id}**\n\n---\n\nNo person dossier card compiled for Person ID {p_id}."
            return
            
        person_name = name_row[0] if name_row[0] else f"Person ID {p_id}"
        person_notes = name_row[1] if name_row[1] else "None"
        header_message = f"### **{person_name}**\n\n---"
        
        # 2. Fetch all overall unique inscriptions linked to this person
        cursor.execute(sql_get_all_person_inscriptions, (person_id_int,))
        all_inscriptions = cursor.fetchall()  
        
        # Keep track of active inscriptions for the map component
        st.session_state.active_inscription_ids = [r[0] for r in all_inscriptions if r[0] is not None]
        st.session_state["active_search_where_clauses"] = []  
        st.session_state["active_search_has_run"] = True      
        
        # Maps & sets to keep track of unique IDs and translate ID -> Ref
        all_insc_ids = {r[0] for r in all_inscriptions if r[0] is not None}
        all_insc_id_to_ref = {r[0]: (r[1] if r[1] else f"Insc ID {r[0]}") for r in all_inscriptions if r[0] is not None}

        # 3. Fetch data sets using the clean standalone helper function
        cursor.execute(sql_get_positions, (person_id_int,))
        positions_data = process_attestation_rows(cursor.fetchall())
        
        cursor.execute(sql_get_status, (person_id_int,))
        status_data = process_attestation_rows(cursor.fetchall())
        
        cursor.execute(sql_get_units, (person_id_int,))
        units_data = process_attestation_rows(cursor.fetchall())
        
        # Track every unique inscription ID accounted for across all groupings
        attested_insc_ids = set()
        for dataset in [positions_data, status_data, units_data]:
            for category in dataset:
                attested_insc_ids.update(dataset[category].keys())
                
        has_any_attestations = len(attested_insc_ids) > 0

        # --- CONDITION LOGIC FOR OUTPUT GENERATION ---
        report_lines = [f"**Name:** {person_name} | **Person ID:** {person_id_int}\n"]
        
        # ALTERNATIVE OUTPUT 1: Completely un-affiliated person
        if not has_any_attestations:
            insc_strings = [f"{ref} (id: [{ins_id}](?ins_id={ins_id}))" for ins_id, ref in all_insc_id_to_ref.items()]
            insc_display = ", ".join(insc_strings) if insc_strings else "None"
            
            report_lines.append(f"**Mentioned in {len(all_insc_ids)} inscription(s):** {insc_display}\n")
            report_lines.append(f"**Notes:** {person_notes}")
            
            st.session_state.search_results = f"{header_message}\n\n" + "\n".join(report_lines)
            return

        # NORMAL ENTRY & ALTERNATIVE OUTPUT 2 CASING
        report_lines.append(f"**Mentioned in {len(all_insc_ids)} inscription(s)**\n")
        

        def format_section(title, dataset):
            if not dataset:
                return ""

            lines = [f"**{title}**\n"] 
            
            for item_name, ins_counts in dataset.items():
                ref_strings = [f"{all_insc_id_to_ref.get(i, f'ID: {i}')} (id: [{i}](?ins_id={i}))" for i in ins_counts.keys()]
                
                lines.append(f"• **{item_name} ({sum(ins_counts.values())} attestations)**: {', '.join(ref_strings)}")
                lines.append("  ") 
                
            return "\n".join(lines) + "\n"

        # Append blocks dynamically if data exists
        if positions_data:
            report_lines.append(format_section("Attested positions in inscriptions:", positions_data))
        if status_data:
            report_lines.append(format_section("Attested status in inscriptions:", status_data))
        if units_data:
            report_lines.append(format_section("Attested unit in inscription:", units_data))
            
        # ALTERNATIVE OUTPUT 2 (Mismatch Logic)
        leftover_insc_ids = all_insc_ids - attested_insc_ids
        if leftover_insc_ids:
            leftover_strings = [f"{all_insc_id_to_ref[ins_id]} (id: [{ins_id}](?ins_id={ins_id}))" for ins_id in leftover_insc_ids]
            leftover_display = " ".join(leftover_strings)
            report_lines.append(f"**Other inscriptions mentioning {person_name}:** {leftover_display}\n")
            
        # Wrap up with notes
        report_lines.append(f"**Notes:** {person_notes}")
        
        st.session_state.search_results = f"{header_message}\n\n" + "\n".join(report_lines)

    except Exception as e:
        st.session_state.search_results = f"Dossier production error: {e}"
    finally:
        if conn:
            conn.close()

# SET UP BASIC DROPDOWN MENU FROM DATABASE (for Advanced Search)
def get_filter_options(table, col):
    options = ["All"]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL AND "{col}" <> "" ORDER BY "{col}" ASC;'
        cursor.execute(query)
        
        for row in cursor.fetchall():
            val = str(row[0])
            options.append(val)
            
        conn.close()
    except Exception:
        pass
    return options
    
# ADVANCED SEARCH
def execute_advanced_search(f_dict):
    global active_inscription_ids
    applied_criteria_summary = []
    where_clauses = []
    query_params = {}
    
    st.session_state["active_search_where_clauses"] = where_clauses
    st.session_state["active_search_query_params"] = query_params
    st.session_state["active_search_has_run"] = True

    # SQL SETUP
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
    
    # NEW INTERVENTION FILTER TOGGLE STRATEGY
    intervention_toggle = f_dict.get('intervention_toggle', 'Interventions Relevant to Maximinus Thrax')
    if intervention_toggle == 'Interventions Relevant to Maximinus Thrax':
        applied_criteria_summary.append("  • Scope: Interventions Relevant to Maximinus Thrax")
        
        # Enforce all conditions: 
        # 1. mt.relevance_index = 1
        # 2. mt.intervention_status = 1
        # 3. Linked to an intervention where method_id != 1
        # 4. NOT linked to person_id 50
        where_clauses.append("""
            mt.relevance_index = 1 
            AND mt.intervention_status = 1 
            AND EXISTS (
                SELECT 1 FROM "interventions" int_sub 
                WHERE int_sub.patient_inscription = mt.inscription_id 
                AND int_sub.method_id != 1
            )
            AND NOT EXISTS (
                SELECT 1 FROM "inscriptions_and_persons" ip_sub 
                WHERE ip_sub.inscription_id = mt.inscription_id 
                AND ip_sub.person_id = 50
            )
        """)
    else:
        applied_criteria_summary.append("  • Scope: All Interventions")

    # ADVANCED TEXT SEARCH (USER PICKS STRATEGY)
    phrase = f_dict.get('text', '').strip()
    if phrase:
        search_mode = f_dict.get('text_search_mode', 'Match any inflected form of word or phrase')
        
        norm_phrase = phrase
        norm_phrase = re.sub(r'\s+[aA][nN][dD]\s+', ' AND ', norm_phrase)
        norm_phrase = re.sub(r'\s+[oO][rR]\s+', ' OR ', norm_phrase)
        norm_phrase = re.sub(r'\s+[nN][oO][tT]\s+', ' NOT ', norm_phrase)
        
        tokens = re.split(r'(\s+| AND | OR | NOT )', norm_phrase)
        
        fts_compiled_terms = []
        for token in tokens:
            t_clean = token.strip()
            if not t_clean: 
                continue
            
            if t_clean in ("AND", "OR", "NOT"):
                fts_compiled_terms.append(t_clean)
            else:
                if search_mode == 'Match any inflected form of word or phrase':
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
                    
                    all_variants = list(set(synonyms + continuous_words))
                    if len(all_variants) > 1:
                        syn_clause = "(" + " OR ".join([f'"{v}"' for v in all_variants]) + ")"
                    else:
                        syn_clause = f'"{all_variants[0]}"'
                    
                    fts_compiled_terms.append(syn_clause)
                else:
                    fts_compiled_terms.append(f'"{t_clean}"')
                    
        fts_query_string = " ".join(fts_compiled_terms)

        mode_label = "Inflected Forms" if search_mode == 'Match any inflected form of word or phrase' else "Exact Match"
        applied_criteria_summary.append(f"  • Keyword/Phrase: '{phrase}' [Mode: {mode_label}]")
        
        pname = f"fts_phrase_{len(query_params)}"
        query_params[pname] = fts_query_string
       
        fts_subquery = f"""
            mt.inscription_id IN (
                SELECT inscription_id 
                FROM inscriptions_fts 
                WHERE inscriptions_fts MATCH :{pname}
            )
        """
        where_clauses.append(fts_subquery)
        
   # DATE (USER PICKS STRATEGY)
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
        applied_criteria_summary.append(f"  • Start Date Bound: >= {req_start} CE")
        where_clauses.append("mt.end_date >= :req_start")
        query_params['req_start'] = int(req_start)
        
    elif req_end is not None:
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

  #SQL BUILDER
    for key, column_sql, display_name in mapping:
        val = f_dict.get(key, [])
        
        # Prevent rewriting explicit manual values if toggle overrules them
        if key == 'relevance_index' and intervention_toggle == 'Interventions Relevant to Maximinus Thrax':
            continue
        if key == 'intervention_status' and intervention_toggle == 'Interventions Relevant to Maximinus Thrax':
            continue

        if key == 'relevance_index' and f_dict.get('relevance_active'):
            applied_criteria_summary.append(f"  • {display_name}: {'Relevant' if val == 1 else 'Not Relevant'}")
            p_name = f"param_{key}"
            where_clauses.append(f"mt.relevance_index = :{p_name}")
            query_params[p_name] = val
            continue

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
            
    #PERSONS
    person_ids = f_dict.get('person_id', [])
    person_op = f_dict.get('person_operator', 'OR')

    if person_ids and person_ids != "All" and person_ids != ["All"]:
        applied_criteria_summary.append(f"  • Person ({person_op}): {', '.join(map(str, person_ids))}")
    
        person_params = []
        for idx, p_id in enumerate(person_ids):
            p_param_name = f"param_person_id_{idx}"
            query_params[p_param_name] = p_id
            person_params.append(f":{p_param_name}")

        if person_op == "AND":
            where_clauses.append(f"""
                (SELECT COUNT(DISTINCT ip_sub.person_id) 
                 FROM "inscriptions_and_persons" ip_sub 
                 WHERE ip_sub.inscription_id = mt.inscription_id 
                 AND ip_sub.person_id IN ({', '.join(person_params)})) = {len(person_ids)}
            """)
        else:
            where_clauses.append(f"ip_f.person_id IN ({', '.join(person_params)})")

    # INSTITUTIONS/GROUPS/MILITARY UNITS
    collective_names = f_dict.get('collective_name', [])
    collective_op = f_dict.get('collective_operator', 'OR')

    if collective_names and collective_names != "All" and collective_names != ["All"]:
        applied_criteria_summary.append(f"  • Collective/Military Unit ({collective_op}): {', '.join(map(str, collective_names))}")
        
        collective_params = []
        for idx, col_name in enumerate(collective_names):
            c_param_name = f"param_collective_name_{idx}"
            query_params[c_param_name] = col_name
            collective_params.append(f":{c_param_name}")

        if collective_op == "AND":
            where_clauses.append(f"""
                (SELECT COUNT(DISTINCT col_sub.collective_name) 
                 FROM "inscriptions_and_collectives" ic_sub
                 JOIN "collectives" col_sub ON ic_sub.collective_id = col_sub.collective_id
                 WHERE ic_sub.inscription_id = mt.inscription_id 
                 AND col_sub.collective_name IN ({', '.join(collective_params)})) = {len(collective_names)}
            """)
        else:
            where_clauses.append(f"col.collective_name IN ({', '.join(collective_params)})")

    # VIRORUM DISTRIBUTIO
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
            )
        """)

    # Combine final clauses
    if where_clauses:
        final_sql = base_sql + " AND " + " AND ".join(where_clauses)
    else:
        final_sql = base_sql
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

        # 3. Stitch every matching custom card together sequentially
        for ins_id in all_matched_ids:
            out_str.append(f"## Inscription ID {ins_id}\n")
            
            # Call your new function to get the complete text report
            dossier_text = get_inscription_report(cursor, int(ins_id))
            
            if dossier_text:
                out_str.append(dossier_text)
            else:
                out_str.append(f"_Warning: Could not find data for ID: {ins_id}_")
                
            out_str.append("\n\n---\n\n")
            
        st.session_state.search_results = "\n\n".join(out_str)
        
        conn.close()
    except Exception as e:
        st.session_state.search_results = f"Advanced Search Failed: {e}"

def fetch_metadata_by_id(inscription_ids_input):
    if not inscription_ids_input.strip():
        st.session_state.search_results = "Please enter one or more Inscription IDs."
        return
        
    raw_id_list = [x.strip() for x in inscription_ids_input.split(",")]
    valid_ids = [int(x) for x in raw_id_list if x and x.isdigit()]
    
    if not valid_ids:
        st.session_state.search_results = "Please enter one or more Inscription IDs as pure numbers"
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        st.session_state.active_inscription_ids = valid_ids
        st.session_state["active_search_where_clauses"] = []  
        st.session_state["active_search_has_run"] = True      

        out_str = []
        missing_ids = []
        valid_reports = []
            
        for ins_id in valid_ids:
            dossier_body = get_inscription_report(cursor, int(ins_id))
            
            if dossier_body == "No inscription data found.":
                missing_ids.append(str(ins_id))
            else:
                valid_reports.append((ins_id, dossier_body))
                
        if missing_ids:
            out_str.append(f"**Warning: The following ID(s) do not exist in the database:** {', '.join(missing_ids)}\n\n---\n\n")
            
        for ins_id, dossier_body in valid_reports:
            out_str.append(f"### Inscription ID {ins_id}\n\n")
            out_str.append(f"{dossier_body}\n\n")
            out_str.append("---\n\n")
            
        conn.close()
        
        st.session_state.search_results = "".join(out_str).rstrip("-\n ")
        
    except Exception as e:
        st.session_state.search_results = f"Error fetching metadata: {e}"
        if 'conn' in locals():
            try:
                conn.close()
            except:
                pass
                
def fetch_metadata_by_object_id(object_id):
    if not str(object_id).strip():
        st.session_state.search_results = "Please enter a valid Object ID."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Ask the database for the total count of unique inscription_id's linked to this object_id
        cursor.execute(
            'SELECT COUNT(DISTINCT inscription_id) FROM "Max_Thrax" WHERE object_id = ?',
            (object_id.strip(),)
        )
        inscription_count = cursor.fetchone()[0] or 0
        
        # Build the big markdown header message
        header_message = f"### **{inscription_count}** inscription(s) on this object\n\n---"
        
        # 2. Grab all companion inscription IDs that share this specific object_id
        cursor.execute(
            'SELECT inscription_id FROM "Max_Thrax" WHERE object_id = ? ORDER BY sequence_id ASC, inscription_id ASC', 
            (object_id.strip(),)
        )
        sibling_ids = [row[0] for row in cursor.fetchall()]
        
        if not sibling_ids:
            st.session_state.active_inscription_ids = []
            st.session_state["active_search_where_clauses"] = []
            st.session_state["active_search_has_run"] = True
            st.session_state.search_results = f"No inscriptions found for Object ID: {object_id}"
            
            conn.close()
        else:
            # 3. Compile the dossier markdown text blocks sequentially for all matched IDs
            compiled_blocks = []
            for sib_id in sibling_ids:
                # Calls your standardized compiler function directly
                dossier_text = get_inscription_report(cursor, int(sib_id))
                
                if dossier_text != "No inscription data found.":
                    compiled_blocks.append(dossier_text)
                else:
                    compiled_blocks.append(f"_Warning: Inscription data for ID {sib_id} could not compile properly._")
            
            conn.close()
            
            # 4. Update active workspace IDs and combine the header with the dossier content blocks
            st.session_state.active_inscription_ids = sibling_ids
            st.session_state["active_search_where_clauses"] = []
            st.session_state["active_search_has_run"] = True
            
            # Joins each full report block with a clear horizontal markdown break
            dossier_body = "\n\n---\n\n".join(compiled_blocks)
            st.session_state.search_results = f"{header_message}\n\n{dossier_body}"
            
    except Exception as e:
        st.session_state.search_results = f"Error fetching metadata by object ID: {e}"
             
# INTERACTIVE MAP

def generate_active_map():
    ids_to_map = st.session_state.active_inscription_ids
    if not ids_to_map:
        st.warning("No active search or report results are currently loaded to map.")
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in ids_to_map)
        
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

        # === PATH B LOOKUP: ERASED INSCRIPTIONS ===
        erased_ids = set()
        if ids_to_map:
            erased_query = f"""
                SELECT DISTINCT mt.inscription_id 
                FROM "Max_Thrax" mt
                INNER JOIN "interventions" i ON mt.inscription_id = i.patient_inscription
                WHERE mt.inscription_id IN ({placeholders})
                  AND mt.relevance_index = 1
                  AND i.method_id = 2
                  AND mt.inscription_id NOT IN (
                      SELECT inscription_id FROM "inscriptions_and_persons" WHERE person_id = 50
                  );
            """
            cursor.execute(erased_query, ids_to_map)
            erased_ids = {row[0] for row in cursor.fetchall()}

        conn.close()
    except Exception as e:
        st.error(f"Map rendering fault: {e}")
        return

    if not matched_points:
        st.info("None of the inscriptions have known geographic coordinates in the database.")
        return

    # SET MAP CENTER TO LARINO
    valid_center = [41.807100, 14.919200]
    
    # INITIALIZE MAP CONTAINER
    mymap = folium.Map(
        location=valid_center, 
        zoom_start=4.5, 
        tiles=None,
        zoom_snap=0.5, 
        zoomDelta=0.5,
        wheel_px_per_zoom_level=150,
        control_scale=True,
        doubleClickZoom=False,
        smooth_wheel_zoom=True,
    )
    
    # BASEMAPS - DARE SET TO TRUE (DEFAULT BASEMAP)
    folium.TileLayer(
        tiles="https://dh.gu.se/tiles/imperium/{z}/{x}/{y}.png", 
        name="Digital Atlas of the Roman Empire", 
        overlay=False, 
        control=True, 
        attr="DARE",
        show=True
    ).add_to(mymap)

    folium.TileLayer(
        tiles="https://cawm.lib.uiowa.edu/tiles/{z}/{x}/{y}.png", 
        name="Ancient World Mapping Center Map", 
        overlay=False, 
        control=True, 
        attr="AWMC",
        show=False
    ).add_to(mymap)
    
    # ITINER-E ROADS LAYER
    optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
    if os.path.exists(optimized_json_path):
        with open(optimized_json_path, "r", encoding="utf-8") as f:
            coords_data = json.load(f)
        folium.GeoJson(
            coords_data, 
            name="Roads (based on Itiner-e)", 
            show=True, 
            overlay=True, 
            control=True,
            style_function=lambda feature: {"color": "#ff33a1", "weight": 1.0, "opacity": 0.8}
        ).add_to(mymap)

# PROVINCES LAYER
    from collections import Counter
    
    # 1. Count total inscriptions per province
    search_counts = Counter([row[9].strip() for row in matched_points if len(row) > 9 and row[9]])
    
    # 2. Count ONLY erased inscriptions per province
    erased_counts = Counter([
        row[9].strip() 
        for row in matched_points 
        if len(row) > 9 and row[9] and row[0] in erased_ids
    ])
    
    if os.path.exists(provinces_json_path):
        with open(provinces_json_path, "r", encoding="utf-8") as f:
            provinces_data = json.load(f)
        
        features = provinces_data.get("features", [provinces_data] if isinstance(provinces_data, dict) else [])
        for feature in features:
            props = feature.setdefault("properties", {})
            geo_name = props.get("Name") or props.get("province_name")
            if geo_name:
                geo_name_clean = geo_name.strip()
                count = search_counts.get(geo_name_clean, 0)
                erased_count = erased_counts.get(geo_name_clean, 0)
                
                # Inject both counts into the GeoJSON properties
                props["search_count"] = f"<br>{count}"
                props["erased_count"] = f"<br>{erased_count}"
            else:
                props["search_count"] = "<br>0"
                props["erased_count"] = "<br>0"
                
        folium.GeoJson(
            provinces_data, 
            name="Provinces (200CE)", 
            show=True, 
            overlay=True, 
            control=True,
            style_function=lambda feature: {"color": "#544CA4", "weight": 2, "fillColor": "#1a53ff", "fillOpacity": 0.05},
            tooltip=folium.GeoJsonTooltip(
                fields=["Name", "search_count", "erased_count"], 
                aliases=["Province:", "Matching<br>Inscriptions:", "Relevant<br>Erasures:"], 
                localize=True,
                style="font-family: sans-serif; font-size: 13px; padding: 8px;"
            )
        ).add_to(mymap)
        
        mymap.get_root().header.add_child(folium.Element("""
            <style>
                .leaflet-tooltip table td {
                    text-align: left !important;
                    padding-right: 15px !important;
                }
            </style>
        """))

         
    # STACKABLE VISUAL LAYERS
    range_layer = folium.FeatureGroup(name="Show Location Range for Approximate Coordinates", show=False)
    default_layer = folium.FeatureGroup(name="Inscriptions (Default View)", show=True)
    erased_layer = folium.FeatureGroup(name="Inscriptions (Show Erasures relevant to Maximinus Thrax in Red)", show=False)

    # GENERATE SPECIAL FEATURES FOR INSCRIPTIONS LAYER (UNCERTAINTY BOUNDS)
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

        geo_json_str = row[13]
        f_id = row[0]
        if geo_json_str:
            try:
                polygon_geometry = json.loads(geo_json_str)
                folium.GeoJson(
                    polygon_geometry,
                    style_function=lambda feature: {
                        "color": "#7f8c8d",       
                        "weight": 2,
                        "dashArray": "6, 6",      
                        "fillColor": "#95a5a6",   
                        "fillOpacity": 0.15,
                    },
                    tooltip=f"Uncertainty Bounds for Inscription ID: {f_id}"
                ).add_to(range_layer)
            except Exception:
                pass
                
    # GENERATE MARKERS FOR BOTH VISUAL LAYERS
    for (lat, lon), rows in coord_buckets.items():
        overlap_count = len(rows)
        is_bucket_approximate = any(row[12] == 1 for row in rows)
        
        bucket_erased_rows = [row for row in rows if row[0] in erased_ids]
        erased_count = len(bucket_erased_rows)
            
        popup_html = ""
        if is_bucket_approximate:
            popup_html += """
            <h3 style="color: #000000; margin: 0 0 10px 0; font-weight: bold; text-align: center; font-size: 13px;">
                WARNING: APPROXIMATE COORDINATES
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
                
            ref_link = f'<a href="https://edcs.hist.uzh.ch/monument/{ref_text.replace("EDCS-", "")}" target="_blank">{ref_text}</a>' if ref_text else 'N/A'
            report_url = f"https://maximinusthraxdatabaseui.streamlit.app/?ins_id={f_id}"

            if overlap_count > 1:
                item_border = "#7f8c8d" if is_approx == 1 else "#001140"
                popup_html += f"<div style='border-left: 3px solid {item_border}; padding-left: 8px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed #ccc;'> "
                popup_html += f"<span style='font-size:11px; font-weight:bold; color:#555;'>Record {idx} of {overlap_count}</span>"
                
                # Dynamic UX Tag placement inside the Record header line
                if f_id in erased_ids:
                    popup_html += " <span style='font-size:11px; color:#e56333; font-weight:bold;'>| Erasure relevant to Maximinus Thrax</span>"
                if is_approx == 1:
                    popup_html += " <span style='font-size:10px; color:#000000; font-weight:bold;'>(APPROXIMATE)</span>"
                popup_html += "<br>"

            if overlap_count == 1 and is_approx == 1:
                popup_html += (
                    "<span style='font-size: 12px; color: #000000; font-weight: normal; line-height: 1.4;'>"
                    "Some legacy place names cannot be securely linked to a modern location.<br>"
                    "Approximate coordinates represent the geometric center of the area where the place is likely located. This area is estimated based on identifiable sites reported in the vicinity,or based on the mile number of a milestone associated with the place.<br>"
                    "</span><br>"
                )
                 
            popup_html += (
                f"<b>Inscription ID:</b> <a href='{report_url}' target='_blank'>{f_id}</a> | <b>Ref:</b> {ref_link}"
            )
            
            # Dynamic UX Tag placement for Single Marker views
            if overlap_count == 1 and f_id in erased_ids:
                popup_html += " <span style='font-size:11px; color:#e56333; font-weight:bold;'>| Erasure relevant to Maximinus Thrax</span>"
                
            popup_html += (
                f"<br><b>Number of Inscriptions:</b> {ins_count} | <b>Sequence ID:</b> {sequence}<br>"
                f"<b>Province:</b> {province}<br>"
                f"<b>Place:</b> {place} | <b>Pleiades:</b> {pleiades_link}"
            )
            
            if support_id in (1, 2):
                popup_html += "<br><b>Type of Inscription:</b> Milestone"
                info = road_links_dict.get(f_id, {'roads': []})
                if info['roads']:
                    road_name = ", ".join(list(set(r[0] for r in info['roads'] if r[0])))
                    popup_html += f"<br><b>road segment:</b> {road_name if road_name else 'N/A'}"
                    links = [f'<a href="https://itiner-e.org/?id={r[1]}" target="_blank">itiner-e.org/?id={r[1]}</a>' for r in info['roads'] if r[1]]
                    popup_html += f"<br><b>itiner-e link to road segment:</b> {', '.join(links) if links else 'N/A'}"
                else:
                    popup_html += "<br><b>road segment:</b> N/A<br><b>itiner-e link to road segment:</b> N/A"
            else:
                popup_html += f"<br><b>Type of Inscription:</b> {dist_tit if dist_tit else 'N/A'}<br><b>support:</b> {support_name if support_name else 'N/A'}"
            
            if overlap_count > 1:
                popup_html += "</div>"
                     
        # PASS A: PLOT TO DEFAULT VIEW LAYER 

        if overlap_count > 1:
            size = 16
            d_border = "#20304c" if is_bucket_approximate else "#001140"
            d_fill = "#6c7c9c" if is_bucket_approximate else "#1a53ff"
            d_icon = f'<div style="background-color: {d_fill}; border: 2px solid {d_border}; color: #ffffff; border-radius: 50%; width: {size}px; height: {size}px; font-size: 11px; font-weight: bold; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 5px rgba(0,0,0,0.4);">{overlap_count}</div>'
            tooltip_label = f"{overlap_count} entries here (Contains Approximate Locations)" if is_bucket_approximate else f"{overlap_count} inscriptions here"
        else:
            size = 10
            d_border = "#20304c" if is_bucket_approximate else "#002fa7"
            d_fill = "#6c7c9c" if is_bucket_approximate else "#33b5e5"
            d_icon = f'<div style="background-color: {d_fill}; border: 2px solid {d_border}; border-radius: 50%; width: {size}px; height: {size}px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);"></div>'
            tooltip_label = f"ID: {rows[0][0]} (Approximate Location)" if is_bucket_approximate else f"ID: {rows[0][0]}"

        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(icon_size=(size, size), icon_anchor=(size // 2, size // 2), html=d_icon),
            popup=folium.Popup(f"<div style='max-height: 280px; overflow-y: auto;'>{popup_html}</div>", min_width=340, max_width=480),
            tooltip=tooltip_label
        ).add_to(default_layer)

        # PASS B: PLOT TO ERASURE OVERLAY LAYER

        if erased_count > 0:
            # UX RE-ENGINEERING: Marker size strictly mirrors default layer (overlap_count) to prevent donuts
            if overlap_count > 1:
                size = 16
                e_border = "#4c2420" if is_bucket_approximate else "#400000"
                e_fill = "#9c726c" if is_bucket_approximate else "#ff1a1a"
                # Displays the unique erased subset value within the matching physical container
                e_icon = f'<div style="background-color: {e_fill}; border: 2px solid {e_border}; color: #ffffff; border-radius: 50%; width: {size}px; height: {size}px; font-size: 11px; font-weight: bold; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 5px rgba(0,0,0,0.4);">{erased_count}</div>'
                e_tooltip = f"{erased_count} relevant erasures here"
            else:
                size = 10
                e_border = "#4c2420" if is_bucket_approximate else "#400000"
                e_fill = "#9c726c" if is_bucket_approximate else "#e56333"
                e_icon = f'<div style="background-color: {e_fill}; border: 2px solid {e_border}; border-radius: 50%; width: {size}px; height: {size}px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);"></div>'
                e_tooltip = f"ID: {bucket_erased_rows[0][0]} (Relevant Erasure)"

            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(icon_size=(size, size), icon_anchor=(size // 2, size // 2), html=e_icon),
                popup=folium.Popup(f"<div style='max-height: 280px; overflow-y: auto;'>{popup_html}</div>", min_width=340, max_width=480),
                tooltip=e_tooltip
            ).add_to(erased_layer)

    # Attach all layers to map
    range_layer.add_to(mymap)
    default_layer.add_to(mymap)
    erased_layer.add_to(mymap)
    
    folium.LayerControl(collapsed=False).add_to(mymap)

    # Global UI Script (Handles double-click interface hiding)
    double_click_hide_script = """
    <script>
        window.addEventListener('DOMContentLoaded', (event) => {
            setTimeout(function() {
                var mapElements = document.querySelectorAll('.folium-map');
                if (mapElements.length > 0) {
                    var mapId = mapElements[0].id;
                    var mymap = window[mapId];
                    
                    if (mymap) {
                        var hiddenState = false;
                        
                        // Native Leaflet map event listener - double click interface toggler
                        mymap.on('dblclick', function(e) {
                            hiddenState = !hiddenState;
                            
                            var selectors = [
                                '.leaflet-control-zoom', 
                                '.leaflet-control-layers', 
                                '.leaflet-draw', 
                                '.easyprint-container', 
                                '.legend',
                                '.leaflet-control-scale'
                            ];
                            
                            selectors.forEach(function(sel) {
                                document.querySelectorAll(sel).forEach(function(el) {
                                    el.style.setProperty('display', hiddenState ? 'none' : 'block', 'important');
                                });
                            });
                        });
                    }
                }
            }, 200);
        });
    </script>
    """
    mymap.get_root().header.add_child(folium.Element(double_click_hide_script))
    st.session_state.trigger_map_html = mymap._repr_html_()


        
__all__ = [
    
    'get_inscription_report',
    'get_db_connection',
    'reset_map_and_search_flags',
    'generate_bulk_search_csv',
    'generate_bulk_search_sql',
    'convert_markdown_bold_to_underline',
    'clean_epigraphic_text',
    'convert_roman_to_arabic_in_text',
    'run_standard_search',
    'run_ref_search',
    'lookup_person_options',
    'generate_person_report',
    'get_filter_options',
    'execute_advanced_search',
    'fetch_metadata_by_id',
    'fetch_metadata_by_object_id',
    'generate_active_map',
    
]
