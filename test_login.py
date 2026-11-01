#!/usr/bin/env python3
"""
Test-Skript für den Login und MCP-Server
"""
import sys
import os
sys.path.append('app')

# Simuliere Umgebungsvariablen
os.environ['ADMIN_PASSWORD'] = 'changeme'
os.environ['SECRET_KEY'] = 'test-secret-key'

from app.main import app
import uvicorn
import requests

if __name__ == "__main__":
    print("Teste hAI.3DDir Login...")
    
    # Teste den Login-Endpunkt
    try:
        response = requests.post("http://localhost:8080/api/login", 
                                json={"password": "changeme"},
                                cookies={"session": "test-session"})
        print(f"Login-Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Login erfolgreich")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Login fehlgeschlagen: {response.text}")
    except Exception as e:
        print(f"❌ Verbindung fehlgeschlagen: {e}")
    
    # Teste MCP-Tools-Endpunkt (ohne Auth)
    try:
        response = requests.get("http://localhost:8080/api/mcp/tools")
        print(f"\nMCP Tools Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ MCP Tools erreichbar")
            print(f"Tools: {len(response.json().get('tools', []))}")
        else:
            print(f"❌ MCP Tools nicht erreichbar: {response.text}")
    except Exception as e:
        print(f"❌ Verbindung fehlgeschlagen: {e}")
    
    print("\nTest abgeschlossen. Server kann mit uvicorn app.main:app --host 0.0.0.0 --port 8080 gestartet werden.")