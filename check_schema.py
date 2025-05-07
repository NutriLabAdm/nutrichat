import sqlite3

def check_users_table_schema():
    connection = sqlite3.connect('nutrichat.db')
    cursor = connection.cursor()

    cursor.execute("PRAGMA table_info(users);")
    columns = cursor.fetchall()

    print("Schema of 'users' table:")
    for column in columns:
        print(column)

    connection.close()

if __name__ == "__main__":
    check_users_table_schema()