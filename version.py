import json
import sys
from datetime import datetime

# Получаем текущую дату и время
build_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Check if a version increment argument is provided
if len(sys.argv) > 1:
    increment = sys.argv[1]
    try:
        inc_major, inc_minor, inc_patch = map(int, increment.split('.'))
    except ValueError:
        raise ValueError("Invalid version increment format. Use 'X.Y.Z', e.g., '0.1.3'.")

    # Load the existing version data from version.json
    try:
        with open("version.json", "r") as f:
            version_data = json.load(f)
            version = version_data.get("version", "0.0.0")
    except FileNotFoundError:
        version = "0.0.0"

    # Parse the current version
    major, minor, patch = map(int, version.split('.'))

    # Increment the version based on the provided argument
    major += inc_major
    minor += inc_minor
    patch += inc_patch

    # Handle overflow for patch and minor versions
    if patch >= 100:
        minor += patch // 100
        patch %= 100
    if minor >= 100:
        major += minor // 100
        minor %= 100

    new_version = f"{major}.{minor}.{patch:02d}"

    # Update the version data
    version_data = {
        "version": new_version,
        "buildDate": build_date
    }

    # Save the updated version data back to version.json
    with open("version.json", "w") as f:
        json.dump(version_data, f, indent=4)

    print(f"Version updated to {new_version} with the current build information.")
else:
    # Load the existing version data from version.json
    try:
        with open("version.json", "r") as f:
            version_data = json.load(f)
            current_version = version_data.get("version", "0.0.0")
            print(f"Current version: {current_version}")
    except FileNotFoundError:
        print("version.json not found. Current version: 0.0.0")
