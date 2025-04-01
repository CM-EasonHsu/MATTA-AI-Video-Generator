FROM python:3.9-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式代碼
COPY . .

# 設置環境變數
ENV PORT=8080

# 暴露端口
EXPOSE 8080

# 啟動應用程式
CMD streamlit run --server.port $PORT --server.address 0.0.0.0 app.py