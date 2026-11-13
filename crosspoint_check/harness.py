"""CrossPoint's own EPUB code, built for this machine.

CrossPoint ships host unit tests for its ZIP reader and its chapter parser.
We clone a release, add one test to each that reads the files we point it
at, and build just those two test programs. Nothing of CrossPoint is copied
into this project; the build lives in the cache folder, one per release.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from xml.parsers import expat

REPO = 'https://github.com/crosspoint-reader/crosspoint-reader.git'
LATEST = 'https://api.github.com/repos/crosspoint-reader/crosspoint-reader/releases/latest'
HTML_EXT = ('.html', '.xhtml', '.htm')

PARSER_TEST = r'''

// crosspoint-check: parse every file in $XHTML_DIR the way a section build does.
TEST_F(ChapterHtmlSlimParserTest, ZZExternalFiles) {
  const char* dir = getenv("XHTML_DIR");
  if (!dir) GTEST_SKIP();
  for (const auto& e : std::filesystem::directory_iterator(dir)) {
    filepath = e.path().string();
    parser.~ChapterHtmlSlimParser();
    new (&parser) ChapterHtmlSlimParser{nullptr, filepath, renderer, 0, 1.0f, false, 0,
        static_cast<uint16_t>(renderer.getScreenWidth()), static_cast<uint16_t>(renderer.getScreenHeight()),
        false, false, {}, true, "", "", 0, {}, nullptr, &cssParser};
    parser.currentTextBlock = std::make_unique<ParsedText>();
    int pages = 0;
    parser.completePageFn = [&](std::unique_ptr<Page>, auto, auto, auto) { pages++; };
    const bool ok = parser.parseAndBuildPages();
    printf("%s %s pages=%d\n", ok ? "OK  " : "FAIL", e.path().filename().c_str(), pages);
  }
}
'''

ZIP_TEST = r'''

// crosspoint-check: read every entry of $EPUB with the firmware's ZipFile.
#include <fstream>
#include <iterator>
TEST_F(ZipFileTest, ZZExternal) {
  const char* f = getenv("EPUB");
  if (!f) GTEST_SKIP();
  std::ifstream in(f, std::ios::binary);
  std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
  Storage.setFile(path, std::move(bytes));
  ZipFile zip(path);
  std::vector<std::string> names;
  zip.enumerateFilePaths([&](auto n) { names.emplace_back(n.data(), n.size()); return true; });
  printf("entries %zu\n", names.size());
  for (auto& n : names) {
    size_t s = 0;
    const bool ok1 = zip.getInflatedFileSize(n.c_str(), &s);
    VectorSink sink;
    const bool ok2 = zip.readFileToStream(n.c_str(), sink, 8192);
    printf("%s %s\n", ok1 && ok2 && sink.text().size() == s ? "OK  " : "FAIL", n.c_str());
  }
}
'''

PARSER_BIN = 'build/test/chapter_html_slim_parser/ChapterHtmlSlimParserTest'
ZIP_BIN = 'build/test/zip_file/ZipFileTest'


class HarnessError(Exception):
    pass


@dataclass
class Problem:
    file: str      # name inside the EPUB
    kind: str      # 'zip', 'chapter' or 'large'
    detail: str    # one plain sentence


@dataclass
class Result:
    tag: str
    chapters: int = 0
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.problems


def latest_tag(cache, max_age=86400):
    """Newest CrossPoint release; asked at most once a day, None when offline."""
    note = os.path.join(cache, 'latest.json')
    try:
        with open(note) as f:
            seen = json.load(f)
        if time.time() - seen['at'] < max_age:
            return seen['tag']
    except (OSError, ValueError, KeyError):
        pass
    try:
        headers = {'User-Agent': 'crosspoint-check', 'Accept': 'application/vnd.github+json'}
        if os.environ.get('GITHUB_TOKEN'):  # optional, only to avoid GitHub's anonymous rate limit
            headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
        req = urllib.request.Request(LATEST, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            tag = json.load(r)['tag_name']
    except Exception:
        return None
    os.makedirs(cache, exist_ok=True)
    with open(note, 'w') as f:
        json.dump({'tag': tag, 'at': time.time()}, f)
    return tag


def built_tags(cache):
    """Releases already built here, newest build first."""
    tags = []
    if os.path.isdir(cache):
        for name in os.listdir(cache):
            src = os.path.join(cache, name)
            if all(os.access(os.path.join(src, b), os.X_OK) for b in (PARSER_BIN, ZIP_BIN)):
                tags.append((os.path.getmtime(os.path.join(src, PARSER_BIN)), name))
    return [name for _, name in sorted(tags, reverse=True)]


def build(cache, tag, log=print):
    """Clone CrossPoint at `tag` and build the two test programs (about two minutes)."""
    for tool in ('git', 'cmake', 'c++'):
        if not shutil.which(tool):
            raise HarnessError('%s is not installed (needed to build CrossPoint\'s parser)' % tool)
    src = os.path.join(cache, tag)
    tmp = src + '.building'
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(cache, exist_ok=True)
    log('building CrossPoint %s parser in %s' % (tag, src))

    def run(*cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-15:]
            raise HarnessError('%s failed:\n%s' % (' '.join(cmd[:3]), '\n'.join(tail)))

    try:
        run('git', 'clone', '-q', '--depth', '1', '--branch', tag, REPO, tmp)
        run('git', '-C', tmp, 'submodule', 'update', '-q', '--init', '--depth', '1')
        for rel, code in (('test/chapter_html_slim_parser/ChapterHtmlSlimParserTest.cpp', PARSER_TEST),
                          ('test/zip_file/ZipFileTest.cpp', ZIP_TEST)):
            path = os.path.join(tmp, rel)
            if not os.path.isfile(path):
                raise HarnessError('CrossPoint %s has no %s (its tests changed)' % (tag, rel))
            with open(path, 'a') as f:
                f.write(code)
        out = os.path.join(tmp, 'build/test')
        run('cmake', '-S', os.path.join(tmp, 'test'), '-B', out, '-DCMAKE_BUILD_TYPE=Release')
        run('cmake', '--build', out, '--target', 'ChapterHtmlSlimParserTest', 'ZipFileTest',
            '-j%d' % (os.cpu_count() or 2))
    except HarnessError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(src, ignore_errors=True)
    os.rename(tmp, src)
    return src


def ensure(cache, tag='latest', log=print):
    """Return (tag, note): a built release to check with, and why if it isn't the wanted one."""
    have = built_tags(cache)
    want = tag
    if tag == 'latest':
        want = latest_tag(cache)
        if want is None:
            if have:
                return have[0], 'GitHub not reachable, checking with CrossPoint %s' % have[0]
            raise HarnessError('GitHub not reachable and no CrossPoint build here yet')
    if want in have:
        return want, None
    try:
        build(cache, want, log)
        return want, None
    except HarnessError as e:
        if have:
            return have[0], 'CrossPoint %s did not build (%s), checking with %s' % (
                want, str(e).splitlines()[0], have[0])
        raise


def _xml_error(data):
    """What an XML parser says about a chapter the firmware refused."""
    p = expat.ParserCreate()
    try:
        p.Parse(data, True)
    except expat.ExpatError as e:
        return 'not well-formed XML: %s' % e
    return 'the firmware\'s parser refused it'


def _lines(binary, env_name, value, timeout):
    env = dict(os.environ, **{env_name: value})
    try:
        r = subprocess.run([binary, '--gtest_filter=*ZZExternal*'], env=env, capture_output=True,
                           timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise HarnessError('CrossPoint\'s parser did not finish within %d s' % timeout) from None
    out = r.stdout.decode('utf-8', 'replace').splitlines()
    return [line for line in out if line.startswith(('OK  ', 'FAIL'))]


def check(cache, tag, epub, large_kb=0, timeout=600):
    """Run one EPUB through the firmware's ZIP reader and chapter parser."""
    src = os.path.join(cache, tag)
    res = Result(tag=tag)
    try:
        z = zipfile.ZipFile(epub)
        names = [n for n in z.namelist() if not n.endswith('/')]
    except (zipfile.BadZipFile, OSError) as e:
        res.problems.append(Problem(os.path.basename(epub), 'zip', 'not a ZIP file: %s' % e))
        return res

    ziplines = _lines(os.path.join(src, ZIP_BIN), 'EPUB', os.path.abspath(epub), timeout)
    if not ziplines and names:
        res.problems.append(Problem(os.path.basename(epub), 'zip', 'the firmware\'s ZIP reader found no files in it'))
    for line in ziplines:
        if line.startswith('FAIL'):
            res.problems.append(Problem(line[5:], 'zip', 'the firmware\'s ZIP reader cannot unpack it'))

    chapters = [n for n in names if n.lower().endswith(HTML_EXT)]
    res.chapters = len(chapters)
    with tempfile.TemporaryDirectory(prefix='crosspoint-check-') as work:
        data = {}
        for i, name in enumerate(chapters):
            try:
                data[i] = z.read(name)
            except Exception as e:
                res.problems.append(Problem(name, 'zip', 'cannot be unpacked: %s' % e))
                continue
            with open(os.path.join(work, '%05d.xhtml' % i), 'wb') as f:
                f.write(data[i])
            if large_kb and len(data[i]) > large_kb * 1024:
                res.warnings.append(Problem(name, 'large', '%d KB in one chapter file' % (len(data[i]) // 1024)))
        seen = set()
        for line in _lines(os.path.join(src, PARSER_BIN), 'XHTML_DIR', work, timeout):
            i = int(line[5:].split('.')[0])
            seen.add(i)
            if line.startswith('FAIL'):
                res.problems.append(Problem(chapters[i], 'chapter', _xml_error(data[i])))
        missed = sorted(set(data) - seen)
        if missed:
            res.problems.append(Problem(chapters[missed[0]], 'chapter',
                                        'the firmware\'s parser crashed; %d chapter files were not checked' % len(missed)))
    return res
