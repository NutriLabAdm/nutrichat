import sqlite3

def list_tables():
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect("nutrichat.db")
        cursor = connection.cursor()

        # Query to list all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if tables:
            print("Tables in the database:")
            for table in tables:
                print(f"- {table[0]}")
        else:
            print("No tables found in the database.")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")

    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    list_tables()