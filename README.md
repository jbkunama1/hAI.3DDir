# 🧊 hAI.3DDir

FastAPI, Vanilla JavaScript und JSON-Persistenz für lokal eingebundene 3D-Druckdateien und Filamentrollen.

## Oberfläche und Bedienung

Fünf Original-Themes mit Hintergründen, Symbolen, Rollengrafiken, Füllstandsbalken, Fotos, Statistik-Karten und Breadcrumbs. Login-v2 bleibt unverändert; design.js und controls.js erweitern die Oberfläche.

Wieder verfügbar: Mehrfachauswahl per Checkbox, Strg/Cmd und Shift-Bereich, alle/keine, Verschieben mit Zielordnerwahl, ZIP und Löschen; neue Ordner; Drag-and-drop-Verschieben und Upload mit Fortschritt; Papierkorb mit Wiederherstellen, endgültigem Löschen und Leeren; Rollen bearbeiten/löschen und CSV/JSON-Import/-Export. Import hängt standardmäßig an; Ersetzen verlangt Bestätigung. Escape beendet die Auswahl.

STL/OBJ/3MF-Viewer und 3D-Thumbnails verwenden WebGL und bei Bedarf Three.js 0.160.0 von jsDelivr. Symbole, Thumbnails und Slicer-Daten bleiben getrennte Ansichten. Optionale Vorschaufehler dürfen den Login nicht blockieren.

## Dateiaktionen und Grenzen

Ausgewählte Unterpfade werden ausgelassen, wenn ihr übergeordneter Ordner ebenfalls ausgewählt ist. ZIPs mit gleichnamigen Wurzelelementen aus verschiedenen Ordnern werden abgelehnt. Teilfehler beim Löschen werden sichtbar angezeigt. Die vorhandene Move-API arbeitet sequenziell, nicht transaktional: bei Fehlern Quelle und Ziel auf Teiländerungen prüfen. Restore und konkurrierende JSON-Schreibzugriffe benötigen weitere Härtung.

Nur vertrauenswürdiges LAN/VPN; kein vollständiger Security-/CSRF-Audit. Backend-Port abschotten. Backups vertraulich und Volume/Share zusätzlich extern sichern. MCP nutzt Bearer-Tokens und Read-only-Rechte. Telegram/optionale Vision-API können Inhalte extern übertragen; Niedrigstand-Pushwarnungen bleiben deaktiviert.

## Betrieb und Tests

Vorhandenes Compose, highfishNetwork, /share und persistentes /data verwenden. Samba auf dem Host mounten; SHARE_HOST_PATH, ADMIN_PASSWORD, stabilen SECRET_KEY und PUID/PGID setzen. Ein gespeicherter pw_hash ersetzt ADMIN_PASSWORD. Keine Volumes für Passwortprobleme löschen.

Nach grünen GitHub-Tests und erfolgreichem Build Image neu ziehen, Container mit unveränderten Volumes neu erstellen und Browser hart neu laden. /build.json zeigt die Revision; data-design und data-controls sind restored-v1. Git-Push ist kein Redeploy.

Python 3.12, Node.js, Dockerfile-Abhängigkeiten und Playwright installieren; python -m playwright install chromium und python -m unittest discover -s tests -v. Tests verwenden temporäre Daten für Login, Themes, Auswahl, ZIP-Inhalt, Verschieben, Papierkorb, Teilfehler, Ordner, Upload und Import. Kein vollständiger WebGL-Test oder Nachweis für die konkrete LAN-Installation.

MIT: LICENSE. [Buy Me a Coffee](https://www.buymeacoffee.com/highfish)
