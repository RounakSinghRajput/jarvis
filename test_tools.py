from tools import build_registry

registry = build_registry()

print(registry.execute("get_current_time", {}))
print(registry.execute("get_battery_status", {}))
print(registry.execute("open_application", {"name": "Calculator"}))
print(registry.execute("open_application", {"name": "x; rm -rf /"}))  # must be refused
print(registry.execute("open_application", {}))                       # missing argument
print(registry.execute("set_volume", {"level": 150}))                 # out of range
print(registry.execute("set_volume", {"level": 30}))
print(registry.execute("does_not_exist", {}))