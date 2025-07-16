import sqlite3

# функции для обращения к базе
def connect_to_db(db_name='videocards.db'):
    return sqlite3.connect(db_name)

def get_total_videocards(db_name='videocards.db'):
    with connect_to_db(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Videocards")
        result = cursor.fetchone()
    return result[0] if result else 0


def get_card_id_by_name(producer, vendor, card_name, db_name='videocards.db'):

    with connect_to_db(db_name) as conn:
        cursor = conn.cursor()
        query = """
            SELECT ROWID
            FROM Videocards
            WHERE LOWER(manufacturer) = LOWER(?) 
            AND LOWER(vendor) = LOWER(?) 
            AND LOWER(name) = LOWER(?)
        """
        cursor.execute(query, (producer, vendor, card_name))
        result = cursor.fetchone()
    return result[0] if result else None

def get_unique_vendors(producer, db_name='videocards.db'):

    with connect_to_db(db_name) as conn:
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT LOWER(vendor)
            FROM Videocards
            WHERE LOWER(manufacturer) = LOWER(?)
        """
        cursor.execute(query, (producer,))
        vendors = {vendor[0].capitalize() for vendor in cursor.fetchall()}
    return sorted(vendors)

def get_total_videocards_by_vendor(producer, vendor, db_name='videocards.db'):

    with connect_to_db(db_name) as conn:
        cursor = conn.cursor()
        query = """
            SELECT COUNT(*)
            FROM Videocards
            WHERE LOWER(manufacturer) = LOWER(?) AND LOWER(vendor) = LOWER(?)
        """
        cursor.execute(query, (producer, vendor))
        total = cursor.fetchone()[0]
    return total






