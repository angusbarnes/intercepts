import tomllib
class Configuration:
    def __init__(self):
        self.global_setting_1 = True
        self.global_setting_2 = "value"

def set_conf_or_branch(obj, dictionary, name):
    cfg = Configuration()
    for section in dictionary:
        if type(dictionary[section]) == dict:
            set_conf_or_branch(config, obj[section], section)   
        else:
            setattr(cfg, section, dictionary[section])

    setattr(obj, name, cfg)

config = Configuration()

with open('config.toml', 'rb') as file:
    obj = tomllib.load(file)
    for section in obj:
        if type(obj[section]) == dict:
            set_conf_or_branch(config, obj[section], section)   
        else:
            setattr(config, section, obj[section])

def force_reload_global_config():
    global config
    with open('config.toml', 'rb') as file:
        obj = tomllib.load(file)
        for section in obj:
            if type(obj[section]) == dict:
                set_conf_or_branch(config, obj[section], section)   
            else:
                setattr(config, section, obj[section])


if __name__ == '__main__':
    print(config.assays)