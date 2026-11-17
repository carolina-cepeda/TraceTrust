from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


OUT = Path('docs/diagrams/presentation-png')
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1600, 900
BG = (246, 249, 255)
NAVY = (20, 33, 61)
BLUE = (49, 94, 251)
CYAN = (53, 183, 216)
PURPLE = (120, 86, 214)
RED = (194, 65, 50)
GREEN = (17, 132, 91)
TEXT = (52, 69, 99)
MUTED = (100, 116, 139)
LINE = (183, 199, 229)
WHITE = (255, 255, 255)


def font(size, bold=False):
    names = [
        'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


F_TITLE = font(42, True)
F_SUB = font(22)
F_H = font(25, True)
F_BODY = font(19)
F_SMALL = font(18)
F_FOOT = font(21)


def canvas(title, subtitle):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    # Soft horizontal tint echoing the dashboard header.
    for y in range(H):
        t = y / H
        c = tuple(int(BG[i] * (1 - .08 * t) + (234, 241, 255)[i] * (.08 * t)) for i in range(3))
        d.line((0, y, W, y), fill=c)
    d.text((90, 55), title, font=F_TITLE, fill=NAVY)
    d.text((90, 108), subtitle, font=F_SUB, fill=MUTED)
    return im, d


def rounded(d, box, fill=WHITE, outline=(205, 218, 241), radius=22, width=2):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def centered(d, xy, text, f, fill, anchor='mm'):
    d.text(xy, text, font=f, fill=fill, anchor=anchor)


def arrow(d, start, end, fill=BLUE, width=4, head=12):
    d.line((*start, *end), fill=fill, width=width)
    import math
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - head * math.cos(angle - .45), end[1] - head * math.sin(angle - .45))
    right = (end[0] - head * math.cos(angle + .45), end[1] - head * math.sin(angle + .45))
    d.polygon([end, left, right], fill=fill)


def save(im, name):
    path = OUT / name
    im.save(path, 'PNG', optimize=True)
    print(path)


def architecture():
    im, d = canvas('TraceTrust · Arquitectura por capas', 'Una capa analítica auditable entre los snapshots y las consultas de negocio')
    cards = [(90, 205, 370, 355), (430, 180, 730, 380), (790, 155, 1090, 405), (1140, 180, 1440, 380)]
    for b in cards:
        rounded(d, b)
    rounded(d, (570, 535, 1030, 715), fill=NAVY, outline=NAVY)
    rounded(d, (1110, 535, 1440, 715))
    data = [
        ('1 · Ingesta', ['JSONL / CSV', 'Manifest · SHA-256', 'Anonimización']),
        ('2 · Dominio', ['Eventos canónicos', 'Evidencias · snapshots', 'Contratos Pydantic']),
        ('3 · Análisis', ['Reconciliación explicable', 'Reglas deterministas', 'Isolation Forest', 'Trust Score']),
        ('4 · Proyección', ['SQLite read model', 'PostgreSQL', 'NetworkX · Neo4j']),
    ]
    for (b, (h, lines)) in zip(cards, data):
        cx = (b[0] + b[2]) // 2
        d.text((cx, b[1] + 32), h, font=F_H, fill=BLUE, anchor='ma')
        for i, line in enumerate(lines):
            centered(d, (cx, b[1] + 80 + i * 35), line, F_BODY, TEXT)
    centered(d, (800, 575), '5 · Servicios de confianza', F_H, WHITE)
    centered(d, (800, 620), 'API · consultas · hallazgos', F_BODY, (220, 231, 255))
    centered(d, (800, 660), 'visualización · IA · auditoría', F_BODY, (220, 231, 255))
    centered(d, (1275, 575), '6 · Experiencia', F_H, BLUE)
    centered(d, (1275, 620), 'dashboard interactivo', F_BODY, TEXT)
    centered(d, (1275, 660), 'global → drill-down', F_BODY, TEXT)
    arrow(d, (370, 280), (430, 280)); arrow(d, (730, 280), (790, 280)); arrow(d, (1090, 280), (1140, 280))
    arrow(d, (1290, 380), (950, 535)); arrow(d, (950, 625), (1110, 625))
    centered(d, (800, 820), 'Offline · determinista · auditable · reproducible', F_FOOT, MUTED)
    save(im, '01-architecture.png')


def pipeline():
    im, d = canvas('TraceTrust · Pipeline analítico reproducible', 'Cada etapa conserva evidencia, versión del algoritmo y explicación')
    boxes = [(70, 245, 290, 415), (340, 245, 560, 415), (610, 245, 830, 415), (880, 245, 1100, 415), (1150, 245, 1370, 415)]
    items = [
        ('Snapshot', ['manifest', 'hash · row count', 'privacy policy']),
        ('Canonicalizar', ['eventos', 'lotes · evidencias', 'raw payload']),
        ('Reconciliar', ['one-to-one', 'score por componente', 'match / review']),
        ('Detectar', ['reglas de integridad', 'Isolation Forest', 'findings']),
        ('Evaluar', ['precision / recall', 'benchmarks', 'calibración']),
    ]
    for b, (h, lines) in zip(boxes, items):
        rounded(d, b)
        cx = (b[0] + b[2]) // 2
        centered(d, (cx, 292), h, F_H, BLUE)
        for i, line in enumerate(lines):
            centered(d, (cx, 335 + i * 30), line, F_SMALL, TEXT)
    rounded(d, (670, 575, 930, 725), fill=NAVY, outline=NAVY)
    rounded(d, (1020, 575, 1280, 725))
    centered(d, (800, 625), 'Trust Score', F_H, WHITE)
    centered(d, (800, 665), '6 factores explicables', F_SMALL, (220, 231, 255))
    centered(d, (800, 695), 'penalizaciones críticas', F_SMALL, (220, 231, 255))
    centered(d, (1150, 625), 'Artefactos', F_H, BLUE)
    centered(d, (1150, 665), 'grafo · JSONL', F_SMALL, TEXT)
    centered(d, (1150, 695), 'API · dashboard', F_SMALL, TEXT)
    for a, b in zip(boxes[:-1], boxes[1:]):
        arrow(d, (a[2], 330), (b[0], 330))
    arrow(d, (1260, 415), (1260, 575)); arrow(d, (990, 415), (800, 575)); arrow(d, (930, 650), (1020, 650))
    centered(d, (800, 820), 'Offline · determinista · auditable · reproducible', F_FOOT, MUTED)
    save(im, '02-analytical-pipeline.png')


def graph_model():
    im, d = canvas('TraceTrust · Modelo de grafo', 'La trazabilidad se consulta como relaciones, no como registros aislados')
    nodes = [
        ((250, 425), 95, BLUE, 'LOTE', 'lot-00006'), ((640, 425), 105, CYAN, 'EVENTO', 'transformation'),
        ((1030, 425), 105, CYAN, 'EVENTO', 'shipping'), ((1420, 425), 95, PURPLE, 'EVIDENCIA', 'delivery_receipt'),
        ((400, 700), 95, RED, 'HALLAZGO', 'orphan_lot'), ((1190, 700), 95, GREEN, 'TRUST', '72.40 / 100')]
    for start, end in [((345, 425), (535, 425)), ((745, 425), (925, 425)), ((1135, 425), (1325, 425)), ((585, 500), (455, 635)), ((1080, 500), (1150, 635)), ((880, 400), (760, 250))]:
        arrow(d, start, end, fill=(120, 147, 199))
    for (xy, r, color, h, sub) in nodes:
        d.ellipse((xy[0]-r, xy[1]-r, xy[0]+r, xy[1]+r), fill=color, outline=WHITE, width=5)
        centered(d, (xy[0], xy[1]-12), h, font(24 if h != 'HALLAZGO' else 21, True), WHITE)
        centered(d, (xy[0], xy[1]+25), sub, F_SMALL, (230, 245, 255))
    labels = [((410, 410), 'produces / input_to'), ((805, 410), 'input_to / produces'), ((1200, 410), 'supported_by'), ((470, 590), 'concerns'), ((1080, 590), 'assesses'), ((735, 270), 'reconciles_with')]
    for xy, text in labels:
        d.text(xy, text, font=F_SMALL, fill=TEXT, anchor='mm')
    centered(d, (800, 840), 'Consultar ancestros · descendientes · impacto · evidencia · confianza', F_FOOT, MUTED)
    save(im, '03-graph-model.png')


def drilldown():
    im, d = canvas('TraceTrust · De la vista global al drill-down', 'Priorizar primero, investigar después')
    rounded(d, (90, 220, 700, 720)); rounded(d, (900, 220, 1510, 720))
    centered(d, (395, 275), '1 · Vista global', F_H, BLUE); centered(d, (395, 315), 'Todos los lotes del snapshot', F_SMALL, MUTED)
    centered(d, (1205, 275), '2 · Lote seleccionado', F_H, BLUE); centered(d, (1205, 315), 'Subgrafo y explicación', F_SMALL, MUTED)
    pts = [(190,390),(290,370),(400,430),(510,360),(590,470),(330,550),(500,590)]
    for a,b in zip(pts[:-1], pts[1:]): d.line((*a,*b), fill=LINE, width=3)
    d.line((290,370,260,470), fill=LINE, width=3); d.line((510,360,470,510), fill=LINE, width=3)
    for x,y in pts: d.ellipse((x-27,y-27,x+27,y+27), fill=BLUE, outline=WHITE, width=4)
    for x,y in [(260,470),(470,510)]: d.ellipse((x-20,y-20,x+20,y+20), fill=RED, outline=WHITE, width=4)
    # Selected subgraph
    center=(1040,465); d.ellipse((982,407,1098,523), fill=BLUE, outline=WHITE, width=5); centered(d,(1040,453),'LOTE',font(21,True),WHITE); centered(d,(1040,487),'00006',F_SMALL,(220,231,255))
    children=[((1190,365),'production'),((1190,565),'receipt'),((1350,365),'shipping'),((1350,565),'delivery')]
    for (x,y), label in children:
        d.ellipse((x-37,y-37,x+37,y+37), fill=CYAN, outline=WHITE, width=4); centered(d,(x,y),label,font(16),TEXT)
    for a,b in [((1090,465),(1160,365)),((1090,465),(1160,565)),((1225,365),(1315,365)),((1225,565),(1315,565))]: arrow(d,a,b,fill=(120,147,199),width=3)
    for x,y in [(1450,300),(1450,650)]: d.ellipse((x-27,y-27,x+27,y+27), fill=PURPLE, outline=WHITE, width=4)
    d.ellipse((1030,640,1090,700), fill=RED, outline=WHITE, width=4); centered(d,(1200,760),'Hallazgo: lote huérfano',F_SMALL,TEXT)
    arrow(d,(700,470),(900,470)); centered(d,(800,440),'click / drill-down',F_SMALL,BLUE)
    centered(d,(1205,805),'Click en un lote → eventos → evidencia → causa → Trust Score',F_SMALL,TEXT)
    centered(d,(800,840),'La vista global prioriza; el subgrafo explica',F_FOOT,MUTED)
    save(im, '04-global-drilldown.png')


if __name__ == '__main__':
    architecture(); pipeline(); graph_model(); drilldown()
