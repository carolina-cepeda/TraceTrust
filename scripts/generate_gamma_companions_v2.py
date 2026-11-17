from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

OUT = Path('docs/diagrams/gamma-companions-v2')
OUT.mkdir(parents=True, exist_ok=True)
W, H = 720, 960
CREAM = (237, 232, 218); BLACK = (20, 19, 16); WHITE = (255, 255, 255)
BLUE = (45, 82, 255); LAV = (155, 158, 242); CYAN = (82, 185, 208)
RED = (197, 67, 53); GREEN = (28, 137, 96); GREY = (198, 193, 182)
MUTED = (112, 108, 98); NAVY = (27, 34, 64)

def ft(size, bold=False):
    p = Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf')
    return ImageFont.truetype(p, size) if p.exists() else ImageFont.load_default()

def base():
    im = Image.new('RGB', (W, H), CREAM); d = ImageDraw.Draw(im)
    d.rounded_rectangle((28,28,W-28,H-28), 28, outline=(214,208,194), width=3)
    return im,d

def text(d, xy, s, size=20, fill=BLACK, bold=False, anchor='mm'):
    d.text(xy, s, font=ft(size,bold), fill=fill, anchor=anchor)

def panel(d, box, fill=WHITE, outline=(216,210,196), r=20, shadow=True):
    if shadow:
        x1,y1,x2,y2=box; d.rounded_rectangle((x1+7,y1+8,x2+7,y2+8),r,fill=(220,214,201))
    d.rounded_rectangle(box,r,fill=fill,outline=outline,width=3)

def line(d,a,b,fill=BLACK,w=5): d.line((*a,*b),fill=fill,width=w)

def arrow(d,a,b,fill=BLUE,w=6):
    line(d,a,b,fill,w); ang=math.atan2(b[1]-a[1],b[0]-a[0]); s=17
    p1=(b[0]-s*math.cos(ang-.5),b[1]-s*math.sin(ang-.5)); p2=(b[0]-s*math.cos(ang+.5),b[1]-s*math.sin(ang+.5))
    d.polygon([b,p1,p2],fill=fill)

def dot(d,x,y,r,color,outline=BLACK,w=3): d.ellipse((x-r,y-r,x+r,y+r),fill=color,outline=outline,width=w)

def save(im,n): im.save(OUT/n,'PNG',optimize=True)

def s1():
    im,d=base(); text(d,(360,82),'FUENTES DISPERSAS',18,MUTED,True)
    # source cards
    cards=[(80,150,'CSV'),(390,150,'JSONL'),(80,265,'ERP'),(390,265,'PDF')]
    for x,y,label in cards:
        panel(d,(x,y,x+250,y+78),WHITE,r=14)
        d.rectangle((x+18,y+20,x+48,y+58),fill=LAV if label in ('CSV','PDF') else BLUE)
        text(d,(x+72,y+39),label,23,BLACK,True,'lm')
        line(d,(x+125,y+39),(x+220,y+39),GREY,4)
    arrow(d,(360,370),(360,445),BLACK,6)
    panel(d,(95,445,625,640),fill=BLACK,outline=BLACK)
    text(d,(360,482),'TRACETRUST',31,WHITE,True)
    text(d,(360,530),'normaliza · relaciona · explica',19,(228,224,214))
    # graph with trust halo
    pts=[(190,755),(360,690),(530,755),(360,835)]
    for a,b in [(pts[0],pts[1]),(pts[1],pts[2]),(pts[1],pts[3]),(pts[3],pts[2])]: line(d,a,b,NAVY,7)
    for i,(x,y) in enumerate(pts): dot(d,x,y,40,BLUE if i==1 else LAV)
    text(d,(360,895),'trazabilidad confiable',22,BLACK,True)
    save(im,'01-problema-datos.png')

def s2():
    im,d=base(); text(d,(360,82),'CAPA ANALÍTICA',18,MUTED,True)
    panel(d,(90,135,630,815),fill=(232,227,215),outline=(205,198,184))
    # central node
    dot(d,360,455,82,BLACK); text(d,(360,445),'TRACE',24,WHITE,True); text(d,(360,480),'TRUST',24,WHITE,True)
    modules=[((180,245),'SNAPSHOT',BLUE),((540,245),'EVENTOS',LAV),((170,665),'GRAFO',CYAN),((550,665),'DASHBOARD',GREEN)]
    for (x,y),lab,col in modules:
        panel(d,(x-90,y-42,x+90,y+42),WHITE,r=14); dot(d,x-55,y,15,col,BLACK,2); text(d,(x+12,y),lab,16,BLACK,True)
        arrow(d,(x,y+48 if y<455 else y-48),(360,373 if y<455 else 537),BLUE,4)
    text(d,(360,865),'una vista común para datos heterogéneos',19,BLACK,True)
    save(im,'02-que-es-tracetrust.png')

def s3():
    im,d=base(); text(d,(360,82),'ARQUITECTURA',18,MUTED,True)
    layers=[('01','INGESTA','JSONL · CSV · SHA-256',LAV),('02','DOMINIO','eventos · lotes · evidencias',BLUE),('03','ANÁLISIS + IA','reglas · reconciliación · anomalías',BLACK),('04','PROYECCIÓN','SQLite · grafo · read model',BLUE),('05','ACCESO','API · dashboard · auditoría',LAV)]
    y=145
    for i,(num,lab,sub,col) in enumerate(layers):
        x=82+i*9; box=(x,y+i*123,638-i*18,y+i*123+94)
        panel(d,box,col,BLACK,r=16,shadow=False)
        d.ellipse((box[0]+20,box[1]+23,box[0]+68,box[1]+71),fill=WHITE if col==BLACK else BLACK)
        text(d,(box[0]+44,box[1]+47),num,15,BLACK if col==BLACK else WHITE,True)
        text(d,(box[0]+92,box[1]+34),lab,21,WHITE if col in (BLACK,BLUE) else BLACK,True,'lm')
        text(d,(box[0]+92,box[1]+67),sub,15,(232,228,218) if col==BLACK else (35,40,55),False,'lm')
        if i < len(layers)-1: arrow(d,(360,box[3]+5),(360,box[3]+28),BLUE,4)
    text(d,(360,850),'responsabilidades separadas · contratos verificables',18,BLACK,True)
    save(im,'03-arquitectura.png')

def s4():
    im,d=base(); text(d,(360,82),'EVENTO CANÓNICO',18,MUTED,True)
    panel(d,(75,145,645,485),WHITE,r=20)
    d.rectangle((75,145,645,225),fill=BLACK)
    text(d,(110,185),'EVENT',18,WHITE,True,'lm'); text(d,(600,185),'transformation',18,(235,231,220),False,'rm')
    rows=[('event_id','evt-00042'),('timestamp','2026-01-01 14:00'),('input_lots','lot-00003'),('output_lots','lot-00006'),('evidence','sha256: 8f2a…')]
    for i,(k,v) in enumerate(rows):
        y=270+i*40; text(d,(115,y),k,17,MUTED,True,'lm'); text(d,(320,y),v,17,BLACK,False,'lm'); line(d,(105,y+18),(615,y+18),(225,221,210),2)
    # relation strip
    text(d,(360,555),'se convierte en relación',18,MUTED,True)
    dot(d,155,710,54,BLUE); text(d,(155,710),'LOTE',16,WHITE,True)
    dot(d,360,710,62,CYAN); text(d,(360,710),'EVENTO',16,WHITE,True)
    dot(d,565,710,54,LAV); text(d,(565,710),'EVIDENCIA',14,BLACK,True)
    arrow(d,(215,710),(295,710),BLACK,5); arrow(d,(425,710),(505,710),BLACK,5)
    text(d,(360,845),'evidencia + contexto + genealogía',20,BLACK,True)
    save(im,'04-evento-canonico.png')

def s5():
    im,d=base(); text(d,(360,82),'DETECCIÓN EXPLICABLE',18,MUTED,True)
    panel(d,(80,135,640,360),WHITE,r=18)
    text(d,(110,175),'RECONCILIACIÓN',18,BLACK,True,'lm'); text(d,(110,220),'fuente A',17,MUTED,True,'lm'); text(d,(110,275),'fuente B',17,MUTED,True,'lm')
    for y,col in [(220,BLUE),(275,LAV)]:
        line(d,(210,y),(530,y),col,18); dot(d,210,y,12,col); dot(d,530,y,12,col)
    line(d,(365,220),(365,275),RED,6); text(d,(570,250),'mismatch',17,RED,True)
    panel(d,(80,410,640,720),fill=BLACK,outline=BLACK,r=18)
    text(d,(110,450),'REGLA + MODELO',18,WHITE,True,'lm')
    rules=[('cantidad',GREEN),('tiempo',BLUE),('evidencia',LAV)]
    for i,(lab,col) in enumerate(rules):
        y=520+i*55; dot(d,135,y,13,col,WHITE,2); text(d,(170,y),lab,18,WHITE,False,'lm'); line(d,(300,y),(545,y),GREY,8)
    panel(d,(135,765,585,845),fill=RED,outline=RED,r=14,shadow=False); text(d,(360,805),'HALLAZGO EXPLICABLE',19,WHITE,True)
    save(im,'05-inconsistencias.png')

def s6():
    im,d=base(); text(d,(360,82),'TRUST SCORE',18,MUTED,True)
    # gauge
    d.arc((110,145,610,645),180,360,fill=(207,201,188),width=42); d.arc((110,145,610,645),180,310,fill=GREEN,width=42)
    text(d,(360,390),'72.40',65,GREEN,True); text(d,(360,455),'/ 100',25,BLACK,True)
    text(d,(360,525),'score compuesto',19,MUTED,True)
    factors=[('provenance evidence',.98),('genealogy continuity',.72),('quantity consistency',.84),('temporal coherence',.61),('cross validation',.76)]
    for i,(lab,val) in enumerate(factors):
        y=620+i*48; text(d,(105,y),lab,16,BLACK,False,'lm'); d.rounded_rectangle((340,y-8,610,y+8),8,fill=(211,205,194)); d.rounded_rectangle((340,y-8,340+270*val,y+8),8,fill=BLUE)
    save(im,'06-trust-score.png')

def s7():
    im,d=base(); text(d,(360,82),'DEMO INTERACTIVA',18,MUTED,True)
    # miniature dashboard
    panel(d,(70,140,650,570),WHITE,r=18)
    d.rectangle((70,140,650,205),fill=BLACK); text(d,(100,172),'TraceTrust',20,WHITE,True,'lm'); text(d,(610,172),'observed-126',15,(230,225,214),False,'rm')
    for i,(lab,num,col) in enumerate([('eventos','72',BLUE),('lotes','36',LAV),('hallazgos','12',RED)]):
        x=115+i*170; panel(d,(x,235,x+135,315),CREAM,CREAM,r=10,shadow=False); text(d,(x+18,258),lab,13,MUTED,True,'lm'); text(d,(x+18,292),num,25,col,True,'lm')
    # graph inside dashboard
    ps=[(155,430),(265,370),(380,450),(500,350),(555,480)]
    for a,b in zip(ps[:-1],ps[1:]): line(d,a,b,(180,190,215),4)
    for i,(x,y) in enumerate(ps): dot(d,x,y,20,RED if i==3 else BLUE,WHITE,3)
    arrow(d,(360,625),(360,700),BLUE,6)
    panel(d,(120,730,600,825),fill=BLACK,outline=BLACK,r=14,shadow=False); text(d,(360,778),'global → lote → causa',21,WHITE,True)
    text(d,(360,875),'la navegación hace visible la investigación',18,BLACK,True)
    save(im,'07-demo.png')

def s8():
    im,d=base(); text(d,(360,82),'VALIDACIÓN',18,MUTED,True)
    # metric cards
    vals=[('72','eventos',BLUE),('36','lotes',LAV),('12','hallazgos',RED),('98.5','trust medio',GREEN)]
    for i,(num,lab,col) in enumerate(vals):
        y=145+i*135; panel(d,(80,y,640,y+100),WHITE,r=16); dot(d,135,y+50,28,col,BLACK,2); text(d,(135,y+50),num,18,WHITE if col!=LAV else BLACK,True); text(d,(205,y+42),lab,18,BLACK,True,'lm'); text(d,(205,y+70),'escenario robusto',13,MUTED,False,'lm')
    panel(d,(110,720,610,830),fill=BLACK,outline=BLACK,r=14,shadow=False); text(d,(360,755),'reproducible · auditable',20,WHITE,True); text(d,(360,795),'métricas derivadas de snapshots offline',15,(230,225,214))
    save(im,'08-resultados.png')

def s9():
    im,d=base(); text(d,(360,82),'EVOLUCIÓN',18,MUTED,True)
    text(d,(100,145),'IMPLEMENTADO',18,BLACK,True,'lm'); text(d,(100,525),'SIGUIENTE ITERACIÓN',18,BLUE,True,'lm')
    panel(d,(80,185,640,450),WHITE,r=18)
    panel(d,(80,565,640,830),fill=(226,224,245),outline=BLUE,r=18)
    today=[('01','snapshots offline'),('02','grafo consultable'),('03','reglas explicables'),('04','dashboard')]
    future=[('01','streaming'),('02','modelos de IA'),('03','conectores reales'),('04','multi-tenant')]
    for i,(num,lab) in enumerate(today):
        y=230+i*52; dot(d,135,y,15,GREEN,BLACK,2); text(d,(135,y),num,11,WHITE,True); text(d,(175,y),lab,18,BLACK,True,'lm'); line(d,(175,y+20),(570,y+20),GREY,2)
    for i,(num,lab) in enumerate(future):
        y=610+i*52; dot(d,135,y,15,BLUE,BLACK,2); text(d,(135,y),num,11,WHITE,True); text(d,(175,y),lab,18,BLACK,True,'lm'); line(d,(175,y+20),(570,y+20),(180,183,220),2)
    arrow(d,(360,470),(360,540),BLUE,6); text(d,(360,505),'evolución incremental',16,MUTED,True)
    text(d,(360,875),'crecer sin romper la trazabilidad existente',18,BLACK,True)
    save(im,'09-roadmap.png')

if __name__=='__main__':
    for fn in (s1,s2,s3,s4,s5,s6,s7,s8,s9): fn()
