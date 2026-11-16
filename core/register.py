import json

from core.utils.paths import config_path

# map = {"a":index,
#        "x":"",
#        "ljx":"",...
#       }

class CustomGamepad:
    def __init__(self):
        self.load_from_json()
        

    def save_to_json(self, name, mapping):
        self.config[name] = mapping
        path = config_path("profiles", "GenericGamepads.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    
    def load_from_json(self):
        path = config_path("profiles", "GenericGamepads.json")
        try:
            with path.open("r", encoding="utf-8") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {}
        return self.config


    def get(self, name):
        if name in self.config.keys():
            return self.config[name]
        return None
