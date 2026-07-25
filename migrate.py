#!/usr/bin/env python3
"""
Cinema Archive → Supabase migration script.
Reads index.html, uploads images to Supabase Storage,
and inserts film records into the `films` table.

Run AFTER pasting supabase-setup.sql into the Supabase SQL Editor.
"""

import re
import sys
import json
import base64
import urllib.request
import urllib.error
import urllib.parse

# ── Supabase credentials ───────────────────────────────────────────────
SUPABASE_URL = 'https://bmmqhphebevajdtqmqgg.supabase.co'
SUPABASE_KEY = ('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
                '.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJtbXFocGhlYmV2YWpkdHFtcWdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ5NDExMjYsImV4cCI6MjEwMDUxNzEyNn0'
                '.PZYH2b6JOC75f58HGTGgpSun8DTvwzsTsSBGcZYY3fc')
SOURCE_FILE  = '/tmp/cinema-archive/index.html'
# ──────────────────────────────────────────────────────────────────────

AUTH_HEADERS = {
    'apikey':        SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
}


def http(method, url, headers=None, data=None):
    h = dict(AUTH_HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as ex:
        return 0, str(ex).encode()


# ── 1. Check that the table exists ────────────────────────────────────
def check_table():
    status, body = http('GET', SUPABASE_URL + '/rest/v1/films?limit=0',
                        headers={'Content-Type': 'application/json',
                                 'Accept': 'application/json'})
    return status == 200


# ── 2. Fetch existing titles to avoid duplicates ─────────────────────
def fetch_existing():
    status, body = http('GET',
        SUPABASE_URL + '/rest/v1/films?select=title,list',
        headers={'Accept': 'application/json'})
    if status != 200:
        return set()
    rows = json.loads(body)
    return {(r['title'], r['list']) for r in rows}


# ── 3. Upload one image to Storage ───────────────────────────────────
def upload_image(data_url, slug):
    """Returns public URL string, or None on failure."""
    m = re.match(r'^data:([^;]+);base64,(.+)$', data_url, re.DOTALL)
    if not m:
        return None
    mime, b64 = m.group(1), m.group(2)
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None
    ext = mime.split('/')[-1]
    if ext == 'jpeg':
        ext = 'jpg'
    path = slug + '.' + ext
    url  = SUPABASE_URL + '/storage/v1/object/film-images/' + path
    status, body = http('POST', url,
                        headers={'Content-Type': mime, 'x-upsert': 'true'},
                        data=raw)
    if status in (200, 201):
        return SUPABASE_URL + '/storage/v1/object/public/film-images/' + path
    print(f'    !! storage upload failed ({status}): {body[:120]}')
    return None


# ── 4. Insert one film record ─────────────────────────────────────────
def insert_film(record):
    status, body = http('POST',
        SUPABASE_URL + '/rest/v1/films',
        headers={'Content-Type': 'application/json',
                 'Accept': 'application/json',
                 'Prefer': 'return=minimal'},
        data=json.dumps(record).encode())
    return status in (200, 201)


# ── 5. Parse archive cards from HTML ─────────────────────────────────
def parse_archive(html):
    """
    Returns list of dicts:
      {title, caption_html, data_url (may be None), gradient (may be None)}
    """
    # Find the archive rail (first .rail before wlStage)
    rail_start = html.find('<div class="rail">')
    wl_start   = html.find('<div id="wlStage">')
    rail_end   = html.find('</div>', rail_start)  # closes the <div class="rail">
    # But the rail contains nested elements; walk forward to find </div>\n</main>
    # Easier: slice up to wlStage
    archive_section = html[rail_start:wl_start]

    blocks = archive_section.split('<article class="card">')
    films  = []
    for block in blocks[1:]:
        cap = re.search(r'<h2 class="caption">(.*?)</h2>', block, re.DOTALL)
        if not cap:
            continue
        caption_html = cap.group(1).strip()
        # plain text title (strip HTML tags)
        title = re.sub(r'<[^>]+>', ' ', caption_html).strip()
        title = re.sub(r'\s+', ' ', title)
        # decode HTML entities
        title = title.replace('&#183;', '·').replace('&amp;', '&')

        img = re.search(r'<img class="still"\s+src="(data:[^"]+)"', block, re.DOTALL)
        grad = re.search(r'<div class="media"\s+style="background:([^"]+)"', block)

        films.append({
            'title':       title,
            'caption_html': caption_html,
            'data_url':    img.group(1) if img else None,
            'gradient':    grad.group(1) if grad else None,
        })
    return films


# ── 6. Parse watchlist films from wlFilms JS array ───────────────────
def parse_watchlist(html):
    """
    Returns list of dicts:
      {title, caption_html, bg, data_url, summary}
    """
    wl_start = html.find('var wlFilms = [')
    wl_end   = html.find('];', wl_start) + 2
    section  = html[wl_start:wl_end]

    # Split on each object boundary
    # Each entry is:  {  title:'...', caption:'...', bg:'...', dataUrl:'...', summary:'...'  }
    # The dataUrl value is a huge base64 string — we can't use a simple regex across it.
    # Strategy: find each title/caption/bg/summary with a short regex,
    # then locate the dataUrl by slicing between "dataUrl:'" and the matching close quote.

    results = []
    # Positions of each '{' that open a film object
    entry_positions = [m.start() for m in re.finditer(r"\{\s*\n\s*title:'", section)]

    for idx, pos in enumerate(entry_positions):
        end_pos = entry_positions[idx + 1] if idx + 1 < len(entry_positions) else len(section)
        chunk = section[pos:end_pos]

        t     = re.search(r"title:'([^']+)'", chunk)
        cap   = re.search(r"caption:'([^']+)'", chunk)
        bg    = re.search(r"bg:'([^']+)'", chunk)
        summ  = re.search(r"summary:'([^']*)'", chunk, re.DOTALL)

        # dataUrl spans the rest of the chunk — extract between dataUrl:' and next ',\n  summary
        du_match = re.search(r"dataUrl:'(data:[^']+)'", chunk, re.DOTALL)

        title       = t.group(1) if t else 'UNKNOWN'
        caption_html = cap.group(1) if cap else title
        summary     = summ.group(1) if summ else ''
        data_url    = du_match.group(1) if du_match else None
        gradient    = bg.group(1) if bg else 'linear-gradient(140deg,#111 0%,#1a1a1a 100%)'

        results.append({
            'title':        title,
            'caption_html': caption_html,
            'data_url':     data_url,
            'gradient':     gradient,
            'summary':      summary,
        })
    return results


# ── 7. Slug helper ────────────────────────────────────────────────────
def slugify(text):
    s = text.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:80]


# ── Main ──────────────────────────────────────────────────────────────
def main():
    print('Cinema Archive → Supabase migration')
    print('=====================================')

    # Check table
    print('\nChecking Supabase connection and table...')
    if not check_table():
        print('\n[ERROR] Could not reach the `films` table.')
        print('Please run supabase-setup.sql in your Supabase SQL Editor first,')
        print('then re-run this script.')
        sys.exit(1)
    print('  ✓  films table is accessible')

    existing = fetch_existing()
    print(f'  ✓  {len(existing)} film(s) already in database')

    # Read source
    print(f'\nReading {SOURCE_FILE} ...')
    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        html = f.read()
    print('  ✓  file read')

    # Parse
    archive_films = parse_archive(html)
    wl_films      = parse_watchlist(html)
    print(f'  Found {len(archive_films)} archive film(s), {len(wl_films)} watchlist film(s)')

    # Migrate archive
    print('\n--- ARCHIVE ---')
    for i, film in enumerate(archive_films):
        key = (film['title'], 'archive')
        if key in existing:
            print(f'  [{i+1:2d}] SKIP (already exists): {film["title"]}')
            continue

        print(f'  [{i+1:2d}] Migrating: {film["title"]}')
        image_url = None
        if film['data_url']:
            slug      = 'archive-' + slugify(film['title'])
            print(f'       uploading image as {slug}...')
            image_url = upload_image(film['data_url'], slug)
            if image_url:
                print(f'       ✓  {image_url}')
            else:
                print(f'       !! image upload failed, will store gradient fallback')

        record = {
            'list':        'archive',
            'title':       film['title'],
            'caption_html': film['caption_html'],
            'image_url':   image_url,
            'gradient':    film['gradient'] or 'linear-gradient(140deg,#111 0%,#1a1a1a 100%)',
            'summary':     '',
            'date_watched': '',
            'rating_seb':  0,
            'rating_zay':  0,
            'sort_order':  i,
        }
        ok = insert_film(record)
        print(f'       {"✓  inserted" if ok else "!! insert failed"}')

    # Migrate watchlist
    print('\n--- WATCHLIST ---')
    for i, film in enumerate(wl_films):
        key = (film['title'], 'watchlist')
        if key in existing:
            print(f'  [{i+1:2d}] SKIP (already exists): {film["title"]}')
            continue

        print(f'  [{i+1:2d}] Migrating: {film["title"]}')
        image_url = None
        if film['data_url']:
            slug      = 'wl-' + slugify(film['title'])
            print(f'       uploading image as {slug}...')
            image_url = upload_image(film['data_url'], slug)
            if image_url:
                print(f'       ✓  {image_url}')
            else:
                print(f'       !! image upload failed, will use gradient')

        record = {
            'list':        'watchlist',
            'title':       film['title'],
            'caption_html': film['caption_html'],
            'image_url':   image_url,
            'gradient':    film['gradient'] or 'linear-gradient(140deg,#111 0%,#1a1a1a 100%)',
            'summary':     film['summary'],
            'date_watched': '',
            'rating_seb':  0,
            'rating_zay':  0,
            'sort_order':  i,
        }
        ok = insert_film(record)
        print(f'       {"✓  inserted" if ok else "!! insert failed"}')

    print('\n=====================================')
    print('Migration complete.')
    print('Open your Supabase dashboard to verify the data.')


if __name__ == '__main__':
    main()
