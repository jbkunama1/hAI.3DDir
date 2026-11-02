# Filament-Import: JSON und CSV

filaments.example.json und filaments.example.csv enthalten dieselben zwei fiktiven Rollen. Beispielmarke, Preise und DEMO-Barcodes sind keine echten Produktangaben. Beide Dateien sind zum direkten Testimport geeignet. Nur eine davon importieren, sonst entstehen doppelte Rollen.

## Dateien und Felder

UTF-8 verwenden, mit oder ohne BOM. JSON muss ein Array von Rollenobjekten sein, auch für eine einzelne Rolle: [{...}]. Kein Wrapper wie {"filaments":[...]}. CSV benötigt eine Kopfzeile; die Beispiele verwenden Semikolon. Der Importer erkennt Semikolon oder Komma anhand der Kopfzeile, aber keine Tabulatoren.

| Feld | Bedeutung / Beispiel |
|---|---|
| brand | Marke, z. B. Beispielmarke |
| material | Material, z. B. PLA oder PETG |
| color_name | Farbname, z. B. Schwarz |
| color_hex | Farbe als #RRGGBB, z. B. #000000 |
| weight_total | Gesamtgewicht in Gramm, z. B. 1000 |
| weight_remaining | Restgewicht in Gramm, z. B. 750 oder 420.5 |
| notes | Freie Notizen |
| barcode | Text; in JSON als String führen, z. B. DEMO-0001 |
| price_per_kg | Preis pro Kilogramm, z. B. 19.90 |
| purchase_date | Datum YYYY-MM-DD oder leer |

Die englischen Feldnamen verwenden; keine übersetzten Spaltenüberschriften. Alle genannten Felder werden vom aktuellen Importer berücksichtigt. Fehlende Textfelder werden leer, fehlende oder leere Zahlenwerte werden 0. Insbesondere weight_remaining ausdrücklich setzen: fehlt es, wird nicht weight_total übernommen. Sinnvolle nicht negative Zahlen und Restgewicht höchstens Gesamtgewicht eintragen; nicht auf die derzeit lockere Validierung verlassen.

JSON-Zahlen ohne Anführungszeichen mit Dezimalpunkt schreiben. CSV-Zahlen können Punkt oder Komma verwenden; Semikolon ist bei Dezimalkomma zweckmäßig. Keine Einheiten oder Währungszeichen an Zahlen hängen: 1000 statt 1000 g, 19.90 statt 19.90 EUR. Datum z. B. 2026-11-01. Barcodes als Text behandeln, damit führende Nullen nicht verloren gehen.

CSV-Felder mit Trennzeichen, Anführungszeichen oder Zeilenumbrüchen in doppelte Anführungszeichen setzen. Anführungszeichen im Feld verdoppeln. Die erste Beispielnotiz zeigt ein korrekt zitiertes Semikolon.

## Import in der Oberfläche

Anmelden, Filamente öffnen, Import CSV/JSON wählen und eine Datei auswählen. Standardmäßig werden neue Rollen angehängt. Bestehende Rollen beim Import ersetzen nur bewusst aktivieren und die Bestätigung lesen. Vorher ein Backup erstellen.

Jeder Import erzeugt neue Rollen-IDs. Es gibt keinen Abgleich oder Merge über IDs oder Barcodes; wiederholter Import erzeugt Duplikate. Mitgelieferte id-Werte werden nicht übernommen. Bilder, Bildpfade und Druckhistorie gehören nicht zu diesem Importformat. Ersetzen entfernt den bisherigen Rollenbestand, während alte Druckbuchungen nicht automatisch auf die neuen IDs umgeschrieben werden. Für eine vollständige Wiederherstellung die Backup/Restore-Funktion statt des Rollenimports verwenden.

Die Beispieldateien werden nicht automatisch importiert; der Repository-Commit verändert keine produktiven Daten.
