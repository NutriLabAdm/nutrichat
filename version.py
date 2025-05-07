import json
from datetime import datetime

# Получаем текущую дату и время
build_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Указываем версию приложения
version = "0.02.00"  # Это может быть параметр, который можно обновлять вручную или автоматически

# Создаем структуру данных
version_data = {
    "version": version,
    "buildDate": build_date
}

# Сохраняем в файл
with open("version.json", "w") as f:
    json.dump(version_data, f, indent=4)

print("Version file created with the current build information.")
