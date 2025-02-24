from fastapi import FastAPI, Response, File, Form, HTTPException, Body
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
from typing import Optional
import fitz  # PyMuPDF
import hashlib
import io
import datetime
import base64

app = FastAPI()

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

async def add_signature_page(
    pdf_content: bytes,
    name: str,
    timestamp: str
) -> bytes:
    """
    Add a signature page to the PDF and return the modified content.
    """
    try:
        # Load PDF from memory
        memory_pdf = io.BytesIO(pdf_content)
        doc = fitz.open(stream=memory_pdf, filetype="pdf")
        
        # Add new page
        page = doc.new_page(width=595, height=842)  # A4 size
        
        # Define text properties
        font_size = 12
        title_font_size = 16
        page_width = page.rect.width
        
        # Function to center text
        def get_centered_position(text: str, font_size: int) -> float:
            # Create a temporary text span to measure
            text_span = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
            return (page_width - text_span) / 2
        
        # Add signature content
        title_text = "Signature Page"
        name_text = f"Name: {name}"
        timestamp_text = f"Timestamp: {timestamp}"
        
        # Insert centered text
        page.insert_text(
            point=(get_centered_position(title_text, title_font_size), 50),
            text=title_text,
            fontname="helv",
            fontsize=title_font_size
        )
        
        page.insert_text(
            point=(get_centered_position(name_text, font_size), 90),
            text=name_text,
            fontname="helv",
            fontsize=font_size
        )
        
        page.insert_text(
            point=(get_centered_position(timestamp_text, font_size), 120),
            text=timestamp_text,
            fontname="helv",
            fontsize=font_size
        )
        
        # Save the modified PDF to bytes
        output_buffer = io.BytesIO()
        doc.save(output_buffer)
        doc.close()
        
        return output_buffer.getvalue()
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )

def compute_md5(content: bytes) -> str:
    """
    Compute MD5 hash of the given content.
    """
    return hashlib.md5(content).hexdigest()


# New endpoint for Power Automate
@app.post("/process-pdf-base64/", response_class=JSONResponse)
async def process_pdf_base64(
    request_data: dict = Body(...)
):
    """
    Process a PDF file (base64 encoded) by adding a signature page and computing its MD5 hash.
    Designed for Power Automate integration.
    """
    try:
        # Extract fields from request body
        if 'pdf_content' not in request_data or 'name' not in request_data:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: pdf_content and name are required"
            )
            
        # Decode base64 PDF content
        try:
            pdf_content = base64.b64decode(request_data['pdf_content'])
        except:
            raise HTTPException(
                status_code=400,
                detail="Invalid base64 PDF content"
            )
            
        name = request_data['name']
        timestamp = request_data.get('timestamp') or datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        
        modified_pdf = await add_signature_page(pdf_content, name, timestamp)
        md5_hash = compute_md5(modified_pdf)
        
        return JSONResponse(
            content={
                "md5_hash": md5_hash,
                "pdf_content": base64.b64encode(modified_pdf).decode('utf-8')
            }
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "healthy"}