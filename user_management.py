"""
User management utility for OptionsAI authentication.
Run from terminal: python user_management.py
"""
import sys
import yaml
import streamlit_authenticator as stauth

CONFIG_FILE = "config.yaml"


def _load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def _save_config(config):
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def list_users():
    config = _load_config()
    users = config.get("credentials", {}).get("usernames", {})
    if not users:
        print("No users found.")
        return
    print(f"\n{'Username':<20} {'Name':<25} {'Email'}")
    print("-" * 65)
    for uname, data in users.items():
        name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        email = data.get("email", "")
        print(f"{uname:<20} {name:<25} {email}")
    print(f"\nTotal: {len(users)} user(s)")


def add_user():
    config = _load_config()
    users = config.setdefault("credentials", {}).setdefault("usernames", {})

    if len(users) >= 10:
        print("Maximum 10 users reached. Remove a user first.")
        return

    username = input("Username: ").strip().lower()
    if not username:
        print("Cancelled.")
        return
    if username in users:
        print(f"User '{username}' already exists.")
        return

    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    email = input("Email: ").strip()
    password = input("Password: ").strip()

    if not password:
        print("Password cannot be empty.")
        return

    hashed = stauth.Hasher.hash(password)
    users[username] = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "password": hashed,
    }
    _save_config(config)
    print(f"User '{username}' added successfully.")


def remove_user():
    config = _load_config()
    users = config.get("credentials", {}).get("usernames", {})

    if not users:
        print("No users to remove.")
        return

    list_users()
    username = input("\nUsername to remove: ").strip().lower()
    if username not in users:
        print(f"User '{username}' not found.")
        return

    confirm = input(f"Remove '{username}'? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    del users[username]
    _save_config(config)
    print(f"User '{username}' removed.")


if __name__ == "__main__":
    actions = {"list": list_users, "add": add_user, "remove": remove_user}

    if len(sys.argv) > 1 and sys.argv[1] in actions:
        actions[sys.argv[1]]()
    else:
        print("\nOptionsAI User Management")
        print("=" * 30)
        print("Usage:")
        print("  python user_management.py list     - List all users")
        print("  python user_management.py add      - Add a new user")
        print("  python user_management.py remove   - Remove a user")
