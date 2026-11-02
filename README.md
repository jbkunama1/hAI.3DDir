# 🧊 hAI.3DDir

FastAPI, Vanilla JavaScript und JSON-Persistenz für lokal eingebundene 3D-Druckdateien und Filamentrollen.

## Gestaltung wiederhergestellt

Modern, Nacht, Bunt, Werkstatt und Galaxie verwenden wieder die ursprünglichen Paletten, Hintergründe und themenabhängigen Symbole aus 3db9b68. Rollenfarben, Füllstandsbalken, vorhandene Rollenfotos, Statistik-Karten und Breadcrumbs sind wieder angebunden. Der Login-v2 bleibt unverändert; design.css/design.js erweitern nur die Oberfläche.

viewer.mjs lädt Three.js 0.160.0/Loader bei Bedarf von jsDelivr: STL/OBJ/3MF-Viewer mit Drehen, Zoom und Modellabmessungen; 3D-Thumbnails mit IndexedDB-Cache. WebGL und Internetzugang sind dafür erforderlich. Optionale Vorschaufehler dürfen den Login nicht blockieren. Dateiansichten: Symbole, 3D-Thumbnails und Slicer-Daten. Thumbnail-Limit im Adminbereich einstellbar. Dies ist kein vollständiger Rollback: Mehrfachauswahl, Batchaktionen und weitere alte Bedienfunktionen sind noch nicht wiederhergestellt.

## Betrieb

Vorhandenes docker-compose.yml, highfishNetwork, /share und persistentes /data verwenden. Samba auf dem Host mounten; SHARE_HOST_PATH, ADMIN_PASSWORD, stabilen SECRET_KEY und PUID/PGID setzen. Ein gespeicherter pw_hash ersetzt ADMIN_PASSWORD; Redeploy setzt kein Passwort zurück. Volumes nicht löschen.

Nach grünem GitHub-Test/Build Image neu ziehen und Container mit unveränderten Volumes neu erstellen. UI login-v2 und /build.json zeigen die Image-Revision; data-design=restored-v1 kennzeichnet die Gestaltung. Details: docs/LOGIN.md. Git-Push ist kein Redeploy.

## Grenzen und Tests

Nur vertrauenswürdiges LAN/VPN, kein umfassender Security-/CSRF-Audit. Proxy-Header nur vertrauenswürdigen Proxys erlauben. Restore und konkurrierende JSON-Schreibzugriffe benötigen weitere Härtung. Backups vertraulich und Volume/Share separat sichern. Telegram und optionale Vision-API können Inhalte extern übertragen; Niedrigstand-Pushwarnungen bleiben deaktiviert. MCP nutzt separate Bearer-Tokens und Read-only-Rechte; tools/list ist maßgeblich.

Python 3.12, Node.js, Abhängigkeiten aus Dockerfile plus Playwright installieren; python -m playwright install chromium und python -m unittest discover -s tests -v. Tests: Login, fünf Themes, Persistenz, Rollengrafiken und Isolation optionaler Vorschaufehler. Kein vollständiger WebGL-Renderingtest aller Dateiformate oder Nachweis für die konkrete LAN-Installation.

MIT: LICENSE. [Buy Me a Coffee](https://www.buymeacoffee.com/highfish)
