# web_integration.py - Script de integração com a aplicação web
#!/usr/bin/env python3
"""
Web Integration Script for Wurm Online Market Tracker
Conecta o scraper com a aplicação web HTML
"""

import json
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import threading
import schedule
import time
import os
from pathlib import Path

class WurmMarketAPI:
    def __init__(self, db_path="wurm_market.db"):
        self.db_path = db_path
        self.app = Flask(__name__)
        CORS(self.app)
        self.setup_routes()
        
    def get_db_connection(self):
        """Retorna conexão com o banco de dados"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
        
    def setup_routes(self):
        """Configura as rotas da API"""
        
        @self.app.route('/api/items', methods=['GET'])
        def get_items():
            """Retorna lista de itens do mercado"""
            conn = self.get_db_connection()
            
            # Parâmetros de filtro
            server = request.args.get('server', 'all')
            category = request.args.get('category', 'all')
            limit = int(request.args.get('limit', 100))
            search = request.args.get('search', '')
            sort_by = request.args.get('sort', 'updated_at')
            order = request.args.get('order', 'DESC')
            
            # Construir query
            query = "SELECT * FROM market_items WHERE status = 'active'"
            params = []
            
            if server != 'all':
                query += " AND server = ?"
                params.append(server)
                
            if category != 'all':
                query += " AND category = ?"
                params.append(category)
                
            if search:
                query += " AND (name LIKE ? OR description LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])
                
            query += f" ORDER BY {sort_by} {order} LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            items = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return jsonify(items)
            
        @self.app.route('/api/stats', methods=['GET'])
        def get_stats():
            """Retorna estatísticas do mercado"""
            conn = self.get_db_connection()
            
            # Total de itens ativos
            total_items = conn.execute(
                "SELECT COUNT(*) as count FROM market_items WHERE status = 'active'"
            ).fetchone()['count']
            
            # Itens por categoria
            categories = conn.execute('''
                SELECT category, COUNT(*) as count 
                FROM market_items WHERE status = 'active' 
                GROUP BY category
            ''').fetchall()
            
            # Preço médio por categoria
            avg_prices = conn.execute('''
                SELECT category, AVG(price) as avg_price 
                FROM market_items WHERE status = 'active' AND price > 0 
                GROUP BY category
            ''').fetchall()
            
            # Itens em alta (últimas 24h)
            hot_items = conn.execute('''
                SELECT COUNT(*) as count FROM market_items 
                WHERE status = 'active' 
                AND updated_at > datetime('now', '-24 hours')
            ''').fetchone()['count']
            
            # Lucro médio
            avg_profit = conn.execute('''
                SELECT AVG((price - COALESCE(cost, 0)) / NULLIF(COALESCE(cost, 1), 0) * 100) as avg_profit
                FROM market_items WHERE status = 'active' AND price > 0 AND cost > 0
            ''').fetchone()['avg_profit'] or 0
            
            # Total de trades detectados
            total_trades = conn.execute('''
                SELECT SUM(quantity) as total FROM market_items WHERE status = 'active'
            ''').fetchone()['total'] or 0
            
            conn.close()
            
            return jsonify({
                'totalItems': total_items,
                'avgProfit': round(avg_profit, 1),
                'hotItems': hot_items,
                'totalTrades': total_trades,
                'categories': {row['category']: row['count'] for row in categories},
                'avgPrices': {row['category']: round(row['avg_price'], 2) for row in avg_prices}
            })
            
        @self.app.route('/api/recommendations', methods=['GET'])
        def get_recommendations():
            """Retorna recomendações de produção"""
            conn = self.get_db_connection()
            
            # Itens com alta demanda e baixa oferta
            recommendations = conn.execute('''
                SELECT name, category, AVG(price) as avg_price, 
                       COUNT(*) as frequency, MAX(updated_at) as last_seen
                FROM market_items 
                WHERE status = 'active' AND price > 0
                GROUP BY name, category
                HAVING frequency >= 2
                ORDER BY avg_price DESC, frequency DESC
                LIMIT 10
            ''').fetchall()
            
            conn.close()
            
            result = []
            for row in recommendations:
                estimated_profit = max(5, row['avg_price'] * 0.3)  # Estimativa conservadora
                result.append({
                    'name': row['name'],
                    'category': row['category'],
                    'avgPrice': round(row['avg_price'], 2),
                    'frequency': row['frequency'],
                    'estimatedProfit': f"{estimated_profit:.0f}-{estimated_profit*1.5:.0f} prata",
                    'lastSeen': row['last_seen']
                })
                
            return jsonify(result)
            
        @self.app.route('/api/add-item', methods=['POST'])
        def add_item():
            """Adiciona um novo item manualmente"""
            data = request.json
            
            required_fields = ['name', 'category', 'price', 'server']
            if not all(field in data for field in required_fields):
                return jsonify({'error': 'Missing required fields'}), 400
                
            conn = self.get_db_connection()
            
            try:
                conn.execute('''
                    INSERT INTO market_items (
                        name, category, price, cost, quality, server, 
                        seller, source, timestamp, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['name'], data['category'], data['price'], 
                    data.get('cost', 0), data.get('quality'), data['server'],
                    data.get('seller', 'manual'), 'manual', 
                    datetime.now().isoformat(), 'active'
                ))
                
                conn.commit()
                conn.close()
                
                return jsonify({'success': True, 'message': 'Item added successfully'})
                
            except Exception as e:
                conn.close()
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/api/export', methods=['GET'])
        def export_data():
            """Exporta dados em diferentes formatos"""
            format_type = request.args.get('format', 'json')
            
            conn = self.get_db_connection()
            items = conn.execute(
                "SELECT * FROM market_items WHERE status = 'active' ORDER BY updated_at DESC"
            ).fetchall()
            conn.close()
            
            if format_type == 'json':
                return jsonify([dict(row) for row in items])
            elif format_type == 'csv':
                # Implementar exportação CSV
                pass
            elif format_type == 'txt':
                # Implementar exportação TXT
                pass
                
        @self.app.route('/api/scrape', methods=['POST'])
        def trigger_scrape():
            """Dispara scraping manual"""
            try:
                # Importa e executa o scraper
                from main import WurmMarketScraper
                
                def run_scrape():
                    scraper = WurmMarketScraper()
                    scraper.run_full_scrape()
                    scraper.close()
                
                # Executa em thread separada para não bloquear
                thread = threading.Thread(target=run_scrape)
                thread.start()
                
                return jsonify({'success': True, 'message': 'Scraping started'})
                
            except Exception as e:
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/')
        def serve_frontend():
            """Serve a aplicação web"""
            return send_from_directory('.', 'index.html')
            
        @self.app.route('/<path:filename>')
        def serve_static(filename):
            """Serve arquivos estáticos"""
            return send_from_directory('.', filename)
            
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Inicia o servidor web"""
        self.app.run(host=host, port=port, debug=debug)

def setup_scheduler():
    """Configura agendamento automático de scraping"""
    def scheduled_scrape():
        try:
            from wurm_scraper import WurmMarketScraper
            scraper = WurmMarketScraper()
            scraper.run_full_scrape()
            scraper.cleanup_old_data(30)
            scraper.close()
            print(f"Scheduled scrape completed at {datetime.now()}")
        except Exception as e:
            print(f"Error in scheduled scrape: {e}")
    
    # Agenda scraping a cada 1 hora
    schedule.every(1).hours.do(scheduled_scrape)
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

if __name__ == '__main__':
    # Cria API
    api = WurmMarketAPI()
    
    # Configura agendamento
    setup_scheduler()
    
    # Inicia servidor
    print("Starting Wurm Online Market Tracker API...")
    print("Access the web interface at: http://localhost:5000")
    api.run(debug=True)
