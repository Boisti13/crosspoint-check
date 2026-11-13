"""Repair an EPUB so CrossPoint can open it.

- Splits every spine (X)HTML file bigger than `max_kb` into several files,
  cutting at table-of-contents anchors (chapter starts) first and by size
  otherwise. Updates the OPF manifest and spine, the NCX / EPUB 3 nav and
  every link.
- Re-serialises all XHTML as well-formed XML (the firmware's parser is strict).
- Writes the charset line as
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  in every XHTML file. Calibre-Web-Automated's EPUB fixer (seen in v4.0.8)
  turns any other form into an unclosed <meta charset="utf-8">, which
  CrossPoint rejects ("Failed to index - invalid book").
- Optionally (`images=True`, needs Pillow) reworks pictures for a 480x800
  e-paper screen: cover 480 px wide in colour, others at most 464x680 in
  pure black and white, all baseline JPEG.
"""
import io
import posixpath
import re
import zipfile
from urllib.parse import unquote

import lxml.etree as E
import lxml.html

XHTML = 'http://www.w3.org/1999/xhtml'
OPF = 'http://www.idpf.org/2007/opf'
NCX = 'http://www.daisy.org/z3986/2005/ncx/'
META = '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'
HTML_TYPES = ('application/xhtml+xml', 'text/html')


def parse_xhtml(data):
    """Returns (root element, True if the file was not well-formed and had to be mended)."""
    try:
        return E.fromstring(data, E.XMLParser(recover=False, resolve_entities=False, huge_tree=True)), False
    except E.XMLSyntaxError:
        # Not well-formed: let the HTML parser repair it, then make it XHTML.
        doc = lxml.html.document_fromstring(data)
        for el in doc.iter():
            if isinstance(el.tag, str) and not el.tag.startswith('{'):
                el.tag = '{%s}%s' % (XHTML, el.tag)
        root = E.Element('{%s}html' % XHTML, nsmap={None: XHTML})
        for c in list(doc):
            root.append(c)
        return root, True


def serialise(root):
    head = root.find('{%s}head' % XHTML)
    if head is None:
        head = E.Element('{%s}head' % XHTML)
        root.insert(0, head)
    for m in head.findall('{%s}meta' % XHTML):
        if m.get('charset') or 'charset' in (m.get('content') or '').lower():
            head.remove(m)
    meta = E.fromstring(META.replace('<meta ', '<meta xmlns="%s" ' % XHTML))
    meta.tail = '\n'
    head.insert(0, meta)
    out = E.tostring(root, encoding='utf-8', xml_declaration=True)
    # lxml writes attributes in the order set; make sure http-equiv comes first.
    return re.sub(rb'<meta[^>]*charset[^>]*/>', META.encode(), out, count=1)


def ids_in(el):
    return {e.get('id') for e in el.iter() if isinstance(e.tag, str) and e.get('id')}


def split_body(root, anchors, max_bytes):
    """Return a list of lists of top-level body children, one list per part."""
    body = root.find('{%s}body' % XHTML)
    container = body
    # Descend through single wrapper elements (e.g. <body><div class="book">).
    while len([c for c in container if isinstance(c.tag, str)]) == 1:
        container = [c for c in container if isinstance(c.tag, str)][0]
    if container is not body:
        # Move the wrapper's children up into body; keep the wrapper's attributes off.
        for c in list(body):
            body.remove(c)
        for c in list(container):
            body.append(c)
    parts, cur, size = [], [], 0
    for c in list(body):
        n = len(E.tostring(c))
        starts_chapter = bool(ids_in(c) & anchors) if isinstance(c.tag, str) else False
        if cur and (starts_chapter or size + n > max_bytes):
            parts.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += n
    if cur:
        parts.append(cur)
    return body, parts


def fix(src, dst, images=False, max_kb=100):
    """Write a repaired copy of `src` to `dst`; returns what was changed, one line each."""
    if images:
        from PIL import Image

    z = zipfile.ZipFile(src)
    files = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    container = E.fromstring(files['META-INF/container.xml'])
    opf_path = container.xpath('//*[local-name()="rootfile"]/@full-path')[0]
    opf_dir = posixpath.dirname(opf_path)
    opf = E.fromstring(files[opf_path])
    manifest = opf.find('{%s}manifest' % OPF)
    spine = opf.find('{%s}spine' % OPF)
    items = {i.get('id'): i for i in manifest.findall('{%s}item' % OPF)}

    def full(href, base=opf_dir):
        return posixpath.normpath(posixpath.join(base, unquote(href.split('#')[0])))

    # TOC files: NCX and EPUB3 nav.
    toc_files = [full(i.get('href')) for i in manifest.findall('{%s}item' % OPF)
                 if i.get('media-type') == 'application/x-dtbncx+xml' or 'nav' in (i.get('properties') or '').split()]
    anchors_by_file = {}
    for t in toc_files:
        text = files[t].decode('utf-8', 'replace')
        for ref in re.findall(r'(?:src|href)="([^"]+)"', text):
            if '#' in ref:
                anchors_by_file.setdefault(full(ref, posixpath.dirname(t)), set()).add(ref.split('#', 1)[1])

    renames = {}          # (old_file, id) -> new_file ; (old_file, None) -> first new file
    new_docs = {}         # path -> bytes
    report = []
    mended = 0
    for ref in spine.findall('{%s}itemref' % OPF):
        item = items[ref.get('idref')]
        if item.get('media-type') not in HTML_TYPES:
            continue
        path = full(item.get('href'))
        data = files[path]
        root, was_broken = parse_xhtml(data)
        mended += was_broken
        if len(data) <= max_kb * 1024:
            new_docs[path] = root
            continue
        body, parts = split_body(root, anchors_by_file.get(path, set()), max_kb * 1024)
        head = root.find('{%s}head' % XHTML)
        stem, ext = posixpath.splitext(item.get('href'))
        new_refs = []
        for k, children in enumerate(parts):
            href = '%s_%03d%s' % (stem, k, ext)
            npath = full(href)
            h = E.Element('{%s}html' % XHTML, nsmap={None: XHTML})
            for at, v in root.attrib.items():
                h.set(at, v)
            h.append(E.fromstring(E.tostring(head)))
            b = E.SubElement(h, '{%s}body' % XHTML, dict(body.attrib))
            for c in children:
                b.append(c)
                for i in ids_in(c):
                    renames[(path, i)] = npath
            if k == 0:
                renames[(path, None)] = npath
            new_docs[npath] = h
            nid = '%s_%03d' % (item.get('id'), k)
            new = E.Element('{%s}item' % OPF, id=nid, href=href, **{'media-type': 'application/xhtml+xml'})
            item.addprevious(new)
            r = E.Element('{%s}itemref' % OPF, idref=nid)
            ref.addprevious(r)
            new_refs.append(r)
        manifest.remove(item)
        spine.remove(ref)
        del files[path]
        report.append('%s (%d KB) split into %d files' % (path, len(data) // 1024, len(parts)))

    # Image handling.
    img_renames = {}
    n_images = 0
    cover_ids = {m.get('content') for m in opf.iter('{%s}meta' % OPF) if m.get('name') == 'cover'}
    cover_ids |= {i.get('id') for i in manifest.findall('{%s}item' % OPF) if 'cover-image' in (i.get('properties') or '').split()}
    if images:
        for i in manifest.findall('{%s}item' % OPF):
            mt = i.get('media-type') or ''
            if not mt.startswith('image/') or mt == 'image/svg+xml':
                continue
            path = full(i.get('href'))
            im = Image.open(io.BytesIO(files[path]))
            if im.mode in ('RGBA', 'LA', 'P'):
                im = im.convert('RGBA')
                bg = Image.new('RGB', im.size, 'white')
                bg.paste(im, mask=im.split()[-1])
                im = bg
            im = im.convert('RGB')
            if i.get('id') in cover_ids:
                im = im.resize((480, round(im.height * 480 / im.width)), Image.LANCZOS)
            else:
                im.thumbnail((464, 680), Image.LANCZOS)
                im = im.convert('L').point(lambda p: 255 if p > 127 else 0)
            o = io.BytesIO()
            im.save(o, 'JPEG', quality=90, progressive=False, optimize=True)
            del files[path]
            href = i.get('href')
            if not re.search(r'\.jpe?g$', href, re.I):
                nhref = posixpath.splitext(href)[0] + '.jpg'
                img_renames[posixpath.basename(href)] = posixpath.basename(nhref)
                i.set('href', nhref)
                path = full(nhref)
            i.set('media-type', 'image/jpeg')
            files[path] = o.getvalue()
            n_images += 1

    def fix_links(text, base):
        def sub(m):
            attr, ref = m.group(1), m.group(2)
            if re.match(r'^[a-z]+:', ref):
                return m.group(0)
            target_file = full(ref, base) if ref.split('#')[0] else None
            frag = ref.split('#', 1)[1] if '#' in ref else None
            if target_file is None:
                return m.group(0)
            new = renames.get((target_file, frag)) or renames.get((target_file, None)) if (target_file, None) in renames else None
            if not new:
                return m.group(0)
            rel = posixpath.relpath(new, base or '.')
            return '%s="%s%s"' % (attr, rel, '#' + frag if frag else '')
        text = re.sub(r'(href|src)="([^"]+)"', sub, text)
        for old, new in img_renames.items():
            text = text.replace(old, new)
        return text

    # Same-file links (#id) inside split parts must name their new file.
    out_docs = {}
    for path, root in new_docs.items():
        data = serialise(root).decode('utf-8')
        base = posixpath.dirname(path)
        origin = next((o for (o, i), n in renames.items() if n == path), None)

        def local(m):
            frag = m.group(2)
            if origin and (origin, frag) in renames:
                return '%s="%s#%s"' % (m.group(1), posixpath.relpath(renames[(origin, frag)], base or '.'), frag)
            return m.group(0)
        data = re.sub(r'(href)="#([^"]+)"', local, data)
        out_docs[path] = fix_links(data, base).encode('utf-8')

    # Non-spine XHTML (rare) also gets the charset line.
    for i in manifest.findall('{%s}item' % OPF):
        p = full(i.get('href'))
        if i.get('media-type') in HTML_TYPES and p not in out_docs and p in files:
            root, was_broken = parse_xhtml(files[p])
            mended += was_broken
            out_docs[p] = fix_links(serialise(root).decode('utf-8'), posixpath.dirname(p)).encode('utf-8')
    for t in toc_files:
        files[t] = fix_links(files[t].decode('utf-8'), posixpath.dirname(t)).encode('utf-8')
    for p in list(files):
        if p.endswith('.css'):
            files[p] = fix_links(files[p].decode('utf-8', 'replace'), posixpath.dirname(p)).encode('utf-8')
    files[opf_path] = E.tostring(opf, encoding='utf-8', xml_declaration=True)
    files.update(out_docs)

    out = zipfile.ZipFile(dst, 'w')
    out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
    for n, d in files.items():
        if n != 'mimetype':
            out.writestr(n, d, compress_type=zipfile.ZIP_DEFLATED)
    out.close()
    big = max(len(d) for d in out_docs.values()) if out_docs else 0
    if mended:
        report.append('%d chapter files were not well-formed XML and were mended' % mended)
    report.append('all %d chapter files rewritten, largest now %d KB' % (len(out_docs), big // 1024))
    if images:
        report.append('%d images reworked (%d renamed to .jpg)' % (n_images, len(img_renames)))
    return report
