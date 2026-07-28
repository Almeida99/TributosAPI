#!/bin/bash
echo "Aguardando inicialização do banco de dados..."
python init_db.py
echo "Iniciando a API..."
uvicorn src.main:app --host 0.0.0.0 --port 8000
