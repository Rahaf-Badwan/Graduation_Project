import mysql.connector

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "rahaf123",
    "database": "apms_db",
    "charset":  "utf8mb4",
    "connection_timeout": 5,
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)
