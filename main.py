from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont
import segno
import logging
from staticmap import StaticMap, CircleMarker
from geopy.geocoders import Nominatim
import xml.etree.ElementTree as ET
from pydantic import BaseModel
from shapely.geometry import Polygon
import fitz  # PyMuPDF
import hashlib
import io
import datetime
import base64

app = FastAPI()
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

defaultLogo = "https://i.ibb.co/6stFKBY/Corp-Circular.png"

class PolygonData(BaseModel): 
    xml_data: str

@app.get("/polygon") 
async def process_polygon(xml_data: str):
    root = ET.fromstring(xml_data) 
    coordinates = root.find('.//coordinates').text.strip().split() 
    coords = [(float(coord.split(',')[0]), float(coord.split(',')[1])) for coord in coordinates]
    
    # Create a polygon using shapely 
    polygon = Polygon(coords)
    
    map = StaticMap(800, 600) 
    for coord in polygon.exterior.coords: 
        marker = CircleMarker((coord[1], coord[0]), 'red', 12) 
        map.add_marker(marker)
    image = map.render()
    return save_result(image)

@app.get("/", response_class=Response)
def qrdemo(color: str = '#7A663C', logourl: str = defaultLogo, percentageOfQrCode: float=0.3):
    # Open QR code image
    qr_image = Image.open(generate_qr('Hello World!', color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode)

    # Save result
    return save_result(qr_image)

@app.get("/qrcode", response_class=Response)
def qrcode(data:str, color: str = '#7A663C', logourl: str = defaultLogo, percentageOfQrCode: float=0.3, textLabel: str | None = None, fontSize: int | None = None):

    # Open QR code image
    qr_image = Image.open(generate_qr(data, color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode, textLabel, fontSize)

    # Save result
    return save_result(qr_image)

@app.get("/staticmap")
def staticMap(deviceLat: float, deviceLon: float):
    # Create a new static map
    m = StaticMap(400, 400)

    # Create a marker for the device location
    marker = CircleMarker((deviceLon, deviceLat), 'red', 12)

    # Add the marker to the map
    m.add_marker(marker)

    # Render the map to an image
    image = m.render()

    # Save result
    return save_result(image)

@app.get("/get_address")
def get_address(deviceLat: float, deviceLon: float):
    
    geolocator = Nominatim(user_agent="Power_API")
    location = geolocator.reverse([deviceLat, deviceLon], exactly_one=True)
    address = location.raw['address']
    formatted_address = f"{address.get('house_number', '')} {address.get('road', '')}, {address.get('country', '')} {address.get('postcode', '')}"
    
    return formatted_address

##### Functions and Variables #####
def generate_qr(data: str, color: str = '#000000'):
    # Generate QR code
    qr = segno.make_qr(data, error='h')
    qr_buffer = BytesIO()
    qr.save(qr_buffer, kind='png', scale=32, border = 1, dark=color)
    qr_buffer.seek(0)
    return qr_buffer

def overlay_qr_code(qr_image, overlay_image, percentageOfQrCode, textLabel=None, fontSize=30):
    # Check if overlay_image is not None
    if overlay_image is None:
        logging.error("Overlay image is not available")
        return qr_image  # Return the original qr_image without overlay
        
    # Calculate size for overlay image (maintain aspect ratio)
    qr_code_size_without_border = ((qr_image.width // 25) * 24)  # Subtract the size of the quiet zone
    overlay_size = int(qr_code_size_without_border * percentageOfQrCode)
    overlay_width = int(overlay_image.width * overlay_size / overlay_image.height)
    overlay_height = int(overlay_image.height * overlay_size / overlay_image.width)
    overlay_image = overlay_image.resize((overlay_width, overlay_height))

    # Calculate position for overlay image (centered)
    position = ((qr_image.width - overlay_width) // 2, (qr_image.height - overlay_height) // 2)

    if textLabel is not None:
        logging.info("Text Label is not none.")
        
        # Create ImageDraw object
        draw = ImageDraw.Draw(overlay_image)

        # Specify font-size and type
        # font_size = 30
        font = ImageFont.truetype("./arialbd.ttf", fontSize)
        
        # Get the bounding box of the entire text block
        bbox = draw.textbbox((0, 0), textLabel, font=font)

        # The height is the difference between the bottom and top of the bounding box
        height = bbox[3] - bbox[1]
        width = bbox[2]
        
        draw.multiline_text(xy=((overlay_image.width-width)/2, (overlay_image.height-height)/2), text=textLabel, font=font, align="center", fill="#E32614")
        
    # Overlay image on QR code
    qr_image.paste(overlay_image, position, overlay_image)  # Use overlay_image as mask for transparency

    # Return the modified qr_image
    return qr_image

def fetch_logo(logourl: str):
    # Download overlay image from URL
    try:
        response = requests.get(logourl)
    except requests.exceptions.RequestException as e:
        logging.error(f" Invalid URL or base64 image: {e}")
        logging.error(f" Response: {response.__dict__ if 'response' in locals() else 'No response'}")
        return None

    # Check if the URL points to an image
    if 'content-type' not in response.headers or not response.headers['content-type'].startswith('image'):
        logging.error("URL does not point to an image")
        logging.error(f" Response: {response.__dict__ if 'response' in locals() else 'No response'}")
        return None
    
    return Image.open(BytesIO(response.content)).convert('RGBA')  # Convert overlay image to RGBA mode
    
def save_result(qr_image: Image):
    # Save result
    result_buffer = BytesIO()
    qr_image.save(result_buffer, format='png')
    result_buffer.seek(0)

    return StreamingResponse(result_buffer, media_type="image/png")

class PDFRequest(BaseModel):
    file_name: str
    file_content: str  # Base64 string
    name: str
    timestamp: str  # ISO 8601 format

def add_signature_page(pdf_bytes: bytes, name: str, timestamp: str) -> bytes:
    """Add a signature page with name and timestamp to the given PDF."""
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    # Create a blank page and add text
    page = pdf_document.new_page()
    text = f"Signed by: {name}\nDate: {timestamp}"
    page.insert_text((50, 100), text, fontsize=12)

    # Save modified PDF to bytes
    output_stream = BytesIO()
    pdf_document.save(output_stream)
    pdf_document.close()
    
    return output_stream.getvalue()

def compute_md5_hash(pdf_bytes: bytes) -> str:
    """Compute MD5 hash of the given PDF bytes."""
    return hashlib.md5(pdf_bytes).hexdigest()

@app.post("/process-pdf/")
async def process_pdf(request: PDFRequest):
    try:
        # Decode Base64 PDF file
        pdf_bytes = base64.b64decode(request.file_content)

        # Modify PDF (add signature page)
        modified_pdf = add_signature_page(pdf_bytes, request.name, request.timestamp)

        # Compute MD5 hash
        pdf_hash = compute_md5_hash(modified_pdf)

        # Encode modified PDF to Base64 for response
        modified_pdf_base64 = base64.b64encode(modified_pdf).decode("utf-8")

        return JSONResponse(content={
            "md5_hash": pdf_hash,
            "modified_pdf": modified_pdf_base64
        })
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing PDF: {str(e)}")