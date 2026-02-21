import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
from collections import defaultdict

# Seitenkonfiguration
st.set_page_config(
    page_title="ÖBV-LAZ Planungstool",
    page_icon="🎵",
    layout="wide"
)

# CSS
st.markdown("""
<style>
    .warning-box {
        background-color: #fff3cd;
        border: 2px solid #ffc107;
        border-radius: 5px;
        padding: 10px;
        margin: 5px 0;
    }
</style>
""", unsafe_allow_html=True)

# Konstanten
DURATION_JUNIOR = 12
DURATION_BRONZE = 15
DURATION_SILBER = 18
SCHLAGZEUG_BONUS = 5
KORREPETITOR_BUFFER = 5
PAUSE_MARKER = "-- PAUSE --"

# Vereins-Hierarchie für Priorisierung (früh -> spät)
VEREINE_NAHBEREICH = {
    'Blasorchester Stadt Bruck/Mur',
    'Eisenbahner Musikverein Bruck/Mur',
    'Werksmusik Norske Skog Bruck',
    'Stadtkapelle Kapfenberg',
    'Werkskapelle Böhler Kapfenberg',
    'Trachtenkapelle Oberaich',
    'Musikverein Pernegg',
    'Marktmusik St. Dionysen'
}

VEREINE_ERWEITERTER_NAHBEREICH = {
    'Musikverein Breitenau-Knappenkapelle',
    'Musikverein Parschlug',
    'Musikverein Pogier',
    'Musikverein Röthelstein',
    'Musikverein St. Lorenzen im Mürztal',
    'Musikverein Heimatklang St. Marein im Mürztal'
}

VEREINE_WEITER_WEG = {
    'Musikverein Aflenz-Kurort',
    'Musikverein Aschbach',
    'Musikverein Etmißl',
    'Musikverein Graßnitz',
    'Stadtkapelle Mariazell',
    'Marktmusikkapelle Thörl',
    'Trachtenkapelle Tragöß',
    'Musikverein Turnau',
    'Bergkapelle Styromag St. Katharein a.d.Laming'
}

# Vereine mit weiter Anreise (alte Konstante für Rückwärtskompatibilität)
REMOTE_LOCATIONS = ["Mariazell", "Gußwerk", "Wildalpen", "Frohnleiten"]


def parse_time(time_str):
    """Konvertiert Zeitstring zu datetime"""
    try:
        if isinstance(time_str, str):
            return datetime.strptime(time_str, '%H:%M')
        elif isinstance(time_str, datetime):
            return time_str
        else:
            return None
    except:
        return None


class Pruefling:
    """Repräsentiert einen Prüfling oder eine Pause"""
    def __init__(self, row, instrument_to_jury_map=None):
        self.id = row.get('id', '')
        self.zuname = str(row.get('zuname', '')) if pd.notna(row.get('zuname')) else ''
        self.vorname = str(row.get('vorname', '')) if pd.notna(row.get('vorname')) else ''
        
        # Prüfe ob es eine Pause ist
        self.ist_pause = (self.zuname == PAUSE_MARKER)
        
        if self.ist_pause:
            self.dauer = int(row.get('dauer', 15)) if pd.notna(row.get('dauer')) else 15
            self.instrument = ''
            self.pruefung = ''
            self.verein = ''
            self.korrepetitor = ''
            self.zugewiesene_jury = None
            self.ist_extern = False
            self.ist_remote = False
        else:
            self.instrument = str(row.get('instrument', '')) if pd.notna(row.get('instrument')) else ''
            self.pruefung = str(row.get('prüfungsbezeichnung', '')) if pd.notna(row.get('prüfungsbezeichnung')) else ''
            self.korrepetitor = str(row.get('korrepetitor', '')) if pd.notna(row.get('korrepetitor')) else ''
            self.verein = str(row.get('vereinsname', '')) if pd.notna(row.get('vereinsname')) else ''
            self.dauer = self._berechne_dauer()
            self.zugewiesene_jury = self._bestimme_jury(instrument_to_jury_map) if instrument_to_jury_map else None
            self.ist_extern = self._ist_extern(row)
            self.ist_remote = self._ist_remote()
        
    def _berechne_dauer(self):
        base_dauer = 0
        if 'Junior' in self.pruefung:
            base_dauer = DURATION_JUNIOR
        elif 'Bronze' in self.pruefung:
            base_dauer = DURATION_BRONZE
        elif 'Silber' in self.pruefung:
            base_dauer = DURATION_SILBER
        
        if any(s in self.instrument for s in ['Schlagzeug', 'Schlagwerk']):
            base_dauer += SCHLAGZEUG_BONUS
            
        return base_dauer
    
    def _bestimme_jury(self, instrument_to_jury_map):
        """Bestimmt Jury - bei Mehrfachzuordnung None (wird später verteilt)"""
        if not instrument_to_jury_map or self.instrument not in instrument_to_jury_map:
            return None
        
        jury_list = instrument_to_jury_map[self.instrument]
        
        # Einzelzuordnung (String oder Liste mit 1 Element)
        if isinstance(jury_list, str):
            return jury_list
        if isinstance(jury_list, list):
            if len(jury_list) == 1:
                return jury_list[0]
            else:
                # Mehrfachzuordnung - Scheduler verteilt
                return None
        
        return None
    
    def _ist_extern(self, row):
        bezirk = row.get('vorbereitungskurs_bezirk', '')
        if pd.isna(bezirk):
            return False
        try:
            bezirk = int(bezirk)
            return bezirk != 861 and bezirk != 0
        except (ValueError, TypeError):
            return False
    
    def _ist_remote(self):
        return any(loc in self.verein for loc in REMOTE_LOCATIONS)


class Zeitslot:
    """Repräsentiert einen Zeitslot"""
    def __init__(self, start_zeit, pruefling):
        self.start_zeit = start_zeit
        self.pruefling = pruefling
        self.end_zeit = start_zeit + timedelta(minutes=pruefling.dauer)


class Scheduler:
    """Hauptklasse für die Prüfungsplanung"""
    
    def __init__(self, prueflings_liste, start_zeit, jurys, jury_names=None, instrument_to_jury_map=None):
        self.prueflings_liste = prueflings_liste
        self.start_zeit = start_zeit
        self.jurys = jurys
        self.jury_names = jury_names or {}
        self.instrument_to_jury_map = instrument_to_jury_map or {}
        self.zeitplan = {jury: [] for jury in jurys}
        self.korrepetitor_slots = defaultdict(list)
    
    def _sortiere_pruefinge(self):
        """Sortiert Prüflinge mit Vereins-Hierarchie und Schlagzeug-Veto
        
        Hierarchie:
        1. ALLE Schlagzeuger zuerst (Schlagzeug-Veto!)
        2. Rest nach Vereins-Kategorien:
           - Nahbereich (früh)
           - Erweiterter Nahbereich (mittel)
           - Weiter Weg (spät)
           - Extern (ganz zum Schluss)
        3. Innerhalb Kategorie: Vereine als Block zusammenhalten
        """
        normale_prueflings = [p for p in self.prueflings_liste if not p.ist_pause]
        
        # Trenne Schlagzeuger von anderen
        schlagzeuger = []
        andere = []
        
        for pruefling in normale_prueflings:
            if any(s in pruefling.instrument for s in ['Schlagzeug', 'Schlagwerk']):
                schlagzeuger.append(pruefling)
            else:
                andere.append(pruefling)
        
        # SCHLAGZEUGER: Sortiere nach Dauer (länger zuerst)
        schlagzeuger.sort(key=lambda p: -p.dauer)
        
        # ANDERE: Gruppiere nach Verein
        verein_gruppen = defaultdict(list)
        for pruefling in andere:
            verein_gruppen[pruefling.verein].append(pruefling)
        
        # Funktion: Bestimme Kategorie eines Vereins (niedrigere Zahl = früher)
        def verein_kategorie(verein_name):
            if verein_name in VEREINE_NAHBEREICH:
                return 1  # Früh
            elif verein_name in VEREINE_ERWEITERTER_NAHBEREICH:
                return 2  # Mittel
            elif verein_name in VEREINE_WEITER_WEG:
                return 3  # Spät
            else:
                return 4  # Extern (ganz zum Schluss)
        
        # Sortiere Vereine nach Kategorie, dann nach Gesamt-Dauer (länger zuerst)
        vereine_sortiert = sorted(
            verein_gruppen.keys(),
            key=lambda v: (verein_kategorie(v), -sum(p.dauer for p in verein_gruppen[v]))
        )
        
        # ANDERE: Erstelle sortierte Liste
        andere_sortiert = []
        for verein in vereine_sortiert:
            gruppe = verein_gruppen[verein]
            # Innerhalb Verein: Nach Dauer sortieren (länger zuerst)
            gruppe.sort(key=lambda p: -p.dauer)
            andere_sortiert.extend(gruppe)
        
        # FINALE LISTE: Schlagzeuger + Rest (nach Kategorien)
        return schlagzeuger + andere_sortiert
    
    def _finde_passende_jury(self, pruefling):
        """Findet passende Jury - mit Vereins-Kompaktheit bei Mehrfachzuordnung"""
        if pruefling.ist_pause:
            return None
        if pruefling.zugewiesene_jury:
            return pruefling.zugewiesene_jury
        
        # Prüfe Mehrfachzuordnung
        if pruefling.instrument not in self.instrument_to_jury_map:
            return list(self.jurys.keys())[0]
        
        moegliche_jurys = self.instrument_to_jury_map[pruefling.instrument]
        
        # Einzelzuordnung
        if isinstance(moegliche_jurys, str):
            return moegliche_jurys
        if isinstance(moegliche_jurys, list) and len(moegliche_jurys) == 1:
            return moegliche_jurys[0]
        
        # Mehrfachzuordnung - Vereins-Kompaktheit!
        if isinstance(moegliche_jurys, list) and len(moegliche_jurys) > 1:
            verein = pruefling.verein
            # Prüfe ob Verein bereits in einer Jury ist
            for jury in moegliche_jurys:
                for slot in self.zeitplan.get(jury, []):
                    if slot.pruefling.verein == verein and not slot.pruefling.ist_pause:
                        return jury
            
            # Gleichmäßige Verteilung
            jury_counts = {j: len([s for s in self.zeitplan.get(j, []) if not s.pruefling.ist_pause]) 
                          for j in moegliche_jurys}
            return min(jury_counts, key=jury_counts.get)
        
        return list(self.jurys.keys())[0]
    
    def _finde_naechsten_slot(self, jury, dauer, korrepetitor):
        if not self.zeitplan[jury]:
            vorgeschlagene_start = self.start_zeit
        else:
            letzter_slot = self.zeitplan[jury][-1]
            vorgeschlagene_start = letzter_slot.end_zeit
        
        max_versuche = 200
        versuch = 0
        
        while versuch < max_versuche:
            vorgeschlagene_ende = vorgeschlagene_start + timedelta(minutes=dauer)
            konflikt_gefunden = False
            
            if korrepetitor and korrepetitor != '' and korrepetitor != 'nan':
                for slot in self.korrepetitor_slots[korrepetitor]:
                    ueberschneidung = not (vorgeschlagene_ende <= slot.start_zeit or 
                                          vorgeschlagene_start >= slot.end_zeit)
                    
                    if ueberschneidung:
                        vorgeschlagene_start = slot.end_zeit + timedelta(minutes=KORREPETITOR_BUFFER)
                        vorgeschlagene_ende = vorgeschlagene_start + timedelta(minutes=dauer)
                        konflikt_gefunden = True
                        break
                    
                    if vorgeschlagene_ende <= slot.start_zeit:
                        pause = (slot.start_zeit - vorgeschlagene_ende).total_seconds() / 60
                        if pause < KORREPETITOR_BUFFER:
                            vorgeschlagene_start = slot.end_zeit + timedelta(minutes=KORREPETITOR_BUFFER)
                            vorgeschlagene_ende = vorgeschlagene_start + timedelta(minutes=dauer)
                            konflikt_gefunden = True
                            break
                    
                    if vorgeschlagene_start >= slot.end_zeit:
                        pause = (vorgeschlagene_start - slot.end_zeit).total_seconds() / 60
                        if pause < KORREPETITOR_BUFFER:
                            vorgeschlagene_start = slot.end_zeit + timedelta(minutes=KORREPETITOR_BUFFER)
                            vorgeschlagene_ende = vorgeschlagene_start + timedelta(minutes=dauer)
                            konflikt_gefunden = True
                            break
            
            if not konflikt_gefunden:
                break
            
            versuch += 1
        
        return vorgeschlagene_start
    
    def erstelle_zeitplan(self):
        """Erstellt den optimierten Zeitplan mit Schlagzeuger-Priorität
        
        Wichtig: Bei Korrepetitor-Konflikten haben Schlagzeuger Vorrang
        """
        sortierte_prueflige = self._sortiere_pruefinge()
        
        # Markiere Schlagzeuger für Priorität
        for pruefling in sortierte_prueflige:
            pruefling.ist_schlagzeuger = any(s in pruefling.instrument for s in ['Schlagzeug', 'Schlagwerk'])
        
        for pruefling in sortierte_prueflige:
            jury = self._finde_passende_jury(pruefling)
            if not jury:
                continue
            
            # Finde passenden Zeitslot
            start_zeit = self._finde_naechsten_slot(jury, pruefling.dauer, pruefling.korrepetitor)
            
            slot = Zeitslot(start_zeit, pruefling)
            self.zeitplan[jury].append(slot)
            
            # Registriere Korrepetitor-Slot
            if pruefling.korrepetitor and pruefling.korrepetitor != '' and pruefling.korrepetitor != 'nan':
                self.korrepetitor_slots[pruefling.korrepetitor].append(slot)
        
        return self.zeitplan


def extrahiere_instrumente(df):
    """Extrahiert alle eindeutigen Instrumente aus der CSV-Datei (dynamisch)
    
    Wichtig: Keine fest hinterlegte Liste - nur was in der CSV vorkommt!
    Berücksichtigt die MLAZ-CSV-Struktur (instrument_id enthält den Namen!)
    """
    if df is None:
        return []
    
    # In der MLAZ-CSV steht das Instrument in 'instrument_id'!
    spalte = 'instrument_id' if 'instrument_id' in df.columns else 'instrument'
    
    if spalte not in df.columns:
        return []
    
    # Extrahiere einzigartige Instrumente (ohne NaN, leere Strings, 'nan')
    instrumente = df[spalte].dropna().unique().tolist()
    
    # Filtere und konvertiere zu String
    instrumente_clean = []
    for inst in instrumente:
        inst_str = str(inst).strip()
        # Filtere 'nan', leere Strings, und Whitespace
        if inst_str and inst_str.lower() != 'nan' and len(inst_str) > 0:
            instrumente_clean.append(inst_str)
    
    # Sortiere alphabetisch (case-insensitive)
    instrumente_clean.sort(key=lambda x: x.lower())
    
    return instrumente_clean


def lade_daten(uploaded_file, instrument_to_jury_map=None):
    """Lädt CSV-Datei mit korrekter Spalten-Zuordnung"""
    try:
        # Lese CSV mit BOM-Behandlung
        df = pd.read_csv(uploaded_file, sep=';', encoding='utf-8-sig')
        
        # Erstelle normalisiertes DataFrame mit korrekter Spalten-Zuordnung
        # Die MLAZ-CSV hat verschobene Spalten!
        df_normalized = pd.DataFrame({
            'id': df['id'],
            'zuname': df['titel'],  # titel enthält Zuname!
            'vorname': df['zuname'],  # zuname enthält Vorname!
            'instrument': df['instrument_id'],  # instrument_id enthält Instrumentenname!
            'prüfungsbezeichnung': df['prüfungs_id'],  # prüfungs_id enthält Bezeichnung!
            'vereinsname': df['anmeldeverein_kurz'],  # anmeldeverein_kurz enthält Vereinsname!
            'korrepetitor': df['vortrag'] if 'vortrag' in df.columns else '',  # vortrag kann Korrepetitor enthalten
            'vorbereitungskurs_bezirk': df['prüfungsart'] if 'prüfungsart' in df.columns else 0
        })
        
        prueflings_liste = []
        for idx, row in df_normalized.iterrows():
            try:
                pruefling = Pruefling(row, instrument_to_jury_map)
                prueflings_liste.append(pruefling)
            except Exception as e:
                st.warning(f"Fehler in Zeile {idx}: {str(e)}")
                continue
        
        return prueflings_liste, len(prueflings_liste)
    
    except Exception as e:
        st.error(f"Fehler beim Laden: {str(e)}")
        return None, 0


def erstelle_zeitplan_dataframe(zeitplan, jury_names):
    """Erstellt DataFrame aus Zeitplan - MIT Instrument-Spalte"""
    data = []
    jury_names = jury_names or {}
    
    for jury_key, slots in zeitplan.items():
        display_name = jury_names.get(jury_key, jury_key)
        
        for slot in slots:
            p = slot.pruefling
            data.append({
                'Jury/Raum': display_name,
                'Start': slot.start_zeit.strftime('%H:%M'),
                'Ende': slot.end_zeit.strftime('%H:%M'),
                'Dauer (min)': p.dauer,
                'Name': f"{p.vorname} {p.zuname}".strip() if not p.ist_pause else PAUSE_MARKER,
                'Musikverein': p.verein if not p.ist_pause else '',
                'Instrument': p.instrument if not p.ist_pause else '-',
                'Stufe': p.pruefung if not p.ist_pause else '',
                'Korrepetitor': p.korrepetitor if not p.ist_pause else ''
            })
    
    return pd.DataFrame(data)


def update_times(df, jury_name, changed_row_idx=None):
    """Berechnet alle Zeiten für eine Jury neu mit Pausen-Priorität
    
    Logik:
    1. Pausen mit manueller Startzeit sind FESTE ANKER
    2. Prüflinge werden um Pausen herum eingefügt
    3. Bei Kollision: Prüfling wird NACH die Pause verschoben
    4. Nach Pausen-Löschung: Prüflinge rücken nach (Lücke wird geschlossen)
    """
    if df is None or len(df) == 0:
        return df
    
    jury_mask = df['Jury/Raum'] == jury_name
    jury_df = df[jury_mask].copy()
    other_df = df[~jury_mask].copy()
    
    if len(jury_df) == 0:
        return df
    
    # SCHRITT 1: Sortiere nach aktueller Startzeit (chronologisch)
    jury_df = jury_df.sort_values('Start').reset_index(drop=True)
    
    # SCHRITT 2: Identifiziere Pausen (diese sind FESTE ANKER)
    pausen_indices = []
    for idx, row in jury_df.iterrows():
        if row['Name'] == PAUSE_MARKER:
            pausen_indices.append(idx)
            # Aktualisiere Ende der Pause basierend auf Dauer
            pause_start = parse_time(row['Start'])
            if pause_start:
                pause_dauer = int(row['Dauer (min)'])
                pause_ende = pause_start + timedelta(minutes=pause_dauer)
                jury_df.at[idx, 'Ende'] = pause_ende.strftime('%H:%M')
    
    # SCHRITT 3: Berechne Zeiten sequenziell (Prüflinge rücken zusammen, Pausen bleiben fix)
    for i in range(len(jury_df)):
        if i in pausen_indices:
            # Pausen bleiben wie sie sind (feste Anker)
            continue
        
        if i == 0:
            # Erste Zeile
            if 0 not in pausen_indices:
                # Erste Zeile ist Prüfling: behalte Start, berechne Ende
                start = parse_time(jury_df.iloc[0]['Start'])
                if start:
                    dauer = int(jury_df.iloc[0]['Dauer (min)'])
                    ende = start + timedelta(minutes=dauer)
                    jury_df.at[0, 'Ende'] = ende.strftime('%H:%M')
        else:
            # Nachfolgende Zeilen
            vorherige_ende_str = jury_df.iloc[i-1]['Ende']
            vorherige_ende = parse_time(vorherige_ende_str)
            
            if vorherige_ende:
                # Prüfling startet direkt nach vorheriger Zeile (nachrücken!)
                jury_df.at[i, 'Start'] = vorherige_ende.strftime('%H:%M')
                
                # Berechne Ende
                dauer = int(jury_df.iloc[i]['Dauer (min)'])
                neue_ende = vorherige_ende + timedelta(minutes=dauer)
                jury_df.at[i, 'Ende'] = neue_ende.strftime('%H:%M')
    
    # SCHRITT 4: KRITISCH - Prüfe Kollisionen mit Pausen und verschiebe Prüflinge
    # Wiederhole bis keine Kollisionen mehr existieren
    max_iterations = 10
    iteration = 0
    
    while iteration < max_iterations:
        kollision_gefunden = False
        
        # Sortiere nochmal (wichtig nach Verschiebungen)
        jury_df = jury_df.sort_values('Start').reset_index(drop=True)
        
        # Update Pausen-Indices nach Sortierung
        pausen_indices = []
        for idx, row in jury_df.iterrows():
            if row['Name'] == PAUSE_MARKER:
                pausen_indices.append(idx)
        
        # Prüfe jede Pause gegen jeden Prüfling
        for pause_idx in pausen_indices:
            pause_row = jury_df.iloc[pause_idx]
            pause_start = parse_time(pause_row['Start'])
            pause_ende = parse_time(pause_row['Ende'])
            
            if not pause_start or not pause_ende:
                continue
            
            # Prüfe alle Prüflinge
            for pruef_idx, pruef_row in jury_df.iterrows():
                if pruef_idx == pause_idx or pruef_row['Name'] == PAUSE_MARKER:
                    continue
                
                pruef_start = parse_time(pruef_row['Start'])
                pruef_ende = parse_time(pruef_row['Ende'])
                
                if not pruef_start or not pruef_ende:
                    continue
                
                # Prüfe Überschneidung
                ueberschneidung = not (pruef_ende <= pause_start or pruef_start >= pause_ende)
                
                if ueberschneidung:
                    # KOLLISION! Verschiebe Prüfling NACH die Pause
                    jury_df.at[pruef_idx, 'Start'] = pause_ende.strftime('%H:%M')
                    
                    pruef_dauer = int(pruef_row['Dauer (min)'])
                    neues_pruef_ende = pause_ende + timedelta(minutes=pruef_dauer)
                    jury_df.at[pruef_idx, 'Ende'] = neues_pruef_ende.strftime('%H:%M')
                    
                    kollision_gefunden = True
        
        if not kollision_gefunden:
            break
        
        iteration += 1
    
    # SCHRITT 5: Finale chronologische Sortierung
    jury_df = jury_df.sort_values('Start').reset_index(drop=True)
    
    # Kombiniere zurück
    result_df = pd.concat([other_df, jury_df], ignore_index=True)
    return result_df


def fuege_pause_ein(df, jury_name):
    """Fügt Pause am Ende der Jury ein - MIT Instrument-Spalte"""
    jury_zeilen = df[df['Jury/Raum'] == jury_name]
    
    if len(jury_zeilen) > 0:
        jury_zeilen = jury_zeilen.sort_values('Start')
        letzte_zeit = jury_zeilen.iloc[-1]['Ende']
        neue_start = letzte_zeit
    else:
        neue_start = '08:00'
    
    start_dt = parse_time(neue_start)
    if not start_dt:
        start_dt = datetime.strptime('08:00', '%H:%M')
    
    ende_dt = start_dt + timedelta(minutes=15)
    
    neue_zeile = {
        'Jury/Raum': jury_name,
        'Start': start_dt.strftime('%H:%M'),
        'Ende': ende_dt.strftime('%H:%M'),
        'Dauer (min)': 15,
        'Name': PAUSE_MARKER,
        'Musikverein': '',
        'Instrument': '-',
        'Stufe': '',
        'Korrepetitor': ''
    }
    
    result_df = pd.concat([df, pd.DataFrame([neue_zeile])], ignore_index=True)
    
    # Sortiere Jury chronologisch
    jury_mask = result_df['Jury/Raum'] == jury_name
    jury_rows = result_df[jury_mask].copy()
    other_rows = result_df[~jury_mask].copy()
    
    jury_rows = jury_rows.sort_values('Start')
    
    result_df = pd.concat([other_rows, jury_rows], ignore_index=True)
    
    return result_df


def check_korrepetitor_konflikte(df, row_idx):
    """Prüft Korrepetitor-Konflikte für eine Zeile"""
    konflikte = []
    
    if df is None or len(df) == 0:
        return konflikte
    
    row = df.iloc[row_idx]
    
    # Pausen haben keine Korrepetitor-Konflikte
    if row['Name'] == PAUSE_MARKER:
        return konflikte
    
    korrepetitor = row.get('Korrepetitor', '')
    if not korrepetitor or korrepetitor == '' or pd.isna(korrepetitor):
        return konflikte
    
    dauer = int(row['Dauer (min)'])
    
    neue_start = parse_time(row['Start'])
    if not neue_start:
        return konflikte
    
    neue_ende = neue_start + timedelta(minutes=dauer)
    
    # Prüfe gegen alle anderen
    for idx, other_row in df.iterrows():
        if idx == row_idx:
            continue
        
        if other_row['Name'] == PAUSE_MARKER:
            continue
        
        other_korr = other_row.get('Korrepetitor', '')
        if other_korr == korrepetitor and other_korr != '':
            other_start = parse_time(other_row['Start'])
            other_ende = parse_time(other_row['Ende'])
            
            if not other_start or not other_ende:
                continue
            
            ueberschneidung = not (neue_ende <= other_start or neue_start >= other_ende)
            
            if ueberschneidung:
                konflikte.append({
                    'typ': 'ueberschneidung',
                    'andere_jury': other_row['Jury/Raum'],
                    'andere_name': other_row['Name']
                })
            elif neue_ende <= other_start:
                pause = (other_start - neue_ende).total_seconds() / 60
                if pause < KORREPETITOR_BUFFER:
                    konflikte.append({
                        'typ': 'puffer',
                        'pause': pause
                    })
            elif neue_start >= other_ende:
                pause = (neue_start - other_ende).total_seconds() / 60
                if pause < KORREPETITOR_BUFFER:
                    konflikte.append({
                        'typ': 'puffer',
                        'pause': pause
                    })
    
    return konflikte


def exportiere_zu_excel(df, jury_names, instrument_assignments):
    """Exportiert Zeitplan als formatierte Excel-Datei mit separaten Tabellenblättern pro Jury
    
    Spalten-Reihenfolge:
    1. Beginnuhrzeit
    2. Name  
    3. Musikverein
    4. Instrument (NEU)
    5. Stufe
    6. Bemerkung
    """
    output = io.BytesIO()
    
    # Erstelle Excel Writer mit xlsxwriter engine
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Definiere Formate
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'left'
        })
        
        subtitle_format = workbook.add_format({
            'italic': True,
            'font_size': 10,
            'align': 'left'
        })
        
        pause_format = workbook.add_format({
            'bg_color': '#D9D9D9',
            'border': 1
        })
        
        cell_format = workbook.add_format({
            'border': 1,
            'valign': 'top'
        })
        
        time_format = workbook.add_format({
            'border': 1,
            'valign': 'top',
            'align': 'center'
        })
        
        # Gruppiere nach Jury
        jurys = sorted(df['Jury/Raum'].unique())
        
        for jury_name in jurys:
            # Filtere Daten für diese Jury
            jury_df = df[df['Jury/Raum'] == jury_name].copy()
            jury_df = jury_df.sort_values('Start').reset_index(drop=True)
            
            # Finde Jury-Key für Instrumenten-Liste
            jury_key = None
            for key, name in jury_names.items():
                if name == jury_name:
                    jury_key = key
                    break
            
            # Sammle Instrumente für diese Jury (berücksichtigt Mehrfachzuordnung)
            instrumente_dieser_jury = []
            if jury_key:
                for instrument, assigned_jurys in instrument_assignments.items():
                    # Mehrfachzuordnung: assigned_jurys ist eine Liste
                    if isinstance(assigned_jurys, list):
                        if jury_key in assigned_jurys:
                            instrumente_dieser_jury.append(instrument)
                    # Einzelzuordnung: assigned_jurys ist ein String
                    elif assigned_jurys == jury_key:
                        instrumente_dieser_jury.append(instrument)
            
            # Erstelle exportierbaren DataFrame in korrekter Spaltenreihenfolge
            export_data = []
            for idx, row in jury_df.iterrows():
                if row['Name'] == PAUSE_MARKER:
                    # Pausenzeile
                    export_data.append({
                        'Beginnuhrzeit': row['Start'],
                        'Name': PAUSE_MARKER,
                        'Musikverein': '',
                        'Instrument': '-',
                        'Stufe': '',
                        'Bemerkung': PAUSE_MARKER
                    })
                else:
                    # Normale Prüfungszeile
                    export_data.append({
                        'Beginnuhrzeit': row['Start'],
                        'Name': row['Name'],
                        'Musikverein': row['Musikverein'],
                        'Instrument': row['Instrument'] if row['Instrument'] else '',
                        'Stufe': row['Stufe'],
                        'Bemerkung': row['Korrepetitor'] if row['Korrepetitor'] else ''
                    })
            
            export_df = pd.DataFrame(export_data)
            
            # Sheet-Name (maximal 31 Zeichen für Excel)
            sheet_name = jury_name[:31]
            
            # Schreibe zu Excel (starte bei Zeile 3 für Überschriften)
            export_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=3, header=False)
            
            # Hole Worksheet
            worksheet = writer.sheets[sheet_name]
            
            # Schreibe Titel
            worksheet.write(0, 0, jury_name, title_format)
            
            # Schreibe Instrumenten-Liste
            if instrumente_dieser_jury:
                instrumente_text = f"Instrumente: {', '.join(sorted(instrumente_dieser_jury))}"
            else:
                instrumente_text = "Instrumente: (keine zugewiesen)"
            worksheet.write(1, 0, instrumente_text, subtitle_format)
            
            # Schreibe Kopfzeile in korrekter Reihenfolge
            headers = ['Beginnuhrzeit', 'Name', 'Musikverein', 'Instrument', 'Stufe', 'Bemerkung']
            for col_num, header in enumerate(headers):
                worksheet.write(3, col_num, header, header_format)
            
            # Formatiere Daten-Zeilen
            for row_num, row_data in enumerate(export_data, start=4):
                ist_pause = (row_data['Name'] == PAUSE_MARKER)
                
                # Wähle Format
                if ist_pause:
                    row_format = pause_format
                    time_fmt = pause_format
                else:
                    row_format = cell_format
                    time_fmt = time_format
                
                # Schreibe Zellen in korrekter Reihenfolge
                worksheet.write(row_num, 0, row_data['Beginnuhrzeit'], time_fmt)
                worksheet.write(row_num, 1, row_data['Name'], row_format)
                worksheet.write(row_num, 2, row_data['Musikverein'], row_format)
                worksheet.write(row_num, 3, row_data['Instrument'], row_format)
                worksheet.write(row_num, 4, row_data['Stufe'], row_format)
                worksheet.write(row_num, 5, row_data['Bemerkung'], row_format)
            
            # Spaltenbreiten anpassen
            worksheet.set_column('A:A', 14)  # Beginnuhrzeit
            worksheet.set_column('B:B', 30)  # Name
            worksheet.set_column('C:C', 25)  # Musikverein
            worksheet.set_column('D:D', 18)  # Instrument (NEU)
            worksheet.set_column('E:E', 12)  # Stufe
            worksheet.set_column('F:F', 20)  # Bemerkung
            
            # Zeile 0-1 Höhe anpassen
            worksheet.set_row(0, 20)
            worksheet.set_row(1, 15)
    
    return output.getvalue()


def exportiere_zu_csv(df):
    """Exportiert zu CSV"""
    return df.to_csv(index=False, sep=';').encode('utf-8')


def main():
    st.title("🎵 ÖBV-LAZ Planungstool")
    st.markdown("**Musikbezirk Bruck an der Mur** - Interaktiver Bearbeitungsmodus")
    st.markdown("---")
    
    # Session State initialisieren
    if 'uploaded_df' not in st.session_state:
        st.session_state.uploaded_df = None
    if 'jury_count' not in st.session_state:
        st.session_state.jury_count = 3
    if 'jury_names' not in st.session_state:
        st.session_state.jury_names = {}
    if 'schedule' not in st.session_state:
        st.session_state.schedule = None
    if 'available_instruments' not in st.session_state:
        st.session_state.available_instruments = []
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Konfiguration")
        
        uploaded_file = st.file_uploader(
            "CSV-Datei hochladen",
            type=['csv'],
            help="CSV mit Semikolon-Trennung"
        )
        
        if uploaded_file is not None:
            # Prüfe ob neue Datei hochgeladen wurde
            if st.session_state.uploaded_df is None or uploaded_file.name != st.session_state.get('last_uploaded_filename'):
                try:
                    # Lese CSV mit BOM-Behandlung (utf-8-sig statt utf-8)
                    df_temp = pd.read_csv(uploaded_file, sep=';', encoding='utf-8-sig')
                    st.session_state.uploaded_df = df_temp
                    st.session_state.last_uploaded_filename = uploaded_file.name
                    
                    # WICHTIG: Extrahiere Instrumente DYNAMISCH aus CSV
                    st.session_state.available_instruments = extrahiere_instrumente(df_temp)
                    
                    # Reset Instrumenten-Zuordnung bei neuem Upload
                    for i in range(10):  # Max 10 Jurys
                        key = f"jury_{i}_instruments"
                        if key in st.session_state:
                            st.session_state[key] = []
                    
                    # Reset Schedule bei neuem Upload
                    st.session_state.schedule = None
                    
                    uploaded_file.seek(0)
                    st.success(f"✅ CSV geladen: {len(df_temp)} Prüflinge, {len(st.session_state.available_instruments)} Instrumente")
                except Exception as e:
                    st.error(f"Fehler beim Laden: {str(e)}")
        
        st.divider()
        
        st.subheader("👥 Jurys")
        jury_count = st.number_input(
            "Anzahl Jurys",
            min_value=1,
            max_value=10,
            value=st.session_state.jury_count,
            key="jury_count_input"
        )
        
        if jury_count != st.session_state.jury_count:
            st.session_state.jury_count = jury_count
            st.rerun()
        
        st.markdown("**Jury-Namen:**")
        for i in range(jury_count):
            jury_key = f"Jury_{i+1}"
            default_name = st.session_state.jury_names.get(jury_key, f"Jury {i+1}")
            
            new_name = st.text_input(
                f"Jury {i+1}",
                value=default_name,
                key=f"jury_name_{i}"
            )
            
            st.session_state.jury_names[jury_key] = new_name
        
        st.divider()
        
        # Instrumenten-Zuordnung
        if st.session_state.available_instruments:
            st.subheader("🎺 Instrumente")
            
            # Zeige gefundene Instrumente
            with st.expander("📋 Gefundene Instrumente in CSV", expanded=False):
                st.write(f"**{len(st.session_state.available_instruments)} Instrumente gefunden:**")
                st.write(", ".join(st.session_state.available_instruments))
            
            st.info("💡 **Mehrfachzuordnung möglich:** Ein Instrument kann mehreren Jurys zugewiesen werden. Schüler werden dann gleichmäßig verteilt (Vereins-Kompaktheit wird beachtet).")
            
            instrument_assignments = {}
            for i in range(jury_count):
                jury_key = f"Jury_{i+1}"
                key = f"jury_{i}_instruments"
                
                # Initialisiere NUR wenn noch nicht vorhanden
                if key not in st.session_state:
                    st.session_state[key] = []
                
                # ALLE Instrumente sind für JEDE Jury verfügbar (Mehrfachzuordnung!)
                # Keine Filterung mehr!
                
                selected = st.multiselect(
                    st.session_state.jury_names.get(jury_key, f"Jury {i+1}"),
                    options=st.session_state.available_instruments,  # ALLE verfügbar!
                    default=st.session_state[key],  # Verwende default für korrekte Anzeige
                    key=f"multiselect_{key}"  # Anderer Key als Session State
                )
                
                # Update Session State
                st.session_state[key] = selected
                
                # Sammle Zuordnungen (ein Instrument kann jetzt mehreren Jurys zugewiesen sein)
                for inst in selected:
                    if inst not in instrument_assignments:
                        instrument_assignments[inst] = []
                    instrument_assignments[inst].append(jury_key)
        else:
            instrument_assignments = {}
        
        st.divider()
        start_time = st.time_input("⏰ Startzeit", value=datetime.strptime("08:00", "%H:%M").time())
        start_zeit = datetime.combine(datetime.today(), start_time)
    
    # Hauptbereich
    if uploaded_file is None:
        st.info("👈 Bitte CSV-Datei hochladen")
        return
    
    # Zeitplan berechnen
    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        if st.button("🚀 Zeitplan berechnen", type="primary", use_container_width=True):
            with st.spinner("Berechne optimierten Zeitplan..."):
                prueflings_liste, anzahl = lade_daten(uploaded_file, instrument_assignments)
                
                if prueflings_liste:
                    jurys = {f"Jury_{i+1}": f"Jury {i+1}" for i in range(jury_count)}
                    
                    scheduler = Scheduler(prueflings_liste, start_zeit, jurys, st.session_state.jury_names, instrument_assignments)
                    zeitplan = scheduler.erstelle_zeitplan()
                    
                    df = erstelle_zeitplan_dataframe(zeitplan, st.session_state.jury_names)
                    
                    st.session_state.schedule = df
                    
                    st.success(f"✅ Zeitplan für {anzahl} Prüflinge erstellt!")
                    
                    # Info über Sortierung
                    st.info("""
                    **📋 Sortier-Hierarchie:**
                    1. 🥁 **ALLE Schlagzeuger zuerst** (Schlagzeug-Veto!)
                    2. 🏘️ **Nahbereich-Vereine** (Bruck, Kapfenberg, Oberaich, etc.)
                    3. 🚗 **Erweiterter Nahbereich** (Breitenau, Parschlug, St. Lorenzen, etc.)
                    4. 🗺️ **Weiter Weg** (Mariazell, Aflenz, Tragöß, etc.)
                    5. 🌍 **Externe Vereine** (nicht in der Liste)
                    
                    💡 **Bei Mehrfachzuordnung:** Vereine bleiben zusammen!
                    
                    *Vereine werden als Block zusammengehalten*
                    """)
                    
                    st.rerun()
    
    with col_btn2:
        if st.session_state.schedule is not None:
            if st.button("🔄 Neu berechnen", use_container_width=True):
                st.session_state.schedule = None
                st.rerun()
    
    # Zeige Zeitplan im Bearbeitungsmodus
    if st.session_state.schedule is not None:
        st.divider()
        st.subheader("📋 Zeitplan bearbeiten")
        
        df = st.session_state.schedule
        
        # Pro-Jury-Ansicht
        jury_namen = sorted(df['Jury/Raum'].unique())
        
        for jury_name in jury_namen:
            with st.expander(f"**{jury_name}**", expanded=True):
                jury_df = df[df['Jury/Raum'] == jury_name].copy()
                jury_df = jury_df.sort_values('Start').reset_index(drop=True)
                
                # Füge Status-Spalte hinzu
                status_liste = []
                for idx, row in jury_df.iterrows():
                    if row['Name'] == PAUSE_MARKER:
                        status_liste.append('⏸️')
                    else:
                        # Finde Original-Index im Gesamt-DataFrame
                        orig_idx = df[(df['Jury/Raum'] == jury_name) & 
                                     (df['Start'] == row['Start']) & 
                                     (df['Name'] == row['Name'])].index[0]
                        
                        konflikte = check_korrepetitor_konflikte(df, orig_idx)
                        if konflikte:
                            status_liste.append('⚠️')
                        else:
                            status_liste.append('✅')
                
                jury_df.insert(0, 'Status', status_liste)
                
                # Data Editor - Start ist editierbar für Pausen
                # Erstelle Spalten-Config
                column_config = {
                    'Status': st.column_config.TextColumn('Status', width='small'),
                    'Start': st.column_config.TextColumn('Start', help='Nur für Pausen editierbar'),
                    'Dauer (min)': st.column_config.NumberColumn(
                        'Dauer',
                        min_value=1,
                        max_value=120,
                        step=1,
                        help="Änderungen verschieben alle nachfolgenden"
                    )
                }
                
                # Disabled Spalten - Musikverein statt Verein
                disabled_cols = ['Status', 'Jury/Raum', 'Ende', 'Name', 'Musikverein', 'Instrument', 'Stufe', 'Korrepetitor']
                
                edited_jury = st.data_editor(
                    jury_df,
                    use_container_width=True,
                    hide_index=True,
                    disabled=disabled_cols,  # Start ist NICHT in der Liste
                    column_config=column_config,
                    key=f"editor_{jury_name}"
                )
                
                # Entferne Status-Spalte aus edited
                edited_jury = edited_jury.drop(columns=['Status'])
                
                # Prüfe auf Änderungen (Start ODER Dauer)
                jury_df_without_status = jury_df.drop(columns=['Status'])
                
                # Validiere Startzeit-Format für Pausen
                for idx, row in edited_jury.iterrows():
                    if row['Name'] == PAUSE_MARKER:
                        start_str = row['Start']
                        if not parse_time(start_str):
                            st.error(f"❌ Ungültige Startzeit '{start_str}' - Format: HH:MM")
                            edited_jury.at[idx, 'Start'] = jury_df_without_status.iloc[idx]['Start']
                
                if not edited_jury.equals(jury_df_without_status):
                    # Prüfe ob Start-Zeit geändert wurde (nur bei Pausen)
                    start_geaendert = False
                    for idx in range(len(edited_jury)):
                        if edited_jury.iloc[idx]['Name'] == PAUSE_MARKER:
                            if edited_jury.iloc[idx]['Start'] != jury_df_without_status.iloc[idx]['Start']:
                                start_geaendert = True
                                break
                    
                    # Update DataFrame
                    andere_jurys = df[df['Jury/Raum'] != jury_name]
                    updated_df = pd.concat([andere_jurys, edited_jury], ignore_index=True)
                    
                    # Zeiten neu berechnen mit Pausen-Priorität
                    updated_df = update_times(updated_df, jury_name)
                    st.session_state.schedule = updated_df
                    
                    # Info-Message wenn Pause verschoben wurde
                    if start_geaendert:
                        st.info("⏸️ Pause verschoben - Prüflinge wurden automatisch angepasst")
                    
                    st.rerun()
                
                # Pause-Button und Lösch-Option
                # Zähle Pausen in dieser Jury
                pausen_in_jury = jury_df[jury_df['Name'] == PAUSE_MARKER]
                anzahl_pausen = len(pausen_in_jury)
                
                col1, col2, col3 = st.columns([1, 2, 2])
                
                with col1:
                    if st.button("⏸️ Pause", key=f"pause_{jury_name}", use_container_width=True):
                        st.session_state.schedule = fuege_pause_ein(df, jury_name)
                        st.rerun()
                
                with col2:
                    if anzahl_pausen > 0:
                        # Erstelle Liste der Pausen mit Index und Startzeit
                        pausen_optionen = []
                        pausen_indices = []
                        
                        for idx, row in jury_df.iterrows():
                            if row['Name'] == PAUSE_MARKER:
                                # Finde Original-Index im Gesamt-DataFrame
                                orig_idx = df[(df['Jury/Raum'] == jury_name) & 
                                             (df['Start'] == row['Start']) & 
                                             (df['Name'] == PAUSE_MARKER)].index
                                
                                if len(orig_idx) > 0:
                                    pausen_optionen.append(f"Pause {row['Start']} ({row['Dauer (min)']} Min)")
                                    pausen_indices.append(orig_idx[0])
                        
                        if pausen_optionen:
                            selected_pause = st.selectbox(
                                "Pause auswählen",
                                options=range(len(pausen_optionen)),
                                format_func=lambda x: pausen_optionen[x],
                                key=f"select_pause_{jury_name}"
                            )
                            
                            if st.button("🗑️ Löschen", key=f"delete_pause_{jury_name}", type="secondary"):
                                # Lösche die ausgewählte Pause
                                idx_to_delete = pausen_indices[selected_pause]
                                pause_info = pausen_optionen[selected_pause]
                                
                                updated_df = df.drop(idx_to_delete).reset_index(drop=True)
                                
                                # Berechne Zeiten neu (Prüflinge rücken nach)
                                updated_df = update_times(updated_df, jury_name)
                                st.session_state.schedule = updated_df
                                
                                st.success(f"✅ {pause_info} gelöscht - Zeitplan aktualisiert")
                                st.rerun()
                    else:
                        st.caption("Keine Pausen vorhanden")
                
                with col3:
                    st.caption(f"📊 {len(jury_df)} Einträge | Ende: {jury_df.iloc[-1]['Ende'] if len(jury_df) > 0 else 'N/A'}")
        
        st.divider()
        
        # Export
        st.subheader("💾 Finalen Zeitplan exportieren")
        
        st.markdown("""
        **Excel-Export enthält:**
        - Pro Jury ein separates Tabellenblatt
        - Jury-Name und zugewiesene Instrumente als Überschrift
        - Professionelle Formatierung (farbige Kopfzeile, hervorgehobene Pausen)
        - Alle manuellen Änderungen und eingefügten Pausen
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Sammle instrument_assignments (mit Mehrfachzuordnung!)
            export_instrument_assignments = {}
            for i in range(jury_count):
                jury_key = f"Jury_{i+1}"
                key = f"jury_{i}_instruments"
                if key in st.session_state:
                    for inst in st.session_state[key]:
                        # Mehrfachzuordnung: Liste statt String
                        if inst not in export_instrument_assignments:
                            export_instrument_assignments[inst] = []
                        export_instrument_assignments[inst].append(jury_key)
            
            excel_data = exportiere_zu_excel(df, st.session_state.jury_names, export_instrument_assignments)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            st.download_button(
                label="📥 Finalen Zeitplan als Excel exportieren",
                data=excel_data,
                file_name=f"MLAZ_Zeitplan_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
        
        with col2:
            csv_data = exportiere_zu_csv(df)
            st.download_button(
                label="📥 Als CSV exportieren (Backup)",
                data=csv_data,
                file_name=f"MLAZ_Zeitplan_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True
            )


if __name__ == "__main__":
    main()
