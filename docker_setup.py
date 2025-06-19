# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \\
    wget \\
    unzip \\
    curl \\
    gnupg \\
    && rm -rf /var/lib/apt/lists/*

# Instala Chrome para Selenium
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \\
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \\
    && apt-get update \\
    && apt-get install -y google-chrome-stable \\
    && rm -rf /var/lib/apt/lists/*

# Instala ChromeDriver
RUN CHROME_DRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE) \\
    && wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/\$CHROME_DRIVER_VERSION/chromedriver_linux64.zip \\
    && unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/ \\
    && rm /tmp/chromedriver.zip \\
    && chmod +x /usr/local/bin/chromedriver

# Copia arquivos da aplicação
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Executa setup inicial
RUN python3 setup_scraper.py

EXPOSE 5000

CMD ["python3", "web_integration.py"]

# docker-compose.yml
version: '3.8'
services:
  wurm-tracker:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./config.json:/app/config.json
    environment:
      - FLASK_ENV=production
    restart: unless-stopped
