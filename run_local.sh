#!/bin/bash

# 確保腳本在錯誤時停止
set -e

# 檢查是否存在虛擬環境
if [ ! -d "venv" ]; then
  echo "創建虛擬環境..."
  python3.12 -m venv venv
fi

# 激活虛擬環境
echo "激活虛擬環境..."
source venv/bin/activate

# 安裝依賴
echo "安裝依賴..."
pip install -r requirements.txt

# 從 .env 文件加載環境變數
if [ -f .env ]; then
  echo "加載環境變數..."
  export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
else
  echo "警告: 找不到 .env 文件。請確保您已設置必要的環境變數。"
fi

# 運行應用程式
echo "啟動 Streamlit 應用程式..."
streamlit run app.py