from PIL import Image

# Ruta de tu imagen PNG exportada desde QGIS
input_path = "Raster.png"
output_path = "Raster_transparente.png"

# Abrir imagen y convertir a RGBA (con canal alfa)
img = Image.open(input_path).convert("RGBA")
datas = img.getdata()

# Crear nueva lista de píxeles
nueva_imagen = []

for item in datas:
    # Si el píxel es blanco (RGB = 255,255,255), lo hacemos transparente
    if item[0] == 255 and item[1] == 255 and item[2] == 255:
        nueva_imagen.append((255, 255, 255, 0))  # Alfa = 0
    else:
        nueva_imagen.append(item)

# Aplicar nueva lista de píxeles a la imagen y guardar
img.putdata(nueva_imagen)
img.save(output_path)

print("✅ Fondo blanco eliminado y guardado como imagen con transparencia.")
