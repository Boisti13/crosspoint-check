import pytest

from crosspoint_check import config


def write(tmp_path, text):
    p = tmp_path / 'c.toml'
    p.write_text(text)
    return str(p)


def test_defaults_and_overrides(tmp_path):
    cfg = config.load(write(tmp_path, '[library]\npath = "/books"\n[check]\nrepair = false\nlarge_kb = 500\n'))
    assert cfg.library_path == '/books' and cfg.repair is False and cfg.large_kb == 500
    assert cfg.max_kb == 100 and cfg.db == '/var/lib/crosspoint-check/state.db'


def test_example_file_loads():
    cfg = config.load('config.example.toml')
    assert cfg == config.Config(library_path='/calibre-library', repair=False)


@pytest.mark.parametrize('text, message', [
    ('[library]\npath = "/a"\ncommand = "b"\n', 'exactly one'),
    ('[check]\nrepair = true\n', 'exactly one'),
    ('[library]\npath = "/a"\n[check]\nrepiar = true\n', 'unknown setting repiar'),
    ('[library]\npath = "/a"\n[chek]\nrepair = true\n', 'unknown section'),
    ('[library]\npath = "/a"\n[check]\nrepair = "yes"\n', 'wrong type'),
    ('[library\n', 'c.toml'),
])
def test_mistakes_are_named(tmp_path, text, message):
    with pytest.raises(config.ConfigError, match=message):
        config.load(write(tmp_path, text))
