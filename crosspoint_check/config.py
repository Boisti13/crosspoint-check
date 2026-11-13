"""Settings: a TOML file, every key optional except where the library is."""
import os
import tomllib
from dataclasses import dataclass

DEFAULT_PATH = '/etc/crosspoint-check/config.toml'


class ConfigError(Exception):
    pass


@dataclass
class Config:
    library_path: str = ''
    library_command: str = ''
    repair: bool = True
    split_large: bool = False
    large_kb: int = 300
    max_kb: int = 100
    images: bool = False
    crosspoint: str = 'latest'
    state: str = '/var/lib/crosspoint-check'
    webhook: str = ''
    page_url: str = ''

    @property
    def cache(self):
        return os.path.join(self.state, 'crosspoint')

    @property
    def originals(self):
        return os.path.join(self.state, 'originals')

    @property
    def www(self):
        return os.path.join(self.state, 'www')

    @property
    def db(self):
        return os.path.join(self.state, 'state.db')


KEYS = {
    'library': {'path': 'library_path', 'command': 'library_command'},
    'check': {'repair': 'repair', 'split_large': 'split_large', 'large_kb': 'large_kb',
              'max_kb': 'max_kb', 'images': 'images', 'crosspoint': 'crosspoint'},
    'service': {'state': 'state', 'page_url': 'page_url'},
    'notify': {'webhook': 'webhook'},
}


def load(path=None):
    path = path or os.environ.get('CROSSPOINT_CHECK_CONFIG') or DEFAULT_PATH
    try:
        with open(path, 'rb') as f:
            raw = tomllib.load(f)
    except OSError as e:
        raise ConfigError('cannot read %s: %s' % (path, e)) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError('%s: %s' % (path, e)) from None
    cfg = Config()
    for section, values in raw.items():
        if section not in KEYS or not isinstance(values, dict):
            raise ConfigError('%s: unknown section [%s]' % (path, section))
        for key, value in values.items():
            if key not in KEYS[section]:
                raise ConfigError('%s: unknown setting %s in [%s]' % (path, key, section))
            attr = KEYS[section][key]
            if type(value) is not type(getattr(cfg, attr)):
                raise ConfigError('%s: %s in [%s] has the wrong type' % (path, key, section))
            setattr(cfg, attr, value)
    if bool(cfg.library_path) == bool(cfg.library_command):
        raise ConfigError('%s: set exactly one of path and command in [library]' % path)
    return cfg
