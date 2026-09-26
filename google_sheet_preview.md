# Google Sheet Live Sync Preview: `persons` Worksheet

This preview demonstrates exactly how rows and columns appear in your Google Sheet (`https://docs.google.com/spreadsheets/d/1eyZ0ssTTkU3wkRw9vN8CGj8L0aYz80utZQUkFE63nMY/edit`) after applying the updates from `update_google_sheet.py`.

---

### Column Mapping & Styling Rules
1. **Dropdown Columns (`note_fb`, `note_li`, `note_tw`, etc.)**:
   - Automatically set to **`Auto_search`** whenever a URL is populated (leaving existing manual notes intact).
2. **URL Columns (`fb_url`, `LinkedIn_url`, `twitter_url`, etc.)**:
   - Inserted with the direct profile link.
   - **Continuous Shading Applied**:
     - <span style="background-color: #FFE599; padding: 2px 6px; border-radius: 3px; color: #7f6000; font-weight: bold;">Amber (#FFE599)</span>: Potential Match (55% – 69%)
     - <span style="background-color: #D9EAD3; padding: 2px 6px; border-radius: 3px; color: #274e13; font-weight: bold;">Lime (#D9EAD3)</span>: Probable Match (70% – 84%)
     - <span style="background-color: #B6D7A8; padding: 2px 6px; border-radius: 3px; color: #1c3b0d; font-weight: bold;">Sage Green (#B6D7A8)</span>: High / Confirmed (85% – 100%)
3. **Consolidated Final `notes` Column**:
   - Concatenates platform rationales into a single cell, e.g.:  
     `FB- Probable 90% Name match, Province Match; LI- Probable 73% Name match, Province Match`

---

## Spreadsheet View Simulation

| Row | id | full_name | party_name | note_fb | fb_url | note_li | LinkedIn_url | note_tw | twitter_url | notes (Final Column) |
| :---: | :--- | :--- | :--- | :---: | :--- | :---: | :--- | :---: | :--- | :--- |
| **2** | `pers_03` | MLUNGISI JUSTICE SHUSHA | ACDP | `Auto_search` | <span style="background-color: #F6E6A5; padding: 2px 6px; border-radius: 3px;">`facebook.com/mlungisijustice.shusha`</span> | *(empty)* | *(empty)* | *(empty)* | *(empty)* | <span style="background-color: #F6E6A5; padding: 2px 6px; border-radius: 3px;">`FB- Potential 60% Full 3-name match, Location match (Margate), Direct profile`</span> |
| **3** | `pers_56` | GOODWILL MFANUFIKILE CELE | Al Jama-Ah | *(empty)* | *(empty)* | `Auto_search` | <span style="background-color: #F6E6A5; padding: 2px 6px; border-radius: 3px;">`linkedin.com/in/goodwill-mfanufikile-cele...`</span> | *(empty)* | *(empty)* | <span style="background-color: #F6E6A5; padding: 2px 6px; border-radius: 3px;">`LI- Potential 65% Full 3-name match, Location match (Port Shepstone), Direct profile`</span> |
| **4** | `pers_84` | SICELO GOODPRESENT CHILIZA | Democratic Alliance | `Auto_search` | <span style="background-color: #B6D7A8; padding: 2px 6px; border-radius: 3px; font-weight: bold;">`facebook.com/p/Sicelo-Chiliza-615757679...`</span> | `Auto_search` | <span style="background-color: #D9EAD3; padding: 2px 6px; border-radius: 3px;">`linkedin.com/in/sicelo-chiliza-a74bb418`</span> | *(empty)* | *(empty)* | <span style="background-color: #B6D7A8; padding: 2px 6px; border-radius: 3px;">`FB- Probable 90% Name match, Province Match, Direct profile; LI- Probable 73% Name match, Province Match`</span> |
| **5** | `pers_09` | ISAAC SIKHUMBUZO MQADI | ANC | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* |
| **6** | `pers_11` | DIXIE NCIKI | ANC | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* | <span style="background-color: #B6D7A8; padding: 2px 6px; border-radius: 3px; font-weight: bold;">`WEB- Probable 100% Name match, Location match (Umuziwabantu), Civic role match`</span> |
| **7** | `pers_18` | BONGANI GOODMAN NYUSWA | ANC | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* | *(empty)* |
