"""Verify an assembled chartbook's files, links, PDF and selected numeric claims."""
import argparse
import csv
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from PIL import Image


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src') and value:
                self.targets.append(value)


def verify(root):
    manifest = json.loads((root/'manifest.json').read_text())
    for name, record in manifest['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError('Path escapes artifact root: '+name)
        if path.stat().st_size != record['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('Payload checksum mismatch: '+name)
    records = json.loads((root/'chart-index.json').read_text())
    sources = json.loads((root/'sources.json').read_text())
    assert len(records) == 19 and len({r['id'] for r in records}) == 19
    for record in records:
        with Image.open(root/record['png']) as image:
            assert image.width >= 1000 and image.height >= 500
            image.verify()
        if record['svg']:
            ET.parse(root/record['svg'])
        assert record['source'] in sources
    for source in sources.values():
        assert hashlib.sha256((root/source['local_path']).read_bytes()).hexdigest() == source['sha256']
    legacy = json.loads((root/'evidence/legacy-manifest.json').read_text())
    for record in records:
        if record['origin']=='reused_exact':
            expected = legacy['files'][record['png']]['sha256']
            assert hashlib.sha256((root/record['png']).read_bytes()).hexdigest() == expected
    links=Links();links.feed((root/'index.html').read_text())
    for value in links.targets:
        parsed=urlsplit(value)
        if parsed.scheme or not parsed.path:
            continue
        path=(root/unquote(parsed.path)).resolve()
        assert path.is_relative_to(root.resolve()) and path.is_file(), value
    for value in re.findall(r'\]\(([^)]+)\)', (root/'report.md').read_text()):
        assert (root/value).is_file(), value
    rows=list(csv.DictReader((root/'metrics.csv').open(encoding='utf-8-sig')))
    assert len(rows)==157
    for row in rows:
        assert row['source'] in sources and row['figure'] in {r['id'][:2] for r in records}
        assert math.isfinite(float(row['value'])) and float(row['sample_n'])>0
    def number(figure,metric,condition):
        matches=[r for r in rows if r['figure']==figure and r['metric']==metric and r['condition']==condition]
        assert len(matches)==1
        return float(matches[0]['value'])
    assert number('08','task_successes','v1')==5 and number('08','task_successes','v2')==4
    assert number('15','suspected_black_frames','right_hand_rgb')==5453
    assert number('15','suspected_black_frames','left_hand_rgb')==4
    assert number('15','suspected_black_frames','third_person_rgb')==0
    assert number('16','trajectory_count','readback')==8
    assert number('16','trajectory_count','strict_success')==7
    assert number('17','required_ram','24-env-model')==144
    assert number('17','effective_available_ram','observed')<144
    pdf=root/'experiment-chartbook.pdf'
    info=subprocess.check_output(['pdfinfo',str(pdf)],text=True)
    assert re.search(r'Pages:\s+20\b',info)
    text=subprocess.run(['pdftotext',str(pdf),'-'],text=True,capture_output=True,check=True)
    assert not text.stderr.strip(),text.stderr
    assert '具身数据生产' in text.stdout and '24' in text.stdout
    return dict(status='passed',charts=len(records),pdf_pages=20,metric_rows=len(rows),
                legacy_byte_identical=14,new_svg_valid=5,local_links_checked=len(links.targets),
                checks='Payload/source hashes, images, SVG XML, HTML/Markdown links, CSV claims, PDF text/fonts/pages')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.directory),ensure_ascii=False,indent=2))
