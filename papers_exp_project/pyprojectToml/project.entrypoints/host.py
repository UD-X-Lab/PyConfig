from importlib.metadata import entry_points

def load_plugins():
    all_entry_points = entry_points()
    plugins = all_entry_points.get("yourplugin.plugins", [])
    for entry in plugins:
        cls = entry.load()
        plugin = cls()
        plugin.run()

if __name__ == "__main__":
    load_plugins()
