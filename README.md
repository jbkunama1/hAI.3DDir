# hAI.3DDir

FastAPI und Vanilla JavaScript für lokal eingebundene Druckdateien, Filamentrollen, Telegram und MCP. JSON-Persistenz; kein Vue.js oder SQLite.

## Deployment und Login

Das vorhandene Compose verwendet ghcr.io/jbkunama1/hai.3ddir:latest, highfishNetwork, /share und /data. Samba auf dem Host mounten; SHARE_HOST_PATH, ADMIN_PASSWORD, SECRET_KEY, PUID/PGID setzen. PORT ist standardmäßig 8080. SECRET_KEY stabil halten (z. B. openssl rand -hex 32).

Ein gespeicherter pw_hash in /data/settings.json hat Vorrang vor ADMIN_PASSWORD. Redeploy und ENV-Änderungen entfernen ihn nicht. Ohne Hash gilt die ENV (Fallback changeme unbedingt ersetzen). Ohne SECRET_KEY wird /data/.session_secret restriktiv angelegt. Passwortwechsel invalidieren Websessions. Fünf Fehlversuche begrenzen das IP-Zeitfenster für fünf Minuten, pro Prozess.

Passwort vergessen: Anwendung stoppen, Einstellungen sichern, nur pw_hash entfernen, ADMIN_PASSWORD sicher setzen und starten. Kein Volume löschen.

## Funktionsstand

Zwei Themes (Modern/Nacht). Unterstützte G-Code-/3MF-Dateien liefern Metadaten und eingebettete Vorschauen, keine browsergerenderten STL-Thumbnails oder vollständigen 3D-Viewer. API/MCP: Dateioperationen, Papierkorb, Filamente, Druckbuchungen, Kosten und Näherungen zum Verbrauch. Nicht jedes Slicerformat wird unterstützt. Einige UI-Funktionen bleiben unvollständig; ein erfolgreicher Login ist kein Nachweis vollständiger Feature-Abdeckung.

MCP: POST /mcp, Bearer-Token; MCP_TOKEN optional global. Persönliche Tokens einmalig kopieren, Hashes werden gespeichert, Klartext-Altbestände migriert. Read-only-Rechte bleiben erhalten. tools/list ist maßgeblich, inklusive Kosten-/Slicerwerkzeugen; keine JWTs.

Telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_IDS, optional TELEGRAM_ADMIN_IDS; /menu, /files, /search, /filament und Inline-Menüs. Niedrigstand-Pushwarnungen sind deaktiviert. KI-Etiketten benötigen LLM_BASE_URL, LLM_MODEL und optional LLM_API_KEY. Externe Integrationen können Inhalte an Anbieter übertragen.

## Sicherheit und Daten

Nur vertrauenswürdiges LAN/VPN; keine gehärtete öffentliche Mehrbenutzerplattform. REST benötigt Websession, MCP separat Bearer-Auth. Passwort-Debug und ungeschützte Tokenverwaltung werden entfernt. SameSite=Lax ist kein vollständiges CSRF-System. Das bestehende Docker-Kommando vertraut Proxy-Headern; Backend-Port abschotten. Weitere Härtung von Restore, Konfigurationsvalidierung und konkurrierenden JSON-Schreibvorgängen ist offen.

Backup: Einstellungen inklusive Passwort-Hash, Filamente, Druckhistorie, Rollenbilder; nicht Share, Tokens, Session-Schlüssel, Cache oder Telegram-Zustand. Vertraulich behandeln und Volume/Share extern sichern. Restore ist keine dateiübergreifende Transaktion.

## Reparatur, Tests und Update

maintenance/repair.py ist ein selbst verfasstes einmaliges Reparaturskript, kein Coding-Agent. GitHub Actions prüft den Ausgangscommit, wendet die Änderungen isoliert an und schreibt sie nur bei erfolgreichen Tests nach main. Bei Fehlern bleibt der zweite Commit aus. Python 3.12, Node.js, Abhängigkeiten aus Dockerfile; Tests: python -m unittest discover -s tests -v. Tests verwenden temporäre Daten und deaktivieren Telegram. Kein umfassender Browser-/Proxy- oder Security-Test.

Der Folgecommit via GITHUB_TOKEN startet normalerweise keinen weiteren Push-Workflow: Image-Build nach erfolgreicher Reparatur ausdrücklich anstoßen. Der bestehende Publish-Workflow ist nicht automatisch von diesem Testlauf abhängig. Nur grünen Stand einsetzen, in Portainer neues Image ziehen, Container mit unveränderten Volumes neu erstellen und Browser hart neu laden. Git-Push ist kein Redeploy.

Logs: docker logs hai3ddir. /health liefert {"status":"ok"}. MIT: siehe LICENSE.
