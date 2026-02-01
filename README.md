# 🎵 ÖBV-LAZ Planungstool

Professionelles Zeitplanungs-Tool für Musikprüfungen des **Blasmusikbezirkes Bruck an der Mur** (Blasmusikverband Steiermark).

**Version:** 6.0 Final  
**Entwickelt für:** Blasmusikbezirksverband Bruck a. d. Mur

---

## 🎯 Hauptfunktionen

### ✅ Automatische Zeitplanung
- **Schlagzeug-Priorität:** ALLE Schlagzeuger beginnen am Morgen (unabhängig vom Verein)
- **Intelligente Vereins-Hierarchie:** 4 Kategorien nach Entfernung (Nahbereich → Extern)
- **Vereins-Kompaktheit:** Mitglieder eines Vereins bleiben als Block zusammen
- **Korrepetitor-Management:** Automatische 5-Minuten-Puffer zwischen Auftritten
- **Flexible Jury-Anzahl:** 1-10 Jurys mit individueller Benennung
- **Dynamische Instrumenten-Zuordnung:** Aus CSV extrahiert, keine fest hinterlegte Liste

### ✅ Interaktiver Bearbeitungsmodus
- **Live-Bearbeitung:** Direkt im Data Editor
- **Start-Zeit editierbar:** Nur für Pausen (manuelle Ankerzeit)
- **Dauer editierbar:** Für Prüflinge UND Pausen
- **Automatische Neuberechnung:** Alle nachfolgenden Zeiten werden sofort angepasst
- **Status-Spalte:** Live-Konflikt-Erkennung mit ⚠️ Symbol

### ✅ Pausen-Management
- **Pausen als DataFrame-Zeilen:** Einfaches Konzept
- **Feste Ankerzeit:** Pausen verdrängen Prüflinge automatisch
- **Einfügen:** Button "⏸️ Pause hinzufügen"
- **Löschen:** Selectbox + "🗑️ Löschen" Button
- **Standard-Dauer:** 15 Minuten (anpassbar)

### ✅ Professioneller Excel-Export
- **Separates Tabellenblatt pro Jury**
- **Formatierung:** Farbige Kopfzeile, hervorgehobene Pausen
- **Spalten:** Beginnuhrzeit, Name, Musikverein, Instrument, Stufe, Bemerkung

---

## 🚀 Schnellstart

```bash
# Dependencies installieren
pip install -r requirements.txt

# Programm starten
streamlit run pruefungsplaner_v6_final.py
```

---

## 📖 Bedienung

### 1. CSV hochladen
MLAZ-CSV-Export Format (Semikolon-getrennt, UTF-8)

### 2. Jurys konfigurieren
- Anzahl festlegen (1-10)
- Namen anpassen

### 3. Instrumente zuweisen
Werden dynamisch aus CSV extrahiert und alphabetisch sortiert

### 4. Zeitplan berechnen
Sortierung:
1. 🥁 Schlagzeuger zuerst
2. 🏘️ Nahbereich-Vereine
3. 🚗 Erweiterter Nahbereich
4. 🗺️ Weiter Weg
5. 🌍 Externe Vereine

### 5. Bearbeiten
- **Dauer ändern:** Klicken → Wert ändern → Enter
- **Pause einfügen:** Button unter Jury-Tabelle
- **Pause löschen:** Selectbox auswählen → Löschen

### 6. Exportieren
Button: "📥 Finalen Zeitplan als Excel exportieren"

---

## 🎨 Vereins-Hierarchie

### Nahbereich (Früh)
Bruck, Kapfenberg, Oberaich, Pernegg, St. Dionysen

### Erweiterter Nahbereich (Mittel)
Breitenau, Parschlug, St. Lorenzen, Röthelstein, St. Marein

### Weiter Weg (Spät)
Mariazell, Aflenz, Tragöß, Turnau, Etmißl, Graßnitz, etc.

### Extern (Ganz zum Schluss)
Alle nicht gelisteten Vereine

---

## 🔧 Technische Details

### Dauer-Berechnung
- Junior: 12 Min
- Bronze: 15 Min
- Silber: 18 Min
- Schlagzeug: +5 Min

### Dependencies
```
streamlit >= 1.31.0
pandas >= 2.0.0
numpy >= 1.24.0
openpyxl >= 3.1.0
xlsxwriter >= 3.1.0
```

### CSV-Format (MLAZ)
Das Programm erkennt die MLAZ-Struktur automatisch!
- Encoding: UTF-8 mit BOM
- Trennzeichen: Semikolon

---

## 💡 Tipps

### Pausen strategisch platzieren
- Mittagspause: 12:00 Uhr als Ankerzeit
- Kaffeepause: 10:00 Uhr synchron für alle Jurys

### Korrepetitor-Konflikte
- Status-Spalte ⚠️ beobachten
- Pausen einfügen um Konflikte zu beheben

### Export optimieren
- Jury-Namen vor Export aussagekräftig benennen
- Instrumente korrekt zuweisen

---

## 🐛 Troubleshooting

### CSV lädt nicht
- Encoding prüfen (UTF-8 mit BOM)
- MLAZ-Export verwenden

### Instrumente fehlen
- Expander "📋 Gefundene Instrumente" öffnen
- CSV-Spalte `instrument_id` prüfen

### ⚠️ Konflikte
- Dauer anpassen
- Pause einfügen
- Start-Zeit ändern

---

## 📝 Changelog

### v6.0 Final (2026-02-01)
- MLAZ-CSV-Format Support
- Dynamische Instrumenten-Extraktion
- 4-stufige Vereins-Hierarchie
- Schlagzeug-Veto
- Pausen als Dummy-Zeilen
- Interaktiver Bearbeitungsmodus
- Professioneller Excel-Export
- Umbenennung auf "ÖBV-LAZ Planungstool"

---

## 🎵 Viel Erfolg bei Ihren Prüfungen! 🎺
