# Login-v2 und Image-Prüfung

Der Login liegt unabhängig von optionalen UI-Funktionen in app/static/app.js. Die Seite zeigt Initialisierung, Bereitschaft, laufende Prüfung und Fehler direkt im Formular. Eingabe per Enter und Button nutzen denselben Handler. Requests brechen nach zwölf Sekunden mit sichtbarer Meldung ab; nach erfolgreichem Passwort wird die Session mit /api/me geprüft. Passwörter werden weder geloggt noch in URLs geschrieben.

Unter dem Login steht UI login-v2 plus die Image-Revision. /build.json liefert {revision, ui}. Fehlt diese Kennung, wird nicht diese neue Oberfläche ausgeliefert. Der Zugriff auf die private LAN-Installation wurde nicht verifiziert.

Der Docker-Workflow führt Backend-Regressionen und echte Chromium-Tests mit Playwright aus: Klick, Enter, falsches Passwort, Serverfehler, fehlender Sessionnachweis, Reload und Logout. Erst danach wird das Image für amd64/arm64 veröffentlicht. Ein erfolgreicher Reparaturworkflow kann den Build ebenfalls auslösen. Image-Tags und /build.json beziehen sich auf den tatsächlich ausgecheckten Quellcommit.

Lokal für Tests zusätzlich uvicorn und playwright installieren, dann python -m playwright install chromium und python -m unittest discover -s tests -v ausführen. Tests verwenden temporäre Daten und eigene Testpasswörter; Telegram/LLM bleiben aus.

GitHub-Push und Image-Publish aktualisieren keinen bestehenden Container. Nach erfolgreichem Build Image in Portainer neu ziehen, Container mit unveränderten Volumes neu erstellen und im Browser die Build-Kennung kontrollieren. Kein Passwortreset und kein Löschen von Datenvolumes erforderlich. Ein gespeicherter pw_hash hat weiterhin Vorrang vor ADMIN_PASSWORD.
