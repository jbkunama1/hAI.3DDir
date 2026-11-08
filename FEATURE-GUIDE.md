# Filament Filter & View Features

## Features

### View Modes
- **List View (Reihe)**: Standard Tabelle, viele Spalten, ideal für Vergleich
- **3 Columns**: Gemischte Ansicht, gute Balance zwischen Überblick und Details
- **Grid View (Kacheln)**: Große Karten mit Vorschaubildern, visuelles Erlebnis

### Filtering
- **Material Filter**: Filtert alle Rollen nach Material (PLA, PETG, TPU etc.)
- **Brand Filter**: Filtert nach Marke (e.g. Polymaker, Prusa)
- **Barcode Search**: Suche direkt über EAN/UPC/QR Code
- **Combined Filters**: Alle Filter können kombiniert werden

### Grouping
- **Group by Material**: Rollen werden nach Material zusammengefasst
- **Group by Brand**: Rollen werden nach Marke zusammengefasst
- **Expand/Collapse**: Jede Gruppe lässt sich ein- und ausklappen
- **Persistent Settings**: Zuletzt gewählte Gruppe wird gespeichert

### Sorting
- **Weight Remaining**: Absteigend (voll bis leer)
- **Weight Total**: Absteigend (größte Rollen zuerst)
- **Material**: Alphabetisch (A-Z)
- **Brand**: Alphabetisch (A-Z)
- **Color Name**: Alphabetisch (A-Z)

## Configuration
In der Admin-Seite (Admin/Settings) wird neue Optionen für Filament-Ansicht:
- **Default View Mode**: Liste, 3-Spalten, Kacheln
- **Default Grouping**: Keine, nach Material, nach Marke
- **Default Sort**: Gewicht, Material, Marke
- **Grid Columns**: Für Kachel-Ansicht (1, 2, 3, 4, 6, 8 Spalten)

## UI Changes
- Obere Leiste erweitert um Filter-Inputs und View-Selector
- Gruppen-Überschriften mit Expand/Collapse-Icons
- Sortier-Indikatoren auf Spaltenköpfen
- Responsive Design für alle Ansichtsmodi
