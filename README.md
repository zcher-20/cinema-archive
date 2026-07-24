# Cinema Archive

A single-page film archive. Twenty-four stills in a horizontal row, drag to move
through them, click one to bring it to centre and open it.

## Running it

Open `index.html` in a browser. There is no build step and no dependencies —
everything is in the one file, including the images, which are embedded as
base64. The only external request is to Google Fonts for Archivo Black; the page
falls back to a system stack if that is blocked.

## Deploying

Push to GitHub and turn on Pages:

**Settings → Pages → Source: Deploy from a branch → `main` / `root`**

The site appears at `https://<user>.github.io/<repo>/` within a minute or two.
`index.html` at the repository root is what Pages looks for.

## Interaction

| | |
|---|---|
| Drag, scroll, or arrow keys | move along the row |
| Click a frame | centre it and zoom in |
| Click again, Escape, or drag | close |
| Click a timeline tick | jump to that film |

While a frame is open, the panel underneath holds the date field and two star
ratings, one for Seb and one for Zay.

## Known limitation

**Dates and star ratings do not persist.** They live in JavaScript memory and
reset when the page reloads. To make them permanent, the `state` array near the
top of the script needs to be replaced with a hardcoded table — one entry per
film with its date and two scores — so the values load on every visit.

## A note on the images

The stills are frames from copyrighted films, embedded directly in the HTML. If
the repository is public, they are published along with it. A private repository
avoids that.
