import sqlite3
import re
import os
import textwrap
import streamlit as st
import folium
import json

st.set_page_config(page_title="Maximinus Thrax Database Explorer", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
db_path = os.path.join(BASE_DIR, "version_58.db")

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
            LEFT JOIN "materials" m             ON mt.material_id = m.material_id
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
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription
            
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
        Sec1_Header AS (SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, '### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec1_List AS (SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, '* ' || mt.sequence_id || '. ' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        Sec2_Summary AS (SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, '**' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || ' :** ' || CASE WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 THEN '_no interventions_' ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' interventions' END || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec2_Spacer AS (SELECT 2 AS sg, 999999 AS seq_id, 2 AS inner_lo, '' AS tl UNION ALL SELECT 2 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        Sec3_Inscription_Headers AS (SELECT 3 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, '#### ' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id AND EXISTS (SELECT 1 FROM "interventions_and_inscriptions" i3 JOIN "interventions" iam3 ON i3.intervention_id = iam3.intervention_id WHERE i3.inscription_id = mt.inscription_id AND i3.role_id = 1 AND iam3.method_id <> 1)),
        Sec3_Intervention_Details AS (SELECT 3 AS sg, mt.sequence_id AS seq_id, 1 + ROW_NUMBER() OVER (PARTITION BY i.inscription_id ORDER BY i.intervention_id) AS inner_lo, '* _intervention ' || ROW_NUMBER() OVER (PARTITION BY i.inscription_id ORDER BY i.intervention_id) || ' :_ ' || CASE WHEN iam.method_id = 2 THEN COALESCE(e.extent_description, '') || ' ' || COALESCE(m.method_description, '') || ' of inscription, ' || COALESCE(m.method_description, '') || ' targeting ' || (SELECT GROUP_CONCAT(t.target_description, ', ') FROM "interventions_and_targets" iat JOIN "targets" t ON iat.target_id = t.target_id WHERE iat.intervention_id = i.intervention_id) WHEN iam.method_id = 3 THEN 'reuse of monument' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END WHEN iam.method_id = 4 THEN 'monument damage' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END ELSE '' END || char(10) AS tl FROM "interventions_and_inscriptions" i JOIN "interventions" iam ON i.intervention_id = iam.intervention_id LEFT JOIN "extent" e ON iam.extent_id = e.extent_id LEFT JOIN "methods" m ON iam.method_id = m.method_id JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id AND i.role_id = 1 AND iam.method_id <> 1)
        SELECT tl FROM (
            SELECT * FROM Sec0_Metadata 
            UNION ALL SELECT * FROM Sec0_Text_Header 
            UNION ALL SELECT * FROM Sec0_Text_Body 
            UNION ALL SELECT * FROM Sec0_Spacer 
            UNION ALL SELECT * FROM Sec1_Header 
            UNION ALL SELECT * FROM Sec1_List 
            UNION ALL SELECT * FROM Sec1_Spacer 
            UNION ALL SELECT * FROM Sec2_Summary 
            UNION ALL SELECT * FROM Sec2_Spacer 
            UNION ALL SELECT * FROM Sec3_Inscription_Headers 
            UNION ALL SELECT * FROM Sec3_Intervention_Details
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
        header = f"## Search Results\nFound {len(text_rows)} direct matches and {len(unique_fallback_rows)} indirect matches!\n"
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
        cursor.execute('SELECT inscription_id, inscription_text, inscription_ref, line_ref, further_bibliography FROM "Max_Thrax" WHERE inscription_ref LIKE ?;', (f"%{ref_query.strip()}%",))
        rows = cursor.fetchall()
        
        # --- DO NOT CLOSE THE CONNECTION YET ---

        if not rows:
            st.session_state.search_results = f"No inscriptions found matching reference: {ref_query}"
            st.session_state.active_inscription_ids = [] # Explicitly clear old map markers out
            conn.close() # Safe to close on an empty exit branch
            return

        # Securely lock the IDs into the session tracking layer while rows is alive
        st.session_state.active_inscription_ids = [row[0] for row in rows]
        
        out_str = [f"Found {len(rows)} matching inscription reference records:\n", "="*70 + "\n\n"]
        for idx, row in enumerate(rows, 1):
            ins_id, ins_text, ins_ref, line_ref, further_bib = row
            out_str.append(f"[{idx}] {ins_ref} {line_ref if line_ref else ''} | ID: {ins_id}\n\nText:\n{ins_text}\n\nBibliography:\n{further_bib}\n" + "-"*70 + "\n\n")
        st.session_state.search_results = "".join(out_str)
        
        # --- CLOSE CONNECTION SAFELY HERE ---
        conn.close()
        
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

   # 3. Mapping Configuration
    mapping = [
        ('relevance_index', 'mt.relevance_index', 'Relevance'),
        ('distributio_titulorum', 'dt.distributio_titulorum', 'Distributio Titulorum'),
        ('material_name', 'm.material_name', 'Material'),
        ('support_name', 's.support_name', 'Support Type'),
        ('context_name', 'ct.context_name', 'Context Type'),
        ('province_name', 'pr.province_name', 'Province'),
        ('number_of_inscriptions', 'o.number_of_inscriptions', 'Inscriptions on Object'),
        # Note: 'person_id' is skipped here and intercepted with custom operator logic below
        ('virorum_distributio', 'vd.virorum_distributio', 'Distributio Virorum'),
        ('status_designation', 'sd.status_designation', 'Status Designation'),
        ('position_description', 'pos.position_description', 'Office/Military Role'),
        ('collective_name', 'col.collective_name', 'Collective/Military Unit'),
        ('intervention_status', 'mt.intervention_status', 'Intervention Status'),
        ('method_description', 'meth.method_description', 'Method of Intervention'),
        ('extent_description', 'ext.extent_description', 'Extent of Intervention'),
        ('target_description', 'targ.target_description', 'Target of Intervention'),
        ('status_tituli_name', 'st.status_tituli_name', 'Status Tituli (Conservation)')
    ]

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
            LEFT JOIN "materials" m             ON mt.material_id = m.material_id
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
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription
            
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
        Sec1_Header AS (SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, '### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec1_List AS (SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, '* ' || mt.sequence_id || '. ' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        Sec2_Summary AS (SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, '**' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || ' :** ' || CASE WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 THEN '_no interventions_' ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' interventions' END || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec2_Spacer AS (SELECT 2 AS sg, 999999 AS seq_id, 2 AS inner_lo, '' AS tl UNION ALL SELECT 2 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        Sec3_Inscription_Headers AS (SELECT 3 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, '#### ' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id AND EXISTS (SELECT 1 FROM "interventions_and_inscriptions" i3 JOIN "interventions" iam3 ON i3.intervention_id = iam3.intervention_id WHERE i3.inscription_id = mt.inscription_id AND i3.role_id = 1 AND iam3.method_id <> 1)),
        Sec3_Intervention_Details AS (SELECT 3 AS sg, mt.sequence_id AS seq_id, 1 + ROW_NUMBER() OVER (PARTITION BY i.inscription_id ORDER BY i.intervention_id) AS inner_lo, '* _intervention ' || ROW_NUMBER() OVER (PARTITION BY i.inscription_id ORDER BY i.intervention_id) || ' :_ ' || CASE WHEN iam.method_id = 2 THEN COALESCE(e.extent_description, '') || ' ' || COALESCE(m.method_description, '') || ' of inscription, ' || COALESCE(m.method_description, '') || ' targeting ' || (SELECT GROUP_CONCAT(t.target_description, ', ') FROM "interventions_and_targets" iat JOIN "targets" t ON iat.target_id = t.target_id WHERE iat.intervention_id = i.intervention_id) WHEN iam.method_id = 3 THEN 'reuse of monument' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END WHEN iam.method_id = 4 THEN 'monument damage' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END ELSE '' END || char(10) AS tl FROM "interventions_and_inscriptions" i JOIN "interventions" iam ON i.intervention_id = iam.intervention_id LEFT JOIN "extent" e ON iam.extent_id = e.extent_id LEFT JOIN "methods" m ON iam.method_id = m.method_id JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id AND i.role_id = 1 AND iam.method_id <> 1)
        SELECT tl FROM (
            SELECT * FROM Sec0_Metadata 
            UNION ALL SELECT * FROM Sec0_Text_Header 
            UNION ALL SELECT * FROM Sec0_Text_Body 
            UNION ALL SELECT * FROM Sec0_Spacer 
            UNION ALL SELECT * FROM Sec1_Header 
            UNION ALL SELECT * FROM Sec1_List 
            UNION ALL SELECT * FROM Sec1_Spacer 
            UNION ALL SELECT * FROM Sec2_Summary 
            UNION ALL SELECT * FROM Sec2_Spacer 
            UNION ALL SELECT * FROM Sec3_Inscription_Headers 
            UNION ALL SELECT * FROM Sec3_Intervention_Details
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
            LEFT JOIN "materials" m             ON mt.material_id = m.material_id
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
            
            UNION ALL SELECT 0 AS sg, 0 AS seq_id, 8 AS inner_lo, '**Persons:** ' || COALESCE((SELECT GROUP_CONCAT('[' || p.person_name || '](?person_id=' || p.person_id || ') (id: ' || p.person_id || ')', ', ') FROM "persons" p JOIN "inscriptions_and_persons" ip ON p.person_id = ip.person_id WHERE ip.inscription_id = (SELECT selected_id FROM TargetInscription)), 'N/A') || char(10) || char(10) AS tl FROM TargetInscription
            
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
        Sec1_Header AS (SELECT 1 AS sg, 0 AS seq_id, 1 AS inner_lo, '### ' || COUNT(mt.inscription_id) || ' inscriptions on object:' || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec1_List AS (SELECT DISTINCT 1 AS sg, mt.sequence_id AS seq_id, 2 AS inner_lo, '* ' || mt.sequence_id || '. ' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || ' (id: [' || mt.inscription_id || '](?ins_id=' || mt.inscription_id || '))' || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec1_Spacer AS (SELECT 1 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        Sec2_Summary AS (SELECT 2 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, '**' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || ' :** ' || CASE WHEN (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) = 0 THEN '_no interventions_' ELSE (SELECT COUNT(DISTINCT i2.intervention_id) FROM "interventions_and_inscriptions" i2 JOIN "interventions" iam2 ON i2.intervention_id = iam2.intervention_id WHERE i2.inscription_id = mt.inscription_id AND i2.role_id = 1 AND iam2.method_id <> 1) || ' interventions' END || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id),
        Sec2_Spacer AS (SELECT 2 AS sg, 999999 AS seq_id, 2 AS inner_lo, '' AS tl UNION ALL SELECT 2 AS sg, 999999 AS seq_id, 3 AS inner_lo, '' || char(10) || char(10) AS tl),
        Sec3_Inscription_Headers AS (SELECT 3 AS sg, mt.sequence_id AS seq_id, 1 AS inner_lo, '#### ' || mt.inscription_ref || CASE WHEN mt.line_ref IS NOT NULL AND mt.line_ref <> '' THEN ' ' || mt.line_ref ELSE '' END || char(10) || char(10) AS tl FROM "Max_Thrax" mt CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id AND EXISTS (SELECT 1 FROM "interventions_and_inscriptions" i3 JOIN "interventions" iam3 ON i3.intervention_id = iam3.intervention_id WHERE i3.inscription_id = mt.inscription_id AND i3.role_id = 1 AND iam3.method_id <> 1)),
        Sec3_Intervention_Details AS (SELECT 3 AS sg, mt.sequence_id AS seq_id, 1 + ROW_NUMBER() OVER (PARTITION BY i.inscription_id ORDER BY i.intervention_id) AS inner_lo, '* _intervention ' || ROW_NUMBER() OVER (PARTITION BY i.inscription_id ORDER BY i.intervention_id) || ' :_ ' || CASE WHEN iam.method_id = 2 THEN COALESCE(e.extent_description, '') || ' ' || COALESCE(m.method_description, '') || ' of inscription, ' || COALESCE(m.method_description, '') || ' targeting ' || (SELECT GROUP_CONCAT(t.target_description, ', ') FROM "interventions_and_targets" iat JOIN "targets" t ON iat.target_id = t.target_id WHERE iat.intervention_id = i.intervention_id) WHEN iam.method_id = 3 THEN 'reuse of monument' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END WHEN iam.method_id = 4 THEN 'monument damage' || CASE WHEN i.note IS NOT NULL AND i.note <> '' THEN ' ' || i.note ELSE '' END ELSE '' END || char(10) AS tl FROM "interventions_and_inscriptions" i JOIN "interventions" iam ON i.intervention_id = iam.intervention_id LEFT JOIN "extent" e ON iam.extent_id = e.extent_id LEFT JOIN "methods" m ON iam.method_id = m.method_id JOIN "Max_Thrax" mt ON i.inscription_id = mt.inscription_id CROSS JOIN TargetObject WHERE mt.object_id = TargetObject.selected_obj_id AND i.role_id = 1 AND iam.method_id <> 1)
        SELECT tl FROM (
            SELECT * FROM Sec0_Metadata 
            UNION ALL SELECT * FROM Sec0_Text_Header 
            UNION ALL SELECT * FROM Sec0_Text_Body 
            UNION ALL SELECT * FROM Sec0_Spacer 
            UNION ALL SELECT * FROM Sec1_Header 
            UNION ALL SELECT * FROM Sec1_List 
            UNION ALL SELECT * FROM Sec1_Spacer 
            UNION ALL SELECT * FROM Sec2_Summary 
            UNION ALL SELECT * FROM Sec2_Spacer 
            UNION ALL SELECT * FROM Sec3_Inscription_Headers 
            UNION ALL SELECT * FROM Sec3_Intervention_Details
        ) ORDER BY sg ASC, seq_id ASC, inner_lo ASC;
        """
        cursor.execute(sql, (int(inscription_id),))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
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
        query = f"""
            SELECT m.inscription_id, p.latitude, p.longitude, m.inscription_ref, m.sequence_id, 
                   m.support_id, s.support_name, dt.distributio_titulorum, o.number_of_inscriptions, pr.province_name,
                   p.place_name, p.pleiades_id
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
        st.info("None of the active entries contain geographic coordinates in the database.")
        return

    mymap = folium.Map(location=[matched_points[0][1], matched_points[0][2]], zoom_start=6, tiles=None)
    folium.TileLayer(tiles="https://cawm.lib.uiowa.edu/tiles/{z}/{x}/{y}.png", name="AWMC", overlay=False, control=True, attr="AWMC").add_to(mymap)
    folium.TileLayer(tiles="https://dh.gu.se/tiles/imperium/{z}/{x}/{y}.png", name="DARE", overlay=False, control=True, attr="DARE").add_to(mymap)
   
    # -------------------------------------------------------------
    # NEW COMPRESSED ROADS JSON OVERLAY
    # -------------------------------------------------------------
    optimized_json_path = os.path.join(BASE_DIR, "itinere_land_roads_optimized.json")
    if os.path.exists(optimized_json_path):
        with open(optimized_json_path, "r", encoding="utf-8") as f:
            roads_data = json.load(f)
            
        folium.GeoJson(
            roads_data,
            name="Itinere Land Roads",
            show=True,
            overlay=True,
            control=True,
            style_function=lambda feature: {
                "color": "#ff33a1",
                "weight": 2.2,
                "opacity": 0.8,
            }
        ).add_to(mymap)
    # -------------------------------------------------------------
    # -------------------------------------------------------------

    inscriptions_layer = folium.FeatureGroup(name="Inscriptions", show=True)

    for row in matched_points:
        f_id, lat, lon, ref_text, seq_id, support_id, support_name, dist_tit, num_ins = row[:9]
        province_name = row[9] if len(row) > 9 else "N/A"
        place_name_val = row[10] if len(row) > 10 else None
        pleiades_id_val = row[11] if len(row) > 11 else None

        if lat and lon:
            ins_count = num_ins if num_ins is not None else "N/A"
            sequence = seq_id if seq_id is not None else "N/A"
            province = province_name if province_name is not None else "N/A"
            
            place = place_name_val if place_name_val is not None else "N/A"
            
            if pleiades_id_val and str(pleiades_id_val).strip():
                # Cast to string and strip spaces to keep the URL perfectly clean
                clean_pleiades_id = str(pleiades_id_val).strip()
                pleiades_link = f'<a href="https://pleiades.stoa.org/places/{clean_pleiades_id}" target="_blank">{clean_pleiades_id}</a>'
            else:
                pleiades_link = 'N/A'
                
            ref_link = f'<a href="https://edcs.hist.uzh.ch/en/search?edcs-id={ref_text}" target="_blank">{ref_text}</a>' if ref_text else 'N/A'
            
            # 4. Inject structural line into the base metadata popup layout block
            report_url = f"https://maximinusthraxdatabaseui.streamlit.app/?ins_id={f_id}"

            popup_content = (
                f"<b>Inscription ID:</b> <a href='{report_url}' target='_blank'>{f_id}</a> | <b>Ref:</b> {ref_link}<br>"
                f"<b>Number of Inscriptions:</b> {ins_count} | <b>Sequence ID:</b> {sequence}<br>"
                f"<b>Province:</b> {province}<br>"
                f"<b>Place:</b> {place} | <b>Pleiades:</b> {pleiades_link}"
            )
            
            # 5. The rest of your milestone/road calculations remain completely untouched:
            if support_id in (1, 2):
                popup_content += "<br><b>Milestone</b>"
                info = road_links_dict.get(f_id, {'roads': []})
                if info['roads']:
                    road_name = ", ".join(list(set(r[0] for r in info['roads'] if r[0])))
                    popup_content += f"<br><b>road segment:</b> {road_name if road_name else 'N/A'}"
                    links = [f'<a href="https://itiner-e.org/?id={r[1]}" target="_blank">itiner-e.org/?id={r[1]}</a>' for r in info['roads'] if r[1]]
                    popup_content += f"<br><b>itiner-e link to road:</b> {', '.join(links) if links else 'N/A'}"
                else:
                    popup_content += "<br><b>road segment:</b> N/A<br><b>itiner-e link to road:</b> N/A"
            else:
                popup_content += f"<br><b>distributio titulorum:</b> {dist_tit if dist_tit else 'N/A'}<br><b>support:</b> {support_name if support_name else 'N/A'}"
            folium.CircleMarker(
                location=[lat, lon], radius=7, color="#002fa7", fill=True, fill_color="#33b5e5", fill_opacity=0.9,
                popup=folium.Popup(popup_content, min_width=320, max_width=480), tooltip=f"ID: {f_id}"
            ).add_to(inscriptions_layer)

    inscriptions_layer.add_to(mymap)

    
    folium.LayerControl(collapsed=False).add_to(mymap)
    st.session_state.trigger_map_html = mymap._repr_html_()

# =========================================================
# APPLICATION CORE GRAPHICAL INTERFACE
# =========================================================

query_params = st.query_params

if "ins_id" in query_params:
    url_id = query_params["ins_id"]
    if url_id.isdigit():
        st.query_params.clear() 
        fetch_metadata_by_id(url_id)

elif "person_id" in query_params:
    url_per_id = query_params["person_id"]
    if url_per_id.isdigit():
        st.query_params.clear() 
        generate_person_report(url_per_id)

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
# Main Word/Phrase Search Row with Generate Map
st.markdown("### Key Word or Phrase Search")
col_text1, col_text2, col_text3 = st.columns([2, 1, 1])
with col_text1:    
    text_input_var = st.text_input(
        "Enter search text:", 
        placeholder="e.g., Quintus Decius",
        key="main_text_input", 
        label_visibility="collapsed"
    )
with col_text2:
    if st.button("Search Text", key="btn_execute_text", use_container_width=True, type="primary"):
        run_standard_search(text_input_var)
with col_text3:
    if st.button("Generate Map", key="global_map_btn", use_container_width=True, type="primary"):
        generate_active_map()
# Full Reports Panel Layout Execution Shell
st.markdown("### Inscription Report and Person Report Generator")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

with col_s1:
    ref_input_var = st.text_input("EDCS number:", placeholder="e.g. EDCS-12345678", key="edcs_report_input")
    if st.button("Generate Inscription Report (EDCS)", use_container_width=True, type="primary"):
        if ref_input_var.strip():
            # Run the search which fully updates st.session_state.active_inscription_ids
            run_ref_search(ref_input_var)
with col_s2:
    id_input_var = st.text_input("Inscription ID:", placeholder="e.g. 24")
    if st.button("Generate Inscription Report (ID)", use_container_width=True, type="primary"):
        if id_input_var.strip():
            st.session_state.active_inscription_ids = [int(id_input_var.strip())]
        fetch_metadata_by_id(id_input_var)
with col_s3:
    pname_input_var = st.text_input("Lookup Person ID by Name:", placeholder="e.g. Maximinus")
    if st.button("Find Person", use_container_width=True):
        lookup_person_options(pname_input_var)

with col_s4:
    if st.session_state.person_matches:
        options_list = [f"{row[1]} (ID: {row[0]})" for row in st.session_state.person_matches]
        selected_option = st.selectbox("Select Person:", options_list)
        
        if st.button("Generate Person Report", use_container_width=True, type="primary"):
            extracted_id = selected_option.split("(ID: ")[-1].replace(")", "").strip()
            generate_person_report(extracted_id)
    else:
        pid_input_var = st.text_input("Person Selector:", placeholder="Select from the list")
        if st.button("Generate Person Report", use_container_width=True, type="primary"):
            generate_person_report(pid_input_var)
# =========================================================
# ADVANCED SEARCH WRAPPER
# =========================================================
with st.expander("🔍 Click to Expand / Collapse Advanced Search", expanded=False):
    st.markdown("### Advanced Search")
    
    # Text search assigned to its own private, isolated row context
    f_text = st.text_input("Advanced Text Search (Boolean Logic Operators Allowed):", placeholder="e.g. Maximinus AND legatus")
    
    st.markdown("---")
    st.markdown("### Filters")
    
    # --- DYNAMIC PERSON DATABASE LOOKUP ---
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT person_id, person_name FROM persons ORDER BY person_name ASC;")
        db_persons = cursor.fetchall()
        conn.close()
        person_options = {row[0]: row[1] for row in db_persons}
    except Exception:
        person_options = {}

    col1, col2, col3 = st.columns(3)
    with col1:
        # 1. Relevance (mt.relevance_index)
        f_rel = st.selectbox("Relevance:", get_filter_options("Max_Thrax", "relevance_index"))
        
        # 2. Distributio Titulorum (dt.distributio_titulorum)
        f_dist_tit = st.multiselect("Distributio Titulorum | Type of Inscription:", [opt for opt in get_filter_options("distributio_titulorum", "distributio_titulorum") if opt != "All"])
        
        # 3. Material (m.material_name)
        f_obj_mat = st.multiselect("Material:", [opt for opt in get_filter_options("materials", "material_name") if opt != "All"])
        
        # 4. Support Type (s.support_name) -> UNTOUCHED, sits in its original natural position
        f_sup_name = st.multiselect("Support Type:", [opt for opt in get_filter_options("support", "support_name") if opt != "All"])
        
        # 5. Context Type (ct.context_name)
        f_in_con = st.multiselect("Context Type:", [opt for opt in get_filter_options("context_types", "context_name") if opt != "All"])
        
        # 6. Province (pr.province_name)
        f_prov = st.multiselect("Province:", [opt for opt in get_filter_options("provinces", "province_name") if opt != "All"])

    with col2:
        # 7. Inscriptions on Object (o.number_of_inscriptions)
        f_num_ins = st.multiselect("Inscriptions on Object:", [opt for opt in get_filter_options("objects", "number_of_inscriptions") if opt != "All"])
        
        # 8. Person (ip_f.person_id)
        f_person_id = st.multiselect(
            "Person:",
            options=list(person_options.keys()),
            format_func=lambda x: person_options[x]
        )
        
        # Radio toggle underneath Person
        f_person_operator = st.radio(
            "Match selected people using:",
            options=["OR (Any of these people)", "AND (All of these people)"],
            horizontal=True,
            index=0,
            label_visibility="collapsed"
        )
        
        # --- VISUAL ALIGNMENT INJECTOR ---
    
        st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
        
        # 9. Distributio Virorum (vd.virorum_distributio) -> NOW ALIGNED
        f_vir_dist = st.multiselect("Distributio Virorum | Type of Persons:", [opt for opt in get_filter_options("virorum_distributio", "virorum_distributio") if opt != "All"])
        
        # 10. Status Designation (sd.status_designation)
        f_status = st.multiselect("Status Designation:", [opt for opt in get_filter_options("status_designations", "status_designation") if opt != "All"])
        
        # 11. Office/Military Role (pos.position_description)
        f_pos = st.multiselect("Office/Military Role:", [opt for opt in get_filter_options("positions", "position_description") if opt != "All"])
        
    with col3:
        # 12. Collective/Military Unit (col.collective_name)
        f_unit = st.multiselect("Collective/Military Unit:", [opt for opt in get_filter_options("collectives", "collective_name") if opt != "All"])
        
        # 13. Intervention Status (mt.intervention_status)
        f_interv_stat = st.selectbox("Intervention Status:", get_filter_options("Max_Thrax", "intervention_status"))
        
        # 14. Method of Intervention (meth.method_description)
        f_interv_meth = st.multiselect("Method of Intervention:", [opt for opt in get_filter_options("methods", "method_description") if opt != "All"])
        
        # 15. Extent of Intervention (ext.extent_description)
        f_interv_ext = st.multiselect("Extent of Intervention:", [opt for opt in get_filter_options("extent", "extent_description") if opt != "All"])
        
        # 16. Target of Intervention (targ.target_description)
        f_interv_tgt = st.multiselect("Target of Intervention:", [opt for opt in get_filter_options("targets", "target_description") if opt != "All"])
        
        # 17. Status Tituli (st.status_tituli_name)
        f_status_tituli = st.multiselect("Status Tituli | Preservation Status:", [opt for opt in get_filter_options("status_tituli", "status_tituli_name") if opt != "All"])
    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        if st.button("Execute Advanced Search", key="btn_advanced_filter_search", use_container_width=True, type="primary"):
            form_payload = {
                'text': f_text,
                'relevance_index': f_rel,
                'distributio_titulorum': f_dist_tit,
                'material_name': f_obj_mat,
                'support_name': f_sup_name,
                'context_name': f_in_con,
                'province_name': f_prov,
                'number_of_inscriptions': f_num_ins,
                'person_id': f_person_id,
                'person_operator': "AND" if "AND" in f_person_operator else "OR",
                'virorum_distributio': f_vir_dist,
                'status_designation': f_status,
                'position_description': f_pos,
                'collective_name': f_unit,
                'intervention_status': f_interv_stat,
                'method_description': f_interv_meth,
                'extent_description': f_interv_ext, 
                'target_description': f_interv_tgt,
                'status_tituli_name': f_status_tituli
            }
            execute_advanced_search(form_payload)

    with col2:
        if st.button("Generate Map", key="btn_advanced_map_generation", use_container_width=True):
            generate_active_map()

# Interactive Map Inline Viewport Component 
if st.session_state.trigger_map_html:
    with st.expander("Close / Open Interactive Leaflet Map Layer Visualizer", expanded=True):
        st.components.v1.html(st.session_state.trigger_map_html, height=500, scrolling=True)

# Search Results
st.markdown("### Search Results")

with st.container(height=520, border=True):
    raw_results = st.session_state.search_results
    
    # 1. Clean standard line breaks
    clean_text = raw_results.replace("\r\n", "\n").replace("\r", "\n")
    
    # 2. Break the results apart by double-newlines to isolate the text blocks
    blocks = clean_text.split("\n\n")
    
    for block in blocks:
        # Check if the block is the Inscription Text or contains any lines starting with 3+ dashes
        lines = block.strip().split("\n")
        has_dangerous_dashes = any(line.strip().startswith("---") for line in lines)
        
        # We also keep your original checks just to be completely safe
        if "RIGHT:" in block or "------ /" in block or has_dangerous_dashes:
            # Swap newlines inside just this block to HTML breaks
            html_block = block.replace("\n", "<br>")
            # Force it to display at normal size, keeping your dashes intact and tight
            st.markdown(f'<div style="font-size:16px; font-weight:normal; margin-bottom:1rem;">{html_block}</div>', unsafe_allow_html=True)
        else:
            # For everything else (Context, Material, etc.), keep regular Markdown active
            st.markdown(block)
