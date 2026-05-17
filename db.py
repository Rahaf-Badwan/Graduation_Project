import mysql.connector

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "root123",
    "database": "apms_db",
    "charset":  "utf8mb4",
    "connection_timeout": 5,
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)
