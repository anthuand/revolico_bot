"""
Database Core Module
-------------------
Efficient SQLite database operations for filters and ads.
"""

import sqlite3
import os
from typing import Any, List, Optional, Set, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'anuncios.db')

def get_connection() -> sqlite3.Connection:
    """
    Returns a new SQLite connection to the main database.
    """
    return sqlite3.connect(DB_PATH)

def create_filters_table() -> None:
    """
    Creates the filters table if it does not exist.
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS filters (
                id INTEGER PRIMARY KEY,
                department TEXT,
                keyword TEXT,
                price_min INTEGER,
                price_max INTEGER,
                province TEXT,
                municipality TEXT,
                photos TEXT
            )
            """
        )
        conn.commit()

def insert_filter(department: str, keyword: str, price_min: Optional[int] = None, price_max: Optional[int] = None, province: Optional[str] = None, municipality: Optional[str] = None, photos: Optional[bool] = False) -> None:
    """
    Inserts a new filter into the filters table.
    """
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO filters (department, keyword, price_min, price_max, province, municipality, photos) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (department, keyword, price_min, price_max, province, municipality, str(photos))
        )
        conn.commit()

def get_filters() -> List[Tuple[Any, ...]]:
    """
    Returns all filters from the filters table.
    """
    with get_connection() as conn:
        return conn.execute("SELECT * FROM filters").fetchall()

def update_filter(filter_id: int, param: str, value: Any) -> None:
    """
    Updates a specific parameter of a filter by its ID.
    """
    with get_connection() as conn:
        conn.execute(f'UPDATE filters SET {param} = ? WHERE id = ?', (value, filter_id))
        conn.commit()

def delete_filter(filter_id: int) -> None:
    """
    Deletes a filter by its ID.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM filters WHERE id = ?;", (filter_id,))
        conn.commit()

def create_ads_table() -> None:
    """
    Drops and recreates the ads table.
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                price TEXT,
                description TEXT,
                date TEXT,
                location TEXT,
                photo TEXT
            )
            """
        )
        conn.commit()

def insert_ad(url: str, title: str, price: str, description: str, date: str, location: str, photo: str) -> None:
    """
    Inserts a new ad into the ads table.
    """
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO ads (url, title, price, description, date, location, photo) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (url, title, price, description, date, location, photo)
        )
        conn.commit()

def get_ads() -> List[Tuple[Any, ...]]:
    """
    Returns all ads from the ads table.
    """
    with get_connection() as conn:
        return conn.execute("SELECT * FROM ads").fetchall()

def create_seen_ads_table() -> None:
    """
    Creates the seen_ads table if it does not exist.
    """
    with get_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS seen_ads (url TEXT PRIMARY KEY)")
        conn.commit()

def add_seen_ad(url: str) -> None:
    """
    Adds a URL to the seen_ads table (if not already present).
    """
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO seen_ads (url) VALUES (?)", (url,))
        conn.commit()

def get_seen_ads() -> Set[str]:
    """
    Returns a set of all seen ad URLs.
    """
    with get_connection() as conn:
        return set(row[0] for row in conn.execute("SELECT url FROM seen_ads")) 