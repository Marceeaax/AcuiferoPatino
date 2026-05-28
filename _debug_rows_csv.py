import csv, io, os
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tesis.settings')
import django
django.setup()
from mapas.views import normalizar_columna, valor_csv, parsear_decimal, fila_csv_estructuralmente_vacia
from django.contrib.gis.geos import Point

p = Path(r"C:\Users\marce\tesis\Muestreo_2001_para_subir.csv")
contenido = p.read_text(encoding='utf-8-sig')
try:
    dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=';,\t')
except csv.Error:
    dialecto = csv.excel_tab
    dialecto.delimiter = '\t'
lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
aliases = {
    'codigo_pozo': ['codigo pozo'], 'nombre': ['nombre lugar', 'nombre', 'lugar'],
    'x': ['x', 'longitud x', 'lon', 'longitude'], 'y': ['y', 'latitud y', 'lat', 'latitude'], 'fecha_toma': ['fecha muestreo', 'fecha toma', 'fecha'],
    'n_amoniaca': ['n amoniacal mg l', 'n amoniacal'], 'nitritos': ['n nitritos mg l', 'n nitritos', 'nitritos'], 'nitratos': ['n nitratos mg l', 'n nitratos', 'nitratos'],
    'alcalinida': ['alcalinidad total mg l', 'alcalinidad total', 'alcalinidad'], 'materia_or': ['materia organica mg l', 'materia organica'],
    'conductivi': ['conductividad us cm', 'conductividad'], 'ph': ['ph'], 'bicarbonat': ['bicarbonato mg l', 'bicarbonato'],
    'carbonatos': ['carbonato mg l', 'carbonato'], 'sulfatos': ['sulfato mg l', 'sulfato'], 'magnesio': ['magnesio mg l', 'magnesio'],
    'calcio': ['calcio mg l', 'calcio'], 'sodio': ['sodio mg l', 'sodio'], 'potasio': ['potasio mg l', 'potasio'], 'cloruro': ['cloruro mg l', 'cloruro'],
    'arsenico': ['arsenico mg l', 'arsenico'], 'mercurio': ['mercurio mg l', 'mercurio'], 'manganeso': ['manganeso mg l', 'manganeso'], 'cobre': ['cobre mg l', 'cobre'],
    'cromo': ['cromo total mg l', 'cromo total', 'cromo'], 'col_fecale': ['coliformes fecales ufc 100 ml', 'coliformes fecales', 'coliformes']
}
filas=[]
for fila in lector:
    fila_normalizada = {normalizar_columna(k): v for k, v in fila.items() if k is not None}
    if fila_csv_estructuralmente_vacia(fila_normalizada):
        continue
    filas.append(fila_normalizada)
errors=[]
for idx, fila in enumerate(filas, start=2):
    try:
        x = parsear_decimal(valor_csv(fila, aliases, 'x'))
        y = parsear_decimal(valor_csv(fila, aliases, 'y'))
        if x is None or y is None:
            errors.append((idx, 'xy invalid', fila))
            continue
        geom = Point(x, y, srid=32721)
        geom.transform(4326)
    except Exception as e:
        errors.append((idx, repr(e), fila))
print('rows', len(filas), 'errors', len(errors))
for item in errors[:10]:
    print(item[0], item[1], item[2])
