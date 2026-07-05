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
In main_report_sql, the text output for each method_id and extent_id are hardcoded, instead of being dynamically fetched from a field in the database. 
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
db_path = os.path.join(BASE_DIR, "version_58.db")

optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
provinces_json_path = os.path.join(BASE_DIR, "roman_provinces.json") 


#SQL QUERY FOR MAIN REPORT
main_report_sql = """
        WITH TargetInscription AS (SELECT ? AS selected_id),
        TargetObject AS (SELECT object_id AS selected_obj_id FROM "Max_Thrax" WHERE inscription_id = (SELECT selected_id FROM TargetInscription)),
        Metadata_Joined AS (
            SELECT mt.inscription_id, mt.inscription_ref, mt.line_ref, 
                   mt.inscription_text_formatted, mt.corrected_lemmas, mt.dating, mt.expanded_bibliography,
                   mt.object_id,
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
                       WHEN inscription_ref IS NOT NULL THEN '[' || inscription_ref || '](https://edcs.hist.uzh.ch/monument/' || REPLACE(inscription_ref, 'EDCS-', '') || ')'
                       ELSE '' 
                   END || 
                   CASE 
                       WHEN inscription_ref IS NOT NULL AND line_ref IS NOT NULL THEN ' ' || line_ref
                       WHEN line_ref IS NOT NULL THEN line_ref
                       WHEN inscription_ref IS NULL AND line_ref IS NULL THEN 'N/A'
                       ELSE ''
                   END || 
                   ' | **TM Number:** ' || tm_hyperlinks ||
                   ' | **Inscription ID:** [' || inscription_id || '](?ins_id=' || inscription_id || ')' ||
                   ' | **Object ID:** [' || COALESCE(object_id, 'N/A') || '](?obj_id=' || COALESCE(object_id, '') || ')' || -- 🚀 Added hyperlinked Object ID metadata badge right here
                   char(10) || char(10) AS tl FROM Metadata_Joined
            
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

# LATIN LEMMMA MAP

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
                root_lemma = LATIN_LEMMA_MAP.get(token, token)
                token_variants = list(set(
                    [k for k, v in LATIN_LEMMA_MAP.items() if v == root_lemma] + [root_lemma, token]
                ))
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
            
            if not text_rows and not fallback_rows:
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
                        
            # SEE IF ANY PERSON KINDA MATCHES THE QUERY AND OUTPUT ALL INSCRIPTIONS LINKED TO THAT PERSON
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
        
        for rank, ins_id in enumerate(all_matched_ids, 1):
            out_str.append(f"## Result {rank}\n")
            
            cursor.execute(main_report_sql, (int(ins_id),))
            card_rows = cursor.fetchall()
            
            if card_rows:
                dossier_text = "\n".join([r[0] for r in card_rows if r[0] is not None])
                out_str.append(dossier_text)
            else:
                out_str.append(f"_Warning: This ID not exist: {ins_id}_")
                
            out_str.append("\n\n---\n\n")
            
        st.session_state.search_results = "\n\n".join(out_str)
        conn.close()
    except Exception as e:
        st.error(f"An unexpected database error occurred: {e}")

# LOOK UP INSCRIPTION BY EDCS NUMBER 

def run_ref_search(ref_query):
    if not ref_query.strip():
        st.session_state.search_results = "Please enter an EDCS ID."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Look up which inscription IDs match your reference text query pattern
        scout_sql = 'SELECT inscription_id FROM "Max_Thrax" WHERE inscription_ref LIKE ?;'
        cursor.execute(scout_sql, (f"%{ref_query.strip()}%",))
        rows = cursor.fetchall()
        
        if not rows:
            st.session_state.search_results = f"No inscriptions in this database matches: {ref_query}"
            st.session_state.active_inscription_ids = []
            conn.close()
            return

        # Gather all matching IDs
        matched_ids = [row[0] for row in rows]
        st.session_state.active_inscription_ids = matched_ids
        st.session_state["csv_mode"] = "ids"
        
        # 2. Loop through those IDs and compile the rich dossier text blocks
        out_str = [
            f"#### Found {len(matched_ids)} matching inscription(s) by reference:\n", 
            "_" * 70 + "\n\n"
        ]
        
        for idx, ins_id in enumerate(matched_ids, 1):
            out_str.append(f"## Result {idx}\n")
            
            # Direct the execution to your single global main query constant
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
        
    except Exception as e:
        st.session_state.search_results = f"Reference Search Error: {e}"
             
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
        
# GENERATE PERSON REPORT
def generate_person_report(p_id):
    if not str(p_id).strip().isdigit():
        st.session_state.search_results = "Please enter a valid numerical Person ID."
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Fetch the person's name first to build the style header
        cursor.execute("SELECT person_name FROM persons WHERE person_id = ?;", (int(p_id),))
        name_row = cursor.fetchone()
        person_name = name_row[0] if name_row else f"Person ID {p_id}"
        
        # Build the header message in your exact requested style
        header_message = f"### **{person_name}**\n\n---"
        
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
            '**Name:** ' || p.person_name || ' | **person id:** ' || p.person_id || char(10) || char(10) ||
            
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
        cursor.execute(sql, (int(p_id),))
        result = cursor.fetchone()
        
        if result and result[0]:
            # Prepend the style header block directly to the SQL report text block
            st.session_state.search_results = f"{header_message}\n\n{result[0]}"
        else:
            st.session_state.search_results = f"{header_message}\n\nNo person dossier card compiled for Person ID {p_id}."
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
        for rank, ins_id in enumerate(all_matched_ids, 1):
            out_str.append(f"## Result {rank}\n")
            
            cursor.execute(main_report_sql, (int(ins_id),))
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
        
        cursor.execute(main_report_sql, (int(inscription_id),))
        rows = cursor.fetchall()
        conn.close()
        
        header_message = f"### Inscription ID {inscription_id.strip()}\n\n"
        
        if not rows:
            st.session_state.active_inscription_ids = [int(inscription_id.strip())]
            st.session_state["active_search_where_clauses"] = []  # Mode 2 explicit ID handling
            st.session_state["active_search_has_run"] = True      # Displays the button

            st.session_state.search_results = f"{header_message}No metadata entries discovered for ID: {inscription_id}"
            
        else:
            dossier_body = "\n".join([row[0] for row in rows if row[0] is not None])
            st.session_state.search_results = f"{header_message}{dossier_body}"
    except Exception as e:
        st.session_state.search_results = f"Error fetching metadata: {e}"
             

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
        else:
            # 3. Compile the dossier markdown text blocks sequentially for all matched IDs
            compiled_blocks = []
            for sib_id in sibling_ids:
                cursor.execute(main_report_sql, (sib_id,))
                report_rows = cursor.fetchall()
                compiled_blocks.append("".join([row[0] for row in report_rows if row[0] is not None]))
            
            conn.close()
            
            # 4. Update active workspace IDs and combine the header with the dossier content blocks
            st.session_state.active_inscription_ids = sibling_ids
            st.session_state["active_search_where_clauses"] = []
            st.session_state["active_search_has_run"] = True
            
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
        
        # Calculate exactly how many inscriptions in this specific bucket are erased
        bucket_erased_rows = [row for row in rows if row[0] in erased_ids]
        erased_count = len(bucket_erased_rows)
        
        # ---------------------------------------------------------
        # 1. BUILD THE POPUP HTML (SHARED SYSTEM)
        # ---------------------------------------------------------
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

            # Structural Header Line for Multi-Record Clusters
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


def teleport_to_results():
    unique_id = str(time.time()).replace(".", "")
    st.components.v1.html(
        f"""
        <script>
            // Unique execution tag: {unique_id}
            function smoothGlide() {{
                try {{
                    // Try direct method first (if running locally/same-origin)
                    var target = window.parent.document.getElementById("results-anchor");
                    if (target) {{
                        target.scrollIntoView({{ behavior: "smooth", block: "start" }});
                        return;
                    }
                }} catch (e) {{
                    // Fallback for Streamlit Cloud sandbox: safe cross-origin messaging
                    window.parent.postMessage({{"type": "scroll", "target": "results-anchor"}}, "*");
                }}
            }}
            smoothGlide();
            setTimeout(smoothGlide, 150);
        </script>
        """,
        height=0
    )

__all__ = [
    
    'main_report_sql',
    'LATIN_LEMMA_MAP',
    'get_db_connection',
    'reset_map_and_search_flags',
    'generate_bulk_search_csv',
    'generate_bulk_search_sql',
    'convert_markdown_bold_to_underline',
    'lemmatize_query',
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
    'teleport_to_results',
    
    
]
