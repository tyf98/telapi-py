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
import base64
from typing import List

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

def encrypt_pdf(pdf_document, password="owner_password"):
    """Restricts editing of the PDF but allows viewing without a password."""
    pdf_document.save("output.pdf", encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="", owner_pw=password, permissions=int("1000101000", 2))
    with open("output.pdf", "rb") as f:
        return f.read()

class SignatureEntry(BaseModel):
    role: str
    name: str
    adname: str
    timestamp: str  # Format: "Feb 7, 2025 09:43 GMT+8"

class PDFRequest(BaseModel):
    file_name: str
    file_content: str  # Base64-encoded PDF
    level_1: List[SignatureEntry] = []
    level_2: List[SignatureEntry] = []
    level_3: List[SignatureEntry] = []
    level_4: List[SignatureEntry] = []
    level_5: List[SignatureEntry] = []
    logo_url_1: str  # First logo URL
    logo_url_2: str  # Second logo URL

def fetch_and_resize_image(url, size=(80, 80)):
    """Fetches an image from URL, resizes it, and converts it to bytes while preserving transparency."""
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None
        img = Image.open(BytesIO(response.content))
        img = img.convert("RGBA")  # Preserve transparency
        img.thumbnail(size)
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format="PNG")
        return img_byte_arr.getvalue()
    except Exception:
        return None

def embed_image(page, image_bytes, x, y):
    """Embeds an image at a specific (x, y) location on the PDF page."""
    if image_bytes:
        image_rect = fitz.Rect(x, y, x + 80, y + 80)
        page.insert_image(image_rect, stream=image_bytes)

def add_signature_page(pdf_bytes: bytes, request: PDFRequest) -> bytes:
    """Adds signature pages dynamically based on content size."""
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    levels = [request.level_1, request.level_2, request.level_3, request.level_4, request.level_5]
    
    # Filter out empty levels
    levels = [level for level in levels if level]
    if not levels:
        return encrypt_pdf(pdf_document)  # No signatures to add
    
    # Load Logos
    logo_1 = fetch_and_resize_image(request.logo_url_1)
    logo_2 = fetch_and_resize_image(request.logo_url_2)
    
    for level in levels:
        page = pdf_document.new_page()
        page_width = page.rect.width
        x_margin = 50
        embed_image(page, logo_1, x_margin, 30)  # Top-left
        embed_image(page, logo_2, page_width - x_margin - 80, 30)  # Top-right
        
        # Signature Block Formatting
        y_offset = 150
        column_width = (page_width - 2 * x_margin) / 2  # Divide into 2 columns
        font_size_title = 12
        font_size_name = 12
        font_size_timestamp = 10
        line_width = 200

        col_position = 0  # 0 = left, 1 = right
        signatures_per_row = 2
        row_count = 0

        for i, entry in enumerate(level):
            role_text = f"{entry.role} By:"
            name_text = entry.name
            timestamp_text = f"{entry.adname} ({entry.timestamp} GMT+8)"

            # Define X positions based on left or right column
            header_x = x_margin + (col_position * column_width)
            name_x = header_x
            line_x_start = header_x
            line_x_end = header_x + line_width
            timestamp_x = header_x

            # Define Y positions
            y = y_offset  # Adjust based on available space
            line_y = y + 20  # Line should be below the name
            timestamp_y = line_y + 15  # Timestamp should be slightly below the line

            # Insert Greetings
            page.insert_text((page_width/2-70,40),"Signed using SMaRT Sign", fontsize=font_size_title, fontname="helvetica")
            page.insert_text((page_width/2-70,60),"Proudly brought to you by:", fontsize=font_size_title, fontname="helvetica")
            page.insert_text((page_width/2-55,75),"Agility, Enterprise IT", fontsize=font_size_title, fontname="helvetica")
            
            # Insert text
            page.insert_text((header_x, y), role_text, fontsize=font_size_title, fontname="helvetica-bold")
            page.insert_text((name_x, y + 10), name_text, fontsize=font_size_name, fontname="courier-oblique", color=(0, 0, 1))  # Italic blue name

            # Draw signature line
            page.draw_line((line_x_start, line_y), (line_x_end, line_y))

            # Insert timestamp with correct formatting
            page.insert_text((timestamp_x, timestamp_y), timestamp_text, fontsize=font_size_timestamp, fontname="helvetica")

            # Switch column
            col_position += 1

            # If two signatures are placed in the row, move to next row
            if col_position >= signatures_per_row:
                col_position = 0  # Reset to left column
                y_offset += 100  # Move down for new row
                row_count += 1

            # If space is exceeded, start a new page
            if y_offset > page.rect.height - 100:
                page = pdf_document.new_page()
                y_offset = 150
                col_position = 0  # Reset to left column
                row_count = 0
    
    # Restrict PDF editing
    encrypted_pdf = encrypt_pdf(pdf_document)
    pdf_document.close()
    return encrypted_pdf

def compute_md5_hash(pdf_bytes: bytes) -> str:
    """Compute MD5 hash of the given PDF bytes."""
    return hashlib.md5(pdf_bytes).hexdigest()

@app.post("/process-pdf/")
async def process_pdf(request: PDFRequest):
    try:
        pdf_bytes = base64.b64decode(request.file_content)
        modified_pdf = add_signature_page(pdf_bytes, request)
        pdf_hash = compute_md5_hash(modified_pdf)
        modified_pdf_base64 = base64.b64encode(modified_pdf).decode("utf-8")

        return JSONResponse(content={
            "md5_hash": pdf_hash,
            "modified_pdf": modified_pdf_base64
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing PDF: {str(e)}")