#!/usr/bin/env python3
"""Início rápido do Wurm Market Tracker"""

import os
import sys
import subprocess
import json
import sqlite3

def setup_quick():
    """Setup rápido"""
    print("🚀 Wurm Market Tracker - Setup Rápido")
    
    # 1. Config mínimo
    config = {
        "forum_base_url": "https://forum.wurmonline.com",
        "delay_between_requests": 3,
        "database_path": "wurm_market.db",
        "categories": {"tools": ["axe"], "weapons": ["sword"]},
        "servers": ["Independence"],
        "price_patterns": [r"(\d+\.?\d*)\s*s"]
    }
    
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=2)
    print("✓ Config criado")
    
    # 2. DB básico
    conn = sqlite3.connect('wurm_market.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS market_items (
            id INTEGER PRIMARY KEY,
            name TEXT, category TEXT, price REAL,
            server TEXT, seller TEXT, timestamp TEXT,
            source TEXT, status TEXT DEFAULT 'active'
        )
    ''')
    conn.commit()
    conn.close()
    print("✓ Database criado")
    
    # 3. Requirements mínimo
    with open('requirements.txt', 'w') as f:
        f.write("""requests>=2.31.0
beautifulsoup4>=4.12.0
flask>=2.3.0
flask-cors>=4.0.0
lxml>=4.9.0""")
    print("✓ Requirements criado")
    
    print("\n📦 Instale as dependências:")
    print("pip install -r requirements.txt")
    print("\n🚀 Execute:")
    print("python main.py")

def test_scraper():
    """Teste rápido do scraper"""
    try:
        from main import WurmMarketScraper
        scraper = WurmMarketScraper()
        items = scraper.scrape_forum_trading_posts()
        print(f"✓ Teste OK - {len(items)} itens encontrados")
        scraper.close()
        return True
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_scraper()
    else:
        setup_quick()
