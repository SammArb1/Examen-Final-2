from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from fastapi.responses import RedirectResponse
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import os

app = FastAPI(
    title="Sistema de Almacenamiento S3 - Universidad EIA",
    description="API para cargar y consultar imágenes personalizadas por usuario en AWS S3",
    version="1.0.0"
)

# =====================================================================
# CONFIGURACIÓN DE AWS S3
# =====================================================================
BUCKET_NAME = "imagenes-usuarios-eia-samm"  # <-- REEMPLAZA CON EL NOMBRE DE TU BUCKET
AWS_REGION = "us-east-2"

# Inicializar cliente de S3 (boto3 tomará las credenciales de la instancia EC2 o del entorno)
s3_client = boto3.client('s3', region_name=AWS_REGION)

# Formatos permitidos
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}

@app.get("/", include_in_schema=False)
def root():
    """Redirecciona automáticamente al Swagger para pruebas rápidas."""
    return RedirectResponse(url="/docs")


# =====================================================================
# ENDPOINT POST: CARGAR IMAGEN (Punto 2.a, 2.b, 2.c)
# =====================================================================
@app.post("/api/images/upload", status_code=status.HTTP_201_CREATED, tags=["Imágenes"])
async def upload_image(
    username: str = Form(..., description="Nombre del usuario"),
    file: UploadFile = File(..., description="Imagen en formato PNG o JPG/JPEG")
):
    # 1. Validar nombre de usuario limpio
    clean_username = username.strip().replace(" ", "_").lower()
    if not clean_username:
        raise HTTPException(status_code=400, detail="El nombre de usuario no puede estar vacío.")

    # 2. Validar formato/extensión del archivo
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato no permitido ({file.filename}). Solo se aceptan archivos PNG, JPG o JPEG."
        )

    # 3. Estructurar la ruta dentro del Bucket: usuario/nombre_archivo
    s3_key = f"{clean_username}/{file.filename}"

    try:
        # Leer el contenido del archivo subido
        file_content = await file.read()
        
        # Subir a S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_content,
            ContentType=file.content_type
        )
        
        return {
            "message": "Imagen almacenada con éxito en S3",
            "usuario": clean_username,
            "ruta_s3": f"s3://{BUCKET_NAME}/{s3_key}",
            "archivo": file.filename
        }
        
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error en AWS S3: {e.response['Error']['Message']}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# =====================================================================
# ENDPOINT GET: CONSULTAR IMAGEN Y GENERAR URL (Punto 2.d, 2.e)
# =====================================================================
@app.get("/api/images/retrieve", tags=["Imágenes"])
def retrieve_image(
    username: str,
    image_name: str
):
    clean_username = username.strip().replace(" ", "_").lower()
    s3_key = f"{clean_username}/{image_name}"

    try:
        # 1. Verificar existencia del objeto y obtener metadatos (head_object)
        metadata = s3_client.head_object(Bucket=BUCKET_NAME, Key=s3_key)
        
        # Extraer la fecha de almacenamiento (LastModified)
        fecha_almacenamiento: datetime = metadata['LastModified']
        
        # 2. Generar una URL prefirmada (Expira en 1 hora = 3600 segundos)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=3600
        )

        return {
            "status": "Encontrado",
            "usuario": clean_username,
            "imagen": image_name,
            "fecha_almacenamiento_utc": fecha_almacenamiento.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "url_prefirmada": presigned_url
        }

    except ClientError as e:
        # Si el código es 404, significa que el usuario o la imagen no existen en esa ruta
        if e.response['Error']['Code'] == "404":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Error: No se encontró el registro para el usuario '{clean_username}' con la imagen '{image_name}' en S3."
            )
        raise HTTPException(status_code=500, detail=f"Error en AWS S3: {e.response['Error']['Message']}")