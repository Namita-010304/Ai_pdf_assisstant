"""
Run this script once to create the MySQL database.
Usage: python create_db.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

import mysql.connector

DB_URL = os.getenv("DATABASE_URL", "mysql+mysqlconnector://root:root@localhost:3306/pdf_assistant_db")
# Parse basic credentials from URL
# Format: mysql+mysqlconnector://user:password@host:port/dbname
parts = DB_URL.replace("mysql+mysqlconnector://", "")
credentials, rest = parts.split("@")
user, password = credentials.split(":", 1)
host_port, dbname = rest.split("/")
host, port = (host_port.split(":") if ":" in host_port else [host_port, "3306"])

conn = mysql.connector.connect(host=host, port=int(port), user=user, password=password)
cursor = conn.cursor()
cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
print(f"✅ Database `{dbname}` created (or already exists).")
cursor.close()
conn.close()
