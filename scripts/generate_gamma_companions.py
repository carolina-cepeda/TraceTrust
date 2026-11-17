from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path('docs/diagrams/gamma-companions')
OUT.mkdir(parents=True, exist_ok=True)
W, H = 720, 960
CREAM = (237, 232, 218)
BLACK = (20, 19, 16)
WHITE = (255, 255, 255)
BLUE = (45, 82, 255)
LAV = (155, 158, 242)
RED = (197, 67, 53)
GREEN = (28, 137, 96)
MUTED = (117, 112, 101)


def f(size, bold=False):
    p = Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf')
    return ImageFont.truetype(p, size) if p.exists() else ImageFont.load_default()


def base():
    im = Image.new('RGB', (W, H), CREAM)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((30, 30, W-30, H-30), radius=28, outline=(216, 210, 194), width=3)
    return im, d


def label(d, xy, text, size=24, fill=BLACK, bold=False, anchor='mm'):
    d.text(xy, text, font=f(size, bold), fill=fill, anchor=anchor)


def arrow(d, a, b, color=BLUE, width=8):
    d.line((*a, *b), fill=color, width=width)
    import math
    ang = math.atan2(b[1]-a[1], b[0]-a[0])
    s = 20
    p1 = (b[0]-s*math.cos(ang-.5), b[1]-s*math.sin(ang-.5))
    p2 = (b[0]-s*math.cos(ang+.5), b[1]-s*math.sin(ang+.5))
    d.polygon([b, p1, p2], fill=color)


def card(d, box, fill=WHITE, outline=(210, 204, 190), radius=20):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)


def save(im, name):
    im.save(OUT / name, 'PNG', optimize=True)


def slide01():
    im, d = base()
    label(d, (360, 105), 'DATOS', 22, MUTED, True)
    for i, y in enumerate((175, 235, 295)):
        card(d, (105, y, 615, y+42), WHITE)
        d.rectangle((130, y+13, 155, y+29), fill=BLUE if i == 1 else LAV)
        d.line((180, y+21, 540, y+21), fill=(190, 186, 174), width=5)
    arrow(d, (360, 355), (360, 425))
    # Trust graph motif.
    pts = [(170, 545), (350, 455), (540, 545), (350, 670)]
    for a, b in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[1], pts[3]), (pts[3], pts[2])):
        d.line((*a, *b), fill=BLACK, width=6)
    for i, p in enumerate(pts):
        d.ellipse((p[0]-38, p[1]-38, p[0]+38, p[1]+38), fill=BLUE if i == 1 else LAV, outline=BLACK, width=5)
    arrow(d, (350, 745), (350, 810), GREEN, 8)
    label(d, (360, 865), 'TRAZABILIDAD CONFIABLE', 24, BLACK, True)
    save(im, '01-problema-datos.png')


def slide02():
    im, d = base()
    label(d, (360, 100), 'TRACEABILITY LAYER', 22, MUTED, True)
    steps = [('SNAPSHOT', BLUE), ('EVENTOS', LAV), ('GRAFO', BLUE), ('IA', GREEN)]
    ys = [195, 355, 515, 675]
    for i, ((txt, col), y) in enumerate(zip(steps, ys)):
        card(d, (105, y, 615, y+92), BLACK if i == 2 else WHITE, BLACK if i == 2 else (210,204,190))
        d.ellipse((145, y+22, 195, y+72), fill=col)
        label(d, (405, y+46), txt, 25, WHITE if i == 2 else BLACK, True)
        if i < 3: arrow(d, (360, y+100), (360, y+145), BLUE, 6)
    label(d, (360, 850), 'DEL DATO A LA EXPLICACIÓN', 23, BLACK, True)
    save(im, '02-que-es-tracetrust.png')


def slide03():
    im, d = base()
    label(d, (360, 95), 'ARQUITECTURA', 22, MUTED, True)
    layers = [('PRESENTACIÓN', LAV), ('API + CONSULTAS', BLUE), ('ANÁLISIS + IA', BLACK), ('GRAFO + READ MODEL', BLUE), ('SNAPSHOTS', LAV)]
    y = 180
    for i, (txt, col) in enumerate(layers):
        h = 92
        d.rounded_rectangle((100+i*18, y+i*105, 620-i*18, y+i*105+h), radius=16, fill=col, outline=BLACK, width=3)
        label(d, (360, y+i*105+h/2), txt, 23, WHITE if col in (BLACK, BLUE) else BLACK, True)
    label(d, (360, 830), 'CAPAS SEPARADAS · CONTRATOS CLAROS', 20, BLACK, True)
    save(im, '03-arquitectura.png')


def slide04():
    im, d = base()
    label(d, (360, 95), 'EVENTO CANÓNICO', 22, MUTED, True)
    card(d, (95, 170, 625, 465), WHITE)
    d.rectangle((95, 170, 625, 235), fill=BLACK)
    label(d, (360, 202), 'EVENT · TRANSFORMATION', 21, WHITE, True)
    fields = [('event_id', 'evt-00042'), ('lot_id', 'lot-00006'), ('timestamp', '2026-01-01 14:00'), ('evidence', 'sha256: 8f2a…')]
    for i, (k, v) in enumerate(fields):
        y = 285+i*50
        label(d, (145, y), k, 19, MUTED, True, 'lm')
        label(d, (385, y), v, 19, BLACK, False, 'lm')
    arrow(d, (360, 505), (360, 570), BLUE, 7)
    for p, txt in [((180, 700), 'LOTE'), ((360, 620), 'EVENTO'), ((540, 700), 'EVIDENCIA')]:
        d.ellipse((p[0]-55, p[1]-55, p[0]+55, p[1]+55), fill=BLUE if txt == 'LOTE' else LAV, outline=BLACK, width=4)
        label(d, p, txt, 18, BLACK, True)
    d.line((225, 675, 315, 640), fill=BLACK, width=5); d.line((405, 640, 495, 675), fill=BLACK, width=5)
    save(im, '04-evento-canonico.png')


def slide05():
    im, d = base()
    label(d, (360, 95), 'DETECCIÓN', 22, MUTED, True)
    label(d, (360, 145), 'INCONSISTENCIA', 28, BLACK, True)
    pts = [(145, 300), (360, 300), (575, 300), (360, 545)]
    d.line((145, 300, 320, 300), fill=BLACK, width=8); d.line((400, 300, 575, 300), fill=BLACK, width=8)
    d.line((360, 340, 360, 505), fill=RED, width=8)
    for i, (x, y) in enumerate(pts):
        col = RED if i == 3 else BLUE
        d.ellipse((x-48, y-48, x+48, y+48), fill=col, outline=BLACK, width=4)
        if i == 3:
            label(d, (x, y), '!', 40, WHITE, True)
        else:
            d.line((x-20, y, x-5, y+16), fill=WHITE, width=8)
            d.line((x-5, y+16, x+24, y-20), fill=WHITE, width=8)
    card(d, (105, 650, 615, 785), fill=BLACK, outline=BLACK)
    label(d, (360, 690), 'hallazgo explicable', 23, WHITE, True)
    label(d, (360, 735), 'lote huérfano · confianza reducida', 18, (230, 225, 215))
    save(im, '05-inconsistencias.png')


def slide06():
    im, d = base()
    label(d, (360, 95), 'TRUST SCORE', 22, MUTED, True)
    d.arc((115, 175, 605, 665), 180, 360, fill=(210, 204, 190), width=42)
    d.arc((115, 175, 605, 665), 180, 310, fill=GREEN, width=42)
    label(d, (360, 420), '72.40', 68, GREEN, True)
    label(d, (360, 480), '/ 100', 27, BLACK, True)
    factors = [('provenance', 0.88), ('genealogy', 0.70), ('quantity', 0.92), ('temporal', 0.62)]
    for i, (txt, val) in enumerate(factors):
        y = 710+i*42
        label(d, (120, y), txt, 17, BLACK, False, 'lm')
        d.rounded_rectangle((280, y-8, 600, y+8), radius=8, fill=(214, 209, 198))
        d.rounded_rectangle((280, y-8, 280+320*val, y+8), radius=8, fill=BLUE)
    save(im, '06-trust-score.png')


def slide07():
    im, d = base()
    label(d, (360, 95), 'DEMO', 22, MUTED, True)
    for i, (txt, col) in enumerate([('1 · SNAPSHOT', BLUE), ('2 · LOTE', LAV), ('3 · GRAFO', BLUE), ('4 · HALLAZGO', RED)]):
        y = 180+i*145
        d.ellipse((105, y, 175, y+70), fill=col, outline=BLACK, width=3)
        label(d, (140, y+35), str(i+1), 25, WHITE if col != LAV else BLACK, True)
        label(d, (220, y+35), txt, 24, BLACK, True, 'lm')
        if i < 3: arrow(d, (140, y+80), (140, y+125), BLACK, 5)
    card(d, (105, 785, 615, 850), fill=BLACK, outline=BLACK)
    label(d, (360, 818), 'GLOBAL → DRILL-DOWN', 20, WHITE, True)
    save(im, '07-demo.png')


def slide08():
    im, d = base()
    label(d, (360, 95), 'RESULTADOS', 22, MUTED, True)
    stats = [('72', 'eventos'), ('36', 'lotes'), ('12', 'hallazgos'), ('98.5', 'trust medio')]
    for i, (num, txt) in enumerate(stats):
        y = 175+i*150
        card(d, (100, y, 620, y+110), BLACK if i == 3 else WHITE, BLACK if i == 3 else (210,204,190))
        label(d, (170, y+55), num, 45, GREEN if i == 3 else BLUE, True)
        label(d, (350, y+55), txt, 22, WHITE if i == 3 else BLACK, True, 'lm')
    save(im, '08-resultados.png')


def slide09():
    im, d = base()
    label(d, (360, 95), 'EVOLUCIÓN', 22, MUTED, True)
    card(d, (105, 180, 615, 440), fill=BLACK, outline=BLACK)
    label(d, (360, 220), 'MVP', 27, WHITE, True)
    for i, txt in enumerate(['grafo consultable', 'reglas explicables', 'dashboard offline']):
        label(d, (155, 290+i*55), '✓', 24, GREEN, True, 'lm')
        label(d, (205, 290+i*55), txt, 20, WHITE, False, 'lm')
    arrow(d, (360, 475), (360, 545), BLUE, 7)
    card(d, (105, 575, 615, 780), fill=LAV, outline=BLACK)
    label(d, (360, 615), 'SIGUIENTE', 27, BLACK, True)
    for i, txt in enumerate(['alertas en streaming', 'modelos de IA', 'multi-tenant']):
        label(d, (155, 680+i*35), '→', 19, BLUE, True, 'lm')
        label(d, (205, 680+i*35), txt, 18, BLACK, False, 'lm')
    save(im, '09-roadmap.png')


if __name__ == '__main__':
    for fn in (slide01, slide02, slide03, slide04, slide05, slide06, slide07, slide08, slide09):
        fn()
