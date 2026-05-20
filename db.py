import mysql.connector

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "root1234",
    "database": "apms_db",
    "charset":  "utf8mb4",
    "connection_timeout": 5,
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)
