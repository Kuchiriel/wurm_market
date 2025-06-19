#!/usr/bin/env python3
"""
Wurm Online Market Data Scraper
Coleta dados de mercado de múltiplas fontes para o Wurm Online Market Tracker
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Union
import logging
from urllib.parse import urljoin, urlparse
import discord
from discord.ext import tasks
import asyncio
import csv
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wurm_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class MarketItem:
    """Classe para representar um item do mercado"""
    name: str
    category: str
    price: float
    cost: Optional[float] = None
    quality: Optional[int] = None
    enchantments: Optional[str] = None
    server: str = "unknown"
    seller: str = "unknown"
    location: str = "unknown"
    quantity: int = 1
    timestamp: str = ""
    source: str = "forum"
    url: str = ""
    description: str = ""
    contact: str = ""
    status: str = "active"  # active, sold, expired

def load_config_safe(self, config_file: str) -> Dict:
    """Carrega config com tratamento de erro melhorado"""
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar config: {e}")
    
    # Config mínimo de emergência
    return {
        "forum_base_url": "https://forum.wurmonline.com",
        "scrape_interval": 3600,
        "max_pages": 5,
        "delay_between_requests": 3,
        "database_path": "wurm_market.db",
        "categories": {"tools": ["axe"], "weapons": ["sword"]},
        "servers": ["Independence"],
        "price_patterns": [r"(\d+\.?\d*)\s*s"]
    }

class WurmMarketScraper:
    """Scraper principal para dados de mercado do Wurm Online"""
    
    def __init__(self, config_file="config.json"):
        self.config = self.load_config(config_file)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.db_connection = self.init_database()
        self.selenium_driver = None
        
    def load_config(self, config_file: str) -> Dict:
        """Carrega configurações do arquivo JSON"""
        default_config = {
            "forum_base_url": "https://forum.wurmonline.com",
            "discord_token": "",  # Token do bot Discord (opcional)
            "scrape_interval": 3600,  # 1 hora
            "max_pages": 10,
            "delay_between_requests": 2,
            "database_path": "wurm_market.db",
            "categories": {
                "tools": ["axe", "pickaxe", "hammer", "saw", "knife"],
                "weapons": ["sword", "spear", "bow", "arrow", "club"],
                "armor": ["helmet", "armor", "shield", "boot", "gauntlet"],
                "materials": ["rope", "brick", "log", "plank", "metal lump"],
                "food": ["bread", "stew", "meal", "wine", "beer"],
                "misc": ["lamp", "chest", "bed", "table", "chair"]
            },
            "servers": ["Independence", "Pristine", "Celebration", "Xanadu", "Cadence"],
            "price_patterns": [
                r"(\d+\.?\d*)\s*s(?:ilver)?",  # Prata
                r"(\d+\.?\d*)\s*c(?:opper)?",  # Cobre
                r"(\d+\.?\d*)\s*iron",        # Ferro
            ]
        }
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            # Salva config padrão
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
        
        return default_config
        
    def init_database(self) -> sqlite3.Connection:
        """Inicializa o banco de dados SQLite"""
        conn = sqlite3.connect(self.config["database_path"])
        
        # Criar tabelas
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
        
        conn.commit()
        return conn
        
    def init_selenium(self):
        """Selenium simplificado"""
        if self.selenium_driver is None:
            try:
                options = Options()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                self.selenium_driver = webdriver.Chrome(options=options)
                return self.selenium_driver
            except Exception as e:
                logger.warning(f"Selenium não disponível: {e}")
                return None
        return self.selenium_driver
        
    def close_selenium(self):
        """Fecha o driver do Selenium"""
        if self.selenium_driver:
            self.selenium_driver.quit()
            self.selenium_driver = None
            
    def extract_price(self, text: str) -> Optional[float]:
        """Extrai preço do texto usando regex"""
        text = text.lower()
        
        # Busca por padrões de preço
        for pattern in self.config["price_patterns"]:
            match = re.search(pattern, text)
            if match:
                price = float(match.group(1))
                
                # Converte para prata se necessário
                if "c" in pattern or "copper" in pattern:
                    price = price / 100  # 100 cobre = 1 prata
                elif "iron" in pattern:
                    price = price * 20   # 1 ferro = 20 prata (aproximado)
                    
                return price
        
        return None
        
    def categorize_item(self, item_name: str) -> str:
        """Categoriza o item baseado no nome"""
        item_lower = item_name.lower()
        
        for category, keywords in self.config["categories"].items():
            for keyword in keywords:
                if keyword in item_lower:
                    return category
        
        return "misc"
        
    def scrape_forum_trading_posts(self) -> List[MarketItem]:
        """Versão simplificada - só posts recentes"""
        items = []
        
        try:
            url = f"{self.config['forum_base_url']}/index.php?/forum/9-selling/"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            posts = soup.find_all('div', class_='ipsDataItem')[:10]  # Só 10 posts
            
            for post in posts:
                try:
                    title_elem = post.find('a')
                    if title_elem and self.is_trading_post(title_elem.text):
                        # Extração básica só do título
                        extracted = self.extract_items_from_text(title_elem.text)
                        for item_data in extracted:
                            item = MarketItem(
                                name=item_data['name'],
                                category=self.categorize_item(item_data['name']),
                                price=item_data.get('price', 0.0),
                                server=item_data.get('server', 'unknown'),
                                seller='forum_user',
                                timestamp=datetime.now().isoformat(),
                                source="forum",
                                url=url,
                                status="active"
                            )
                            items.append(item)
                            
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Erro no post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Erro no forum: {e}")
            
        return items
        
    def parse_forum_post(self, post_element, base_url: str) -> List[MarketItem]:
        """Analisa um post do fórum para extrair itens"""
        items = []
        
        try:
            # Extrai informações básicas do post
            title_elem = post_element.find('a', {'data-linktype': 'topic'})
            if not title_elem:
                return items
                
            title = title_elem.get_text(strip=True)
            post_url = urljoin(base_url, title_elem.get('href', ''))
            
            # Pula se não parecer ser um post de trading
            if not self.is_trading_post(title):
                return items
                
            # Extrai detalhes do post
            author_elem = post_element.find('a', {'data-linktype': 'profile'})
            author = author_elem.get_text(strip=True) if author_elem else "unknown"
            
            timestamp_elem = post_element.find('time')
            timestamp = timestamp_elem.get('datetime') if timestamp_elem else datetime.now().isoformat()
            
            # Busca o conteúdo completo do post
            post_content = self.get_post_content(post_url)
            if not post_content:
                return items
                
            # Extrai itens do conteúdo
            extracted_items = self.extract_items_from_text(post_content, title)
            
            # Cria objetos MarketItem
            for item_data in extracted_items:
                item = MarketItem(
                    name=item_data['name'],
                    category=self.categorize_item(item_data['name']),
                    price=item_data.get('price', 0.0),
                    quality=item_data.get('quality'),
                    enchantments=item_data.get('enchantments'),
                    server=item_data.get('server', 'unknown'),
                    seller=author,
                    location=item_data.get('location', 'unknown'),
                    quantity=item_data.get('quantity', 1),
                    timestamp=timestamp,
                    source="forum",
                    url=post_url,
                    description=title,
                    contact=f"Forum: {author}",
                    status="active"
                )
                items.append(item)
                
        except Exception as e:
            logger.error(f"Error parsing forum post: {e}")
            
        return items
        
    def is_trading_post(self, title: str) -> bool:
        """Verifica se o título indica um post de trading"""
        trading_keywords = [
            'wts', 'wtb', 'wtt', 'selling', 'buying', 'trade', 'shop',
            'sale', 'price', 'silver', 'copper', 'iron', 'market'
        ]
        
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in trading_keywords)
        
    def get_post_content(self, post_url: str) -> Optional[str]:
        """Obtém o conteúdo completo de um post"""
        try:
            response = self.session.get(post_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Encontra o conteúdo do post
            content_elem = soup.find('div', class_=['ipsType_richText', 'ipsContained'])
            if content_elem:
                return content_elem.get_text(separator=' ', strip=True)
                
        except Exception as e:
            logger.error(f"Error getting post content from {post_url}: {e}")
            
        return None
        
    def extract_items_from_text(self, text: str, title: str = "") -> List[Dict]:
        """Extrai itens e preços do texto"""
        items = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Busca por padrões de itens com preços
            item_matches = re.findall(
                r'([A-Za-z\s]+(?:axe|sword|hammer|rope|brick|armor|helmet|shield|bow|arrow|knife|saw|pickaxe|spear|club|meal|bread|wine|beer|lamp|chest|bed|table|chair))\s*[:-]?\s*(\d+\.?\d*)\s*([sc]|silver|copper|iron)?',
                line, re.IGNORECASE
            )
            
            for match in item_matches:
                item_name = match[0].strip()
                price_value = float(match[1])
                currency = match[2].lower() if match[2] else 's'
                
                # Converte preço para prata
                if currency in ['c', 'copper']:
                    price_value = price_value / 100
                elif currency == 'iron':
                    price_value = price_value * 20
                    
                # Extrai qualidade se presente
                quality_match = re.search(r'ql?\s*(\d+)', line, re.IGNORECASE)
                quality = int(quality_match.group(1)) if quality_match else None
                
                # Extrai servidor se presente
                server = 'unknown'
                for srv in self.config["servers"]:
                    if srv.lower() in line.lower():
                        server = srv
                        break
                        
                items.append({
                    'name': item_name,
                    'price': price_value,
                    'quality': quality,
                    'server': server,
                    'quantity': 1
                })
                
        return items
        
    def scrape_discord_markets(self) -> List[MarketItem]:
        """Scraper para canais de mercado do Discord (requer bot token)"""
        items = []
        
        if not self.config.get("discord_token"):
            logger.warning("Discord token not configured, skipping Discord scraping")
            return items
            
        # Implementação do scraping do Discord seria aqui
        # Requer configuração de um bot Discord
        logger.info("Discord scraping not implemented yet")
        
        return items
        
    def scrape_steam_community(self) -> List[MarketItem]:
        """Scraper para discussões do Steam Community"""
        items = []
        
        try:
            # URLs do Steam Community
            steam_urls = [
                "https://steamcommunity.com/app/1179680/discussions/",  # Wurm Online
                "https://steamcommunity.com/app/366220/discussions/"   # Wurm Unlimited
            ]
            
            for url in steam_urls:
                logger.info(f"Scraping Steam Community: {url}")
                
                response = self.session.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Encontra tópicos de discussão
                topics = soup.find_all('div', class_='forum_topic')
                
                for topic in topics:
                    try:
                        title_elem = topic.find('a', class_='forum_topic_title')
                        if title_elem and self.is_trading_post(title_elem.get_text()):
                            # Processa tópico de trading
                            topic_items = self.process_steam_topic(title_elem.get('href'))
                            items.extend(topic_items)
                            
                        time.sleep(self.config["delay_between_requests"])
                        
                    except Exception as e:
                        logger.error(f"Error processing Steam topic: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error scraping Steam Community: {e}")
            
        return items
        
    def process_steam_topic(self, topic_url: str) -> List[MarketItem]:
        """Processa um tópico do Steam para extrair itens"""
        items = []
        
        try:
            response = self.session.get(topic_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extrai posts do tópico
            posts = soup.find_all('div', class_='forum_post_content')
            
            for post in posts:
                text_content = post.get_text(separator=' ', strip=True)
                extracted_items = self.extract_items_from_text(text_content)
                
                for item_data in extracted_items:
                    item = MarketItem(
                        name=item_data['name'],
                        category=self.categorize_item(item_data['name']),
                        price=item_data.get('price', 0.0),
                        quality=item_data.get('quality'),
                        server=item_data.get('server', 'unknown'),
                        seller="steam_user",
                        timestamp=datetime.now().isoformat(),
                        source="steam",
                        url=topic_url,
                        status="active"
                    )
                    items.append(item)
                    
        except Exception as e:
            logger.error(f"Error processing Steam topic {topic_url}: {e}")
            
        return items
        
    def save_items_to_database(self, items: List[MarketItem]):
        """Salva itens no banco de dados"""
        cursor = self.db_connection.cursor()
        
        for item in items:
            try:
                # Verifica se item já existe
                cursor.execute('''
                    SELECT id FROM market_items 
                    WHERE name = ? AND seller = ? AND url = ? AND status = 'active'
                ''', (item.name, item.seller, item.url))
                
                if cursor.fetchone():
                    # Atualiza item existente
                    cursor.execute('''
                        UPDATE market_items SET
                            price = ?, quality = ?, quantity = ?, 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE name = ? AND seller = ? AND url = ? AND status = 'active'
                    ''', (item.price, item.quality, item.quantity, 
                          item.name, item.seller, item.url))
                else:
                    # Insere novo item
                    cursor.execute('''
                        INSERT INTO market_items (
                            name, category, price, cost, quality, enchantments,
                            server, seller, location, quantity, timestamp, source,
                            url, description, contact, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        item.name, item.category, item.price, item.cost,
                        item.quality, item.enchantments, item.server, item.seller,
                        item.location, item.quantity, item.timestamp, item.source,
                        item.url, item.description, item.contact, item.status
                    ))
                    
            except Exception as e:
                logger.error(f"Error saving item {item.name}: {e}")
                
        self.db_connection.commit()
        logger.info(f"Saved {len(items)} items to database")
        
    def export_to_json(self, filename: str = None) -> str:
        """Exporta dados para JSON"""
        if not filename:
            filename = f"wurm_market_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
        cursor = self.db_connection.cursor()
        cursor.execute('''
            SELECT * FROM market_items WHERE status = 'active'
            ORDER BY updated_at DESC
        ''')
        
        items = []
        columns = [description[0] for description in cursor.description]
        
        for row in cursor.fetchall():
            item_dict = dict(zip(columns, row))
            items.append(item_dict)
            
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Exported {len(items)} items to {filename}")
        return filename
        
    def run_full_scrape(self):
        """Executa scraping completo de todas as fontes"""
        logger.info("Starting full market data scrape")
        
        all_items = []
        
        # Scrape fórum oficial
        logger.info("Scraping official forum...")
        forum_items = self.scrape_forum_trading_posts()
        all_items.extend(forum_items)
        logger.info(f"Found {len(forum_items)} items from forum")
        
        # Scrape Steam Community
        logger.info("Scraping Steam Community...")
        steam_items = self.scrape_steam_community()
        all_items.extend(steam_items)
        logger.info(f"Found {len(steam_items)} items from Steam")
        
        # Scrape Discord (se configurado)
        if self.config.get("discord_token"):
            logger.info("Scraping Discord...")
            discord_items = self.scrape_discord_markets()
            all_items.extend(discord_items)
            logger.info(f"Found {len(discord_items)} items from Discord")
        
        # Salva no banco de dados
        if all_items:
            self.save_items_to_database(all_items)
        
        # Registra histórico de scraping
        cursor = self.db_connection.cursor()
        cursor.execute('''
            INSERT INTO scrape_history (source, url, items_found, status)
            VALUES (?, ?, ?, ?)
        ''', ("full_scrape", "multiple", len(all_items), "completed"))
        self.db_connection.commit()
        
        logger.info(f"Full scrape completed. Total items found: {len(all_items)}")
        
        return all_items
        
    def cleanup_old_data(self, days_old: int = 30):
        """Remove dados antigos do banco"""
        cursor = self.db_connection.cursor()
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        cursor.execute('''
            UPDATE market_items SET status = 'expired'
            WHERE updated_at < ? AND status = 'active'
        ''', (cutoff_date.isoformat(),))
        
        updated_rows = cursor.rowcount
        self.db_connection.commit()
        
        logger.info(f"Marked {updated_rows} old items as expired")
        
    def get_market_stats(self) -> Dict:
        """Retorna estatísticas do mercado"""
        cursor = self.db_connection.cursor()
        
        # Total de itens ativos
        cursor.execute("SELECT COUNT(*) FROM market_items WHERE status = 'active'")
        total_items = cursor.fetchone()[0]
        
        # Itens por categoria
        cursor.execute('''
            SELECT category, COUNT(*) FROM market_items 
            WHERE status = 'active' GROUP BY category
        ''')
        categories = dict(cursor.fetchall())
        
        # Preço médio por categoria
        cursor.execute('''
            SELECT category, AVG(price) FROM market_items 
            WHERE status = 'active' AND price > 0 GROUP BY category
        ''')
        avg_prices = dict(cursor.fetchall())
        
        # Itens em alta (atualizados recentemente)
        cursor.execute('''
            SELECT COUNT(*) FROM market_items 
            WHERE status = 'active' AND updated_at > datetime('now', '-24 hours')
        ''')
        trending_items = cursor.fetchone()[0]
        
        return {
            'total_items': total_items,
            'categories': categories,
            'average_prices': avg_prices,
            'trending_items': trending_items,
            'last_update': datetime.now().isoformat()
        }
        
    def close(self):
        """Fecha conexões e limpa recursos"""
        if self.db_connection:
            self.db_connection.close()
        if self.selenium_driver:
            self.selenium_driver.quit()
        logger.info("Scraper closed")

def main():
    """Função principal para executar o scraper"""
    scraper = WurmMarketScraper()
    
    try:
        # Executa scraping completo
        items = scraper.run_full_scrape()
        
        # Limpa dados antigos
        scraper.cleanup_old_data(30)
        
        # Exporta dados para JSON
        json_file = scraper.export_to_json()
        
        # Mostra estatísticas
        stats = scraper.get_market_stats()
        print("\n=== Market Statistics ===")
        print(f"Total active items: {stats['total_items']}")
        print(f"Trending items (24h): {stats['trending_items']}")
        print(f"Categories: {stats['categories']}")
        print(f"Data exported to: {json_file}")
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
    finally:
        scraper.close()

if __name__ == "__main__":
    main()
