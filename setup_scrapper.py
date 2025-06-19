#!/usr/bin/env python3
"""
Setup script for Wurm Online Market Tracker
Configura o ambiente inicial e cria os arquivos necessários
"""

import os
import json
import sqlite3
from pathlib import Path

def create_config_file():
    """Cria arquivo de configuração inicial"""
    config = {
        "forum_base_url": "https://forum.wurmonline.com",
        "discord_token": "",
        "scrape_interval": 3600,
        "max_pages": 10,
        "delay_between_requests": 2,
        "database_path": "wurm_market.db",
        "categories": {
            "tools": ["axe", "pickaxe", "hammer", "saw", "knife", "chisel", "file", "rake", "shovel", "scissor"],
            "weapons": ["sword", "spear", "bow", "arrow", "club", "mace", "staff", "wand", "dagger"],
            "armor": ["helmet", "armor", "shield", "boot", "gauntlet", "sleeve", "jacket", "cap"],
            "materials": ["rope", "brick", "log", "plank", "metal lump", "ore", "clay", "tar", "cotton", "wemp"],
            "food": ["bread", "stew", "meal", "wine", "beer", "juice", "soup", "pie", "cake"],
            "misc": ["lamp", "chest", "bed", "table", "chair", "barrel", "jar", "pottery", "sail", "cart"]
        },
        "servers": ["Independence", "Pristine", "Celebration", "Xanadu", "Cadence", "Harmony", "Melody"],
        "price_patterns": [
            r"(\d+\.?\d*)\s*s(?:ilver)?",
            r"(\d+\.?\d*)\s*c(?:opper)?",
            r"(\d+\.?\d*)\s*iron"
        ]
    }
    
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print("✓ Arquivo config.json criado")

def create_database():
    """Cria banco de dados inicial"""
    conn = sqlite3.connect('wurm_market.db')
    
    # Tabela de itens do mercado
    conn.execute('''
        CREATE TABLE IF NOT EXISTS market_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            price REAL,
            cost REAL,
            quality INTEGER,
            enchantments TEXT,
            server TEXT,
            seller TEXT,
            location TEXT,
            quantity INTEGER DEFAULT 1,
            timestamp TEXT,
            source TEXT,
            url TEXT,
            description TEXT,
            contact TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de histórico de scraping
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scrape_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            url TEXT,
            items_found INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            error_message TEXT
        )
    ''')
    
    # Índices para performance
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_status ON market_items(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_category ON market_items(category)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_server ON market_items(server)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_items_updated ON market_items(updated_at)')
    
    conn.commit()
    conn.close()
    
    print("✓ Banco de dados wurm_market.db criado")

def create_requirements_file():
    """Cria arquivo requirements.txt"""
    requirements = """requests>=2.31.0
beautifulsoup4>=4.12.0
selenium>=4.11.0
flask>=2.3.0
flask-cors>=4.0.0
schedule>=1.2.0
discord.py>=2.3.0
lxml>=4.9.0
pandas>=2.0.0
"""
    
    with open('requirements.txt', 'w') as f:
        f.write(requirements)
    
    print("✓ Arquivo requirements.txt criado")

def create_startup_script():
    """Cria script de inicialização"""
    startup_script = '''#!/bin/bash
# Startup script for Wurm Online Market Tracker

echo "Starting Wurm Online Market Tracker..."

# Verifica se Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed"
    exit 1
fi

# Instala dependências se necessário
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Executa setup inicial se necessário
if [ ! -f "wurm_market.db" ]; then
    echo "Running initial setup..."
    python3 setup_scraper.py
fi

# Inicia o servidor
echo "Starting web server at http://localhost:5000"
python3 web_integration.py
'''
    
    with open('start.sh', 'w') as f:
        f.write(startup_script)
    
    os.chmod('start.sh', 0o755)
    print("✓ Script start.sh criado")

def main():
    """Função principal de setup"""
    print("=== Wurm Online Market Tracker Setup ===")
    
    # Cria arquivos necessários
    create_config_file()
    create_database()
    create_requirements_file()
    create_startup_script()
    
    print("\n✓ Setup completo!")
    print("\nPróximos passos:")
    print("1. Instale as dependências: pip install -r requirements.txt")
    print("2. (Opcional) Configure Discord token no config.json")
    print("3. Execute: python3 web_integration.py")
    print("4. Acesse: http://localhost:5000")
    print("\nOu execute: ./start.sh para inicialização automática")

if __name__ == "__main__":
    main()
