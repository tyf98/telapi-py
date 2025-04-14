from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
import segno
import logging
from staticmap import StaticMap, CircleMarker
from geopy.geocoders import Nominatim
import xml.etree.ElementTree as ET
from pydantic import BaseModel, Field
from shapely.geometry import Polygon
import fitz  # PyMuPDF
import hashlib
import base64
from typing import List, Optional
import secrets
import string

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

# ==================== Constants ====================
LOGO_SIZE = (80, 80)
X_MARGIN = 50
SIGNATURES_PER_ROW = 2
PAGE_BOTTOM_MARGIN = 100
PAGE_TOP_Y = 30
SIGNATURE_START_Y = 150
FONT_SIZE_TITLE = 12
FONT_SIZE_NAME = 12
FONT_SIZE_TIMESTAMP = 10
LINE_WIDTH = 200

# ==================== Models ====================
class SignatureEntry(BaseModel):
    role: str
    name: str
    adname: str
    timestamp: str = Field(..., regex=r".+\d{4}.*GMT\+8")  # Simple regex check

class PDFRequest(BaseModel):
    file_name: str = Field(..., min_length=1)
    file_content: str  # Base64-encoded PDF
    level_1: List[SignatureEntry] = []
    level_2: List[SignatureEntry] = []
    level_3: List[SignatureEntry] = []
    level_4: List[SignatureEntry] = []
    level_5: List[SignatureEntry] = []
    logo_url_1: str
    logo_url_2: str

# ==================== Utility Functions ====================
def generate_strong_password(length: int = 32) -> str:
    """Generates a cryptographically secure strong password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def encrypt_pdf(pdf_document) -> tuple[bytes, str]:
    """Encrypts the PDF with a strong random password (editing restricted)."""
    owner_password = generate_strong_password()
    output_stream = BytesIO()
    pdf_document.save(
        output_stream,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="",  # Anyone can view
        owner_pw=owner_password,  # Cannot edit without this password
        permissions=660  # Allow printing + copying
    )
    return output_stream.getvalue(), owner_password

def fetch_and_resize_image(url: str, size=LOGO_SIZE) -> Optional[bytes]:
    """Fetches an image from URL, resizes it, and converts it to bytes."""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        img = img.convert("RGBA")
        img.thumbnail(size)
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format="PNG")
        return img_byte_arr.getvalue()
    except (requests.RequestException, UnidentifiedImageError):
        return None

def embed_image(page, image_bytes: Optional[bytes], x: float, y: float):
    """Embeds an image at a specific (x, y) location on the PDF page."""
    if image_bytes:
        image_rect = fitz.Rect(x, y, x + LOGO_SIZE[0], y + LOGO_SIZE[1])
        page.insert_image(image_rect, stream=image_bytes)

def insert_header_text(page, page_width):
    """Inserts branding text at the top of the signature page."""
    page.insert_text((page_width / 2 - 70, 40), "Signed using SMaRT Sign", fontsize=FONT_SIZE_TITLE, fontname="helvetica")
    page.insert_text((page_width / 2 - 70, 60), "Proudly brought to you by:", fontsize=FONT_SIZE_TITLE, fontname="helvetica")
    page.insert_text((page_width / 2 - 55, 75), "Agility, Enterprise IT", fontsize=FONT_SIZE_TITLE, fontname="helvetica")

def add_signature_page(pdf_bytes: bytes, request: PDFRequest) -> tuple[bytes, str]:
    """Adds signature pages dynamically based on content size."""
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    levels = [lvl for lvl in [request.level_1, request.level_2, request.level_3, request.level_4, request.level_5] if lvl]
    if not levels:
        return encrypt_pdf(pdf_document)

    # Load logos once
    logo_1 = fetch_and_resize_image(request.logo_url_1)
    logo_2 = fetch_and_resize_image(request.logo_url_2)

    try:
        for level in levels:
            page = pdf_document.new_page()
            page_width = page.rect.width
            y_offset = SIGNATURE_START_Y
            col_position = 0
            insert_header_text(page, page_width)
            embed_image(page, logo_1, X_MARGIN, PAGE_TOP_Y)
            embed_image(page, logo_2, page_width - X_MARGIN - LOGO_SIZE[0], PAGE_TOP_Y)

            for i, entry in enumerate(level):
                # Prepare signature block
                header_x = X_MARGIN + (col_position * (page_width - 2 * X_MARGIN) / 2)
                name_x = header_x
                line_x_start = header_x
                line_x_end = header_x + LINE_WIDTH
                timestamp_x = header_x

                # Y positions
                y = y_offset
                line_y = y + 20
                timestamp_y = line_y + 15

                # Signature text
                page.insert_text((header_x, y), f"{entry.role} By:", fontsize=FONT_SIZE_TITLE, fontname="helvetica-bold")
                page.insert_text((name_x, y + 15), entry.name, fontsize=FONT_SIZE_NAME, fontname="times-italic", color=(0, 0, 1))
                page.draw_line((line_x_start, line_y), (line_x_end, line_y))
                page.insert_text((timestamp_x, timestamp_y), f"{entry.adname} ({entry.timestamp})", fontsize=FONT_SIZE_TIMESTAMP, fontname="helvetica")

                # Handle column and row switching
                col_position += 1
                if col_position >= SIGNATURES_PER_ROW:
                    col_position = 0
                    y_offset += 100

                # Create new page if space is exceeded
                if y_offset > page.rect.height - PAGE_BOTTOM_MARGIN:
                    page = pdf_document.new_page()
                    y_offset = SIGNATURE_START_Y
                    col_position = 0
                    insert_header_text(page, page_width)
                    embed_image(page, logo_1, X_MARGIN, PAGE_TOP_Y)
                    embed_image(page, logo_2, page_width - X_MARGIN - LOGO_SIZE[0], PAGE_TOP_Y)

        return encrypt_pdf(pdf_document)

    finally:
        pdf_document.close()

def compute_md5_hash(pdf_bytes: bytes) -> str:
    """Compute MD5 hash of the given PDF bytes."""
    return hashlib.md5(pdf_bytes).hexdigest()

# ==================== Endpoint ====================
@app.post("/process-pdf-refactored/")
async def process_pdf_refactored(request: PDFRequest):
    try:
        pdf_bytes = base64.b64decode(request.file_content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64-encoded PDF content")

    try:
        modified_pdf, owner_password = add_signature_page(pdf_bytes, request)
        pdf_hash = compute_md5_hash(modified_pdf)
        modified_pdf_base64 = base64.b64encode(modified_pdf).decode("utf-8")

        return JSONResponse(content={
            "md5_hash": pdf_hash,
            "modified_pdf": modified_pdf_base64,
            "owner_password": owner_password  # ⚠️ Return only if it's safe to expose
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")